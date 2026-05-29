# django_ma/commission/services/collect.py
"""
환수관리(Collect) 서비스 레이어 — Step 5

[원칙]
- 뷰(api_collect.py, pages.py)는 이 모듈만 호출한다. 직접 ORM 금지.
- 수정·삭제 권한 판정은 반드시 이 서비스에서 수행.
  반환값 None / False → 뷰에서 403 처리.
- N+1 쿼리 금지: Subquery + annotate로 최신 피드백을 한 번에 조회.
- 월도 형식: "202603" (YYYYMM 6자리) — CollectRecord.ym 규약과 동일.
- transaction.atomic + select_for_update: 수정·삭제 경쟁조건 방지.
"""

from __future__ import annotations

import logging
from datetime import date
import re
from typing import Any, TypeAlias

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import OuterRef, QuerySet, Subquery

from accounts.models import CustomUser
from partner.models import SubAdminTemp
from commission.models import (
    CollectDropdownFeedback,
    CollectFeedback,
    CollectRecord,
    CollectUploadLog,
    DepositSummary,
)


logger = logging.getLogger(__name__)

CollectRow: TypeAlias = dict[str, Any]
DepositData: TypeAlias = dict[str, int]


# =============================================================================
# 월도 유틸 — YYYYMM 6자리 형식
# =============================================================================

def ym_to_date(ym: str) -> date:
    """
    "202603" → date(2026, 3, 1)
    잘못된 형식이면 ValueError.
    """
    try:
        return date(int(ym[:4]), int(ym[4:6]), 1)
    except Exception as exc:
        raise ValueError(f"월도 형식 오류: {ym!r}") from exc


def date_to_ym(d: date) -> str:
    """date(2026, 3, 1) → '202603'"""
    return f"{d.year:04d}{d.month:02d}"


def offset_ym(base_ym: str, months: int) -> str:
    """
    base_ym 기준으로 months만큼 이동한 월도를 반환한다.
    예) offset_ym("202603", -1) → "202602"
        offset_ym("202603", -2) → "202601"
    """
    d = ym_to_date(base_ym)
    return date_to_ym(d + relativedelta(months=months))


# =============================================================================
# 내부 헬퍼
# =============================================================================
def _parse_surety_bond_detail(detail: str) -> tuple[int, int]:
    """
    '채권:0 / 보증:0' 형식 문자열 파싱 → (채권합계, 보증합계)
    '채권:0 / 보증:0' 형식 문자열 파싱 → (bond_debt, bond_surety)
    반환: (채권:값, 보증:값)
    콤마 포함 숫자 지원: '채권:22,080,000 / 보증:40,000,000'

    예시:
        "채권:1500000 / 보증:500000" → (1500000, 500000)
        "채권:0 / 보증:0"            → (0, 0)
        ""                           → (0, 0)
    """
    debt, surety = 0, 0
    if not detail:
        return debt, surety
    try:
        # [\d,]+ : 콤마 포함 숫자 매칭 후 콤마 제거
        m_debt   = re.search(r"채권:(-?[\d,]+)", detail)
        m_surety = re.search(r"보증:(-?[\d,]+)", detail)
        if m_debt:   debt   = int(m_debt.group(1).replace(",", ""))
        if m_surety: surety = int(m_surety.group(1).replace(",", ""))
    except Exception:
        logger.exception(
            "[collect] surety bond detail parse failed detail=%r",
            detail,
        )
    return debt, surety


def _build_deposit_map(emp_ids: list[str]) -> dict[str, dict]:
    """
    emp_id 목록을 받아 DepositSummary의 환수 보조 필드를 dict로 반환한다.

    반환 형태:
        {
            emp_id: {
                "other_total": int,
                "refund_expected": int,
            }
        }

    DepositSummary.user_id == emp_id (CustomUser PK = 사번 문자열) 규약 활용.
    DepositSummary에 없는 emp_id는 0으로 처리.
    N+1 방지: bulk IN 쿼리 1회.
    """
    if not emp_ids:
        return {}
    qs = DepositSummary.objects.filter(
        user_id__in=emp_ids
    ).values_list("user_id", "other_total", "refund_expected")
    return {
        uid: {"other_total": o, "refund_expected": r}
        for uid, o, r in qs
    }

_DEPOSIT_DEFAULTS: DepositData = {
    "other_total": 0,
    "refund_expected": 0,
}


def _latest_feedback_subquery() -> Subquery:
    """
    CollectRecord QS에 annotate할 최신 피드백 content Subquery.
    emp_id 기준으로 CollectFeedback 최신 1건의 content를 가져온다.
    N+1 없이 단일 쿼리로 처리.
    """
    return Subquery(
        CollectFeedback.objects
        .filter(emp_id=OuterRef("emp_id"))
        .order_by("-created_at")
        .values("content")[:1]
    )


def _latest_branch_feedback_subquery() -> Subquery:
    """영업가족 드랍다운 피드백 최신값 Subquery (emp_id + ym 기준)."""
    return Subquery(
        CollectDropdownFeedback.objects
        .filter(emp_id=OuterRef("emp_id"), ym=OuterRef("ym"), feedback_type="branch")
        .order_by("-created_at")
        .values("value")[:1]
    )


def _latest_hq_feedback_subquery() -> Subquery:
    """본사 드랍다운 피드백 최신값 Subquery (emp_id + ym 기준)."""
    return Subquery(
        CollectDropdownFeedback.objects
        .filter(emp_id=OuterRef("emp_id"), ym=OuterRef("ym"), feedback_type="hq")
        .order_by("-created_at")
        .values("value")[:1]
    )


def _get_allowed_emp_ids_for_leader(user: CustomUser) -> list[str] | None:
    """
    leader의 팀 스코프에 해당하는 emp_id 목록 반환.
    - SubAdminTemp에서 level/team 확인 → 같은 팀의 CustomUser.id 목록
    - 팀 미설정이면 None 반환 (본인 branch 전체로 fallback)
    """

    sa = SubAdminTemp.objects.filter(user_id=user.id).first()
    if not sa:
        return None

    level = (sa.level or "").strip()
    field_map = {"A레벨": "team_a", "B레벨": "team_b", "C레벨": "team_c"}
    team_field = field_map.get(level)
    if not team_field:
        return None

    my_team_value = (getattr(sa, team_field, "") or "").strip()
    if not my_team_value or my_team_value == "-":
        return None

    # 같은 branch + 같은 팀값의 SubAdminTemp user_id 목록
    team_user_ids = list(
        SubAdminTemp.objects.filter(
            branch=(user.branch or "").strip(),
            **{f"{team_field}__iexact": my_team_value},
        ).values_list("user_id", flat=True)
    )
    return team_user_ids if team_user_ids else [str(user.id)]


def _apply_scope(
    qs: QuerySet[CollectRecord],
    *,
    user: CustomUser | None = None,
    part: str = "",
    bizmoon: str = "",
) -> QuerySet[CollectRecord]:
    """
    부서(part) / 부문(bizmoon) 필터 + 권한 스코프 적용.

    권한 스코프:
    - superuser: part/bizmoon 필터만
    - head: 로그인 사용자의 branch로 고정
    - leader: SubAdminTemp 팀 emp_id 목록으로 필터
      단, 팀 정보가 없으면 기존 동작대로 branch 전체 fallback
    """
    if user is not None:
        grade = getattr(user, "grade", "")
        if grade == "head":
            branch = (getattr(user, "branch", "") or "").strip()
            if branch:
                qs = qs.filter(branch=branch)
        elif grade == "leader":
            allowed_ids = _get_allowed_emp_ids_for_leader(user)
            if allowed_ids is not None:
                qs = qs.filter(emp_id__in=allowed_ids)
            else:
                # 팀 미설정: branch 전체
                branch = (getattr(user, "branch", "") or "").strip()
                if branch:
                    qs = qs.filter(branch=branch)

    if part:
        qs = qs.filter(part=part)
    if bizmoon:
        qs = qs.filter(bizmoon=bizmoon)
    return qs


def _serialize_record(
    r: CollectRecord,
    extra: CollectRow | None = None,
    deposit_data: DepositData | None = None,
) -> CollectRow:
    """
    CollectRecord 인스턴스를 API 응답용 dict로 직렬화한다.
    
    extra:
        탭별 추가 컬럼.
        예: prev_ym, prev_payment, oldest_ym, oldest_payment

    deposit_data:
        DepositSummary 기반 보조 금액.
        값이 없으면 _DEPOSIT_DEFAULTS를 사용해 기존 0 fallback 유지.
    """
    bond_debt, bond_surety = _parse_surety_bond_detail(r.surety_bond_detail)
    _dep = deposit_data or _DEPOSIT_DEFAULTS
    row = {
        "emp_id":          r.emp_id,
        "emp_name":        r.emp_name,
        "part":            r.part,
        "bizmoon":         r.bizmoon,
        "branch":          r.branch,
        "work_status":     r.work_status,
        "final_payment":   r.final_payment,
        "bond_total":      r.surety_bond_total,
        "bond_debt":       bond_debt,
        "bond_surety":     bond_surety,
        "other_total":     _dep["other_total"],  # DepositSummary.other_total (기타합계)
        "refund_expected": _dep["refund_expected"],  # DepositSummary.refund_expected (환수예상)
        "branch_feedback":    getattr(r, "latest_branch_feedback", None) or "",
        "hq_feedback":        getattr(r, "latest_hq_feedback", None) or "",
        "latest_feedback":    getattr(r, "latest_feedback_content", None) or "",
    }
    if extra:
        row.update(extra)
    return row


# =============================================================================
# 공통 조회 헬퍼
# =============================================================================

def get_available_yms() -> list[str]:
    """
    CollectRecord에 존재하는 월도 목록을 최신순으로 반환한다.
    드롭다운 옵션 생성용.
    """
    return list(
        CollectRecord.objects
        .values_list("ym", flat=True)
        .distinct()
        .order_by("-ym")
    )


def get_available_parts() -> list[str]:
    """CollectRecord 기준 부서 목록 (드롭다운용)."""
    return list(
        CollectRecord.objects
        .exclude(part="")
        .values_list("part", flat=True)
        .distinct()
        .order_by("part")
    )


def get_available_bizmoons() -> list[str]:
    """CollectRecord 기준 부문 목록 (드롭다운용)."""
    return list(
        CollectRecord.objects
        .exclude(bizmoon="")
        .values_list("bizmoon", flat=True)
        .distinct()
        .order_by("bizmoon")
    )


# =============================================================================
# 탭별 쿼리 함수
# =============================================================================
def get_collect_all(
    ym: str,
    part: str = "",
    bizmoon: str = "",
    user: CustomUser | None = None,
) -> list[CollectRow]:
    """
    전체 환수 대상 조회.

    조건:
    - 기준 월도 ym
    - final_payment < 0
    - part/bizmoon 및 사용자 권한 스코프 적용
    """
    qs = (
        CollectRecord.objects
        .filter(ym=ym, final_payment__lt=0)
        .annotate(
            latest_feedback_content=_latest_feedback_subquery(),
            latest_branch_feedback=_latest_branch_feedback_subquery(),
            latest_hq_feedback=_latest_hq_feedback_subquery(),
        )
    )
    qs = _apply_scope(qs, user=user, part=part, bizmoon=bizmoon)
    records = list(qs.order_by("part", "branch", "emp_id"))
    deposit_map = _build_deposit_map([r.emp_id for r in records])
    return [
        _serialize_record(r, deposit_data=deposit_map.get(r.emp_id))
        for r in records
    ]


def get_collect_new(
    ym: str,
    part: str = "",
    bizmoon: str = "",
    user: CustomUser | None = None,
) -> list[CollectRow]:
    """
    신규 환수 대상 조회.

    조건:
    - 당월 final_payment < 0
    - 전월 final_payment >= 0
    """
    prev_ym = offset_ym(ym, -1)

    curr_neg: set[str] = set(
        CollectRecord.objects
        .filter(ym=ym, final_payment__lt=0)
        .values_list("emp_id", flat=True)
    )
    if not curr_neg:
        return []

    prev_ok: set[str] = set(
        CollectRecord.objects
        .filter(ym=prev_ym, emp_id__in=curr_neg, final_payment__gte=0)
        .values_list("emp_id", flat=True)
    )
    target_ids = curr_neg & prev_ok
    if not target_ids:
        return []

    curr_qs = (
        CollectRecord.objects
        .filter(ym=ym, emp_id__in=target_ids)
        .annotate(
            latest_feedback_content=_latest_feedback_subquery(),
            latest_branch_feedback=_latest_branch_feedback_subquery(),
            latest_hq_feedback=_latest_hq_feedback_subquery(),
        )
    )
    curr_qs = _apply_scope(curr_qs, user=user, part=part, bizmoon=bizmoon)

    prev_map: dict[str, int] = dict(
        CollectRecord.objects
        .filter(ym=prev_ym, emp_id__in=target_ids)
        .values_list("emp_id", "final_payment")
    )

    records = list(curr_qs.order_by("part", "branch", "emp_id"))
    deposit_map = _build_deposit_map([r.emp_id for r in records])

    rows = []
    for r in records:
        rows.append(_serialize_record(r, extra={
            "prev_ym":      prev_ym,
            "prev_payment": prev_map.get(r.emp_id, 0),
        }, deposit_data=deposit_map.get(r.emp_id)))
    return rows


def get_collect_long(
    ym: str,
    months: int,
    part: str = "",
    bizmoon: str = "",
    user: CustomUser | None = None,
) -> list[CollectRow]:
    """
    장기 환수 대상 조회.

    조건:
    - months는 3, 6, 12만 허용
    - 기준 월도부터 months개월 연속 final_payment < 0
    """
    if months not in (3, 6, 12):
        raise ValueError(f"months는 3, 6, 12 중 하나여야 합니다. 입력값: {months}")

    ym_range = [offset_ym(ym, -i) for i in range(months)]
    oldest_ym = ym_range[-1]

    sets: list[set[str]] = [
        set(
            CollectRecord.objects
            .filter(ym=m, final_payment__lt=0)
            .values_list("emp_id", flat=True)
        )
        for m in ym_range
    ]

    target_ids = set.intersection(*sets) if sets else set()
    if not target_ids:
        return []

    curr_qs = (
        CollectRecord.objects
        .filter(ym=ym, emp_id__in=target_ids)
        .annotate(
            latest_feedback_content=_latest_feedback_subquery(),
            latest_branch_feedback=_latest_branch_feedback_subquery(),
            latest_hq_feedback=_latest_hq_feedback_subquery(),
        )
    )
    curr_qs = _apply_scope(curr_qs, user=user, part=part, bizmoon=bizmoon)

    oldest_map: dict[str, int] = dict(
        CollectRecord.objects
        .filter(ym=oldest_ym, emp_id__in=target_ids)
        .values_list("emp_id", "final_payment")
    )

    records = list(curr_qs.order_by("part", "branch", "emp_id"))
    deposit_map = _build_deposit_map([r.emp_id for r in records])

    rows = []
    for r in records:
        rows.append(_serialize_record(r, extra={
            "oldest_ym":      oldest_ym,
            "oldest_payment": oldest_map.get(r.emp_id, 0),
        }, deposit_data=deposit_map.get(r.emp_id)))
    return rows


def get_collect_list(
    ym: str,
    tab: str,
    part: str = "",
    bizmoon: str = "",
    user: CustomUser | None = None,
) -> list[CollectRow]:
    """
    탭 키(tab)에 따라 해당 서비스 함수를 호출하는 dispatcher.
    API 뷰에서 단일 진입점으로 사용한다.

    tab:
        all | new | long3 | long6 | long12
    """
    if tab == "all":
        return get_collect_all(ym, part=part, bizmoon=bizmoon, user=user)
    elif tab == "new":
        return get_collect_new(ym, part=part, bizmoon=bizmoon, user=user)
    elif tab == "long3":
        return get_collect_long(ym, months=3, part=part, bizmoon=bizmoon, user=user)
    elif tab == "long6":
        return get_collect_long(ym, months=6, part=part, bizmoon=bizmoon, user=user)
    elif tab == "long12":
        return get_collect_long(ym, months=12, part=part, bizmoon=bizmoon, user=user)
    else:
        raise ValueError(f"알 수 없는 탭입니다: {tab!r}")


# =============================================================================
# 피드백 CRUD 서비스
# =============================================================================

def get_feedbacks(emp_id: str) -> list[CollectRow]:
    """
    특정 사번의 피드백 전체 목록을 최신순으로 반환한다.
    author 정보(id, name)를 select_related로 포함한다.

    반환 필드:
        id / emp_id / author_id / author_name
        / content / created_at / updated_at / is_modified
    """
    qs = (
        CollectFeedback.objects
        .filter(emp_id=emp_id)
        .select_related("author")
        .order_by("-created_at")
    )

    result = []
    for fb in qs:
        # is_modified: created_at과 updated_at 차이가 1초 이상이면 수정됨
        is_modified = abs((fb.updated_at - fb.created_at).total_seconds()) > 1
        result.append({
            "id":          fb.id,
            "emp_id":      fb.emp_id,
            "author_id":   fb.author_id,
            "author_name": fb.author.name,
            "content":     fb.content,
            "date_input":  fb.date_input.strftime("%Y-%m-%d") if fb.date_input else "",
            "department":  fb.department or "",
            "manager":     fb.manager    or "",
            "created_at":  fb.created_at.strftime("%Y-%m-%d %H:%M"),
            "updated_at":  fb.updated_at.strftime("%Y-%m-%d %H:%M") if is_modified else "",
            "is_modified": is_modified,
        })
    return result


@transaction.atomic
def create_feedback(
    author: CustomUser,
    emp_id: str,
    content: str,
    date_input: date | None = None,
    department: str = "",
    manager: str = "",
) -> CollectFeedback:
    """
    피드백을 생성한다.

    [검증]
    - content 빈 값 → ValueError
    - emp_id 빈 값 → ValueError
    (CollectRecord에 없는 사번도 피드백 입력 가능 — FK 없음)
    """
    emp_id = emp_id.strip()
    content = content.strip()

    if not emp_id:
        raise ValueError("대상자 사번을 입력해주세요.")
    if not content:
        raise ValueError("피드백 내용을 입력해주세요.")

    fb = CollectFeedback.objects.create(
        emp_id=emp_id,
        author=author,
        content=content,
        date_input=date_input,
        department=department.strip() if department else "",
        manager=manager.strip()    if manager    else "",
    )
    logger.info(
        "[collect] feedback created: id=%s, author=%s, emp_id=%s",
        fb.id, author.id, emp_id,
    )
    return fb


@transaction.atomic
def update_feedback(
    feedback_id: int,
    author: CustomUser,
    content: str,
) -> Optional[CollectFeedback]:
    """
    피드백을 수정한다. 본인(author)만 가능.

    [권한 판정 — 서버 최종]
    - feedback.author_id != author.id → None 반환 (뷰에서 403 처리)

    반환:
        CollectFeedback — 성공
        None            — 권한 없음 또는 존재하지 않음
    """
    content = content.strip()
    if not content:
        raise ValueError("피드백 내용을 입력해주세요.")

    try:
        fb = (
            CollectFeedback.objects
            .select_for_update()
            .get(id=feedback_id)
        )
    except CollectFeedback.DoesNotExist:
        return None

    # 서버 권한 최종 판정
    if fb.author_id != author.id:
        logger.warning(
            "[collect] unauthorized update: feedback_id=%s, requester=%s, real_author=%s",
            feedback_id, author.id, fb.author_id,
        )
        return None

    fb.content = content
    fb.save(update_fields=["content", "updated_at"])
    logger.info(
        "[collect] feedback updated: id=%s, author=%s", fb.id, author.id
    )
    return fb


@transaction.atomic
def delete_feedback(
    feedback_id: int,
    author: CustomUser,
) -> bool:
    """
    피드백을 삭제한다. 본인(author)만 가능.

    [권한 판정 — 서버 최종]
    - feedback.author_id != author.id → False 반환 (뷰에서 403 처리)

    반환:
        True  — 정상 삭제
        False — 권한 없음 또는 존재하지 않음
    """
    try:
        fb = (
            CollectFeedback.objects
            .select_for_update()
            .get(id=feedback_id)
        )
    except CollectFeedback.DoesNotExist:
        return False

    # 서버 권한 최종 판정
    if fb.author_id != author.id:
        logger.warning(
            "[collect] unauthorized delete: feedback_id=%s, requester=%s, real_author=%s",
            feedback_id, author.id, fb.author_id,
        )
        return False

    fb.delete()
    logger.info(
        "[collect] feedback deleted: id=%s, author=%s", feedback_id, author.id
    )
    return True


# =============================================================================
# 드랍다운 피드백 서비스
# =============================================================================

@transaction.atomic
def save_dropdown_feedback(
    author: CustomUser,
    emp_id: str,
    ym: str,
    feedback_type: str,
    value: str,
) -> CollectDropdownFeedback:
    """
    드랍다운 피드백 저장 (이력 누적).

    [검증]
    - feedback_type: 'branch' | 'hq'
    - value: 빈 문자열 허용 ('선택' 상태 기록)
    - 권한 검증은 뷰에서 수행 후 호출
    """
    emp_id        = emp_id.strip()
    ym            = ym.strip()
    feedback_type = feedback_type.strip()
    value         = value.strip()

    if not emp_id:
        raise ValueError("대상자 사번을 입력해주세요.")
    if not ym or len(ym) != 6 or not ym.isdigit():
        raise ValueError("월도 형식이 올바르지 않습니다. (YYYYMM)")
    if feedback_type not in ("branch", "hq"):
        raise ValueError("피드백 구분이 올바르지 않습니다.")

    fb = CollectDropdownFeedback.objects.create(
        emp_id=emp_id,
        ym=ym,
        feedback_type=feedback_type,
        value=value,
        author=author,
    )
    logger.info(
        "[collect] dropdown feedback saved: id=%s type=%s emp_id=%s ym=%s value=%s",
        fb.id, feedback_type, emp_id, ym, value,
    )
    return fb


# =============================================================================
# 업로드 이력
# =============================================================================


def get_last_collect_upload_log() -> CollectUploadLog | None:
    """
    가장 최근 CollectUploadLog 단건 반환.

    collect_home 페이지의 최근 업로드 현황 표시에 사용한다.
    """
    return CollectUploadLog.objects.first()