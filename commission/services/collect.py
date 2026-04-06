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
from typing import Optional

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import OuterRef, Subquery

from accounts.models import CustomUser
from commission.models import CollectFeedback, CollectRecord

logger = logging.getLogger(__name__)


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


def _apply_scope(qs, part: str = "", bizmoon: str = ""):
    """
    부서(part) / 부문(bizmoon) 필터를 CollectRecord QS에 적용한다.
    빈 문자열이면 해당 필터를 건너뛴다 (전체 조회).
    """
    if part:
        qs = qs.filter(part=part)
    if bizmoon:
        qs = qs.filter(bizmoon=bizmoon)
    return qs


def _serialize_record(r: CollectRecord, extra: dict | None = None) -> dict:
    """
    CollectRecord 인스턴스를 API 응답용 dict로 직렬화한다.
    extra: 탭별 추가 컬럼 (prev_payment, oldest_payment 등)
    """
    row = {
        "emp_id":          r.emp_id,
        "emp_name":        r.emp_name,
        "part":            r.part,
        "bizmoon":         r.bizmoon,
        "branch":          r.branch,
        "work_status":     r.work_status,
        "final_payment":   r.final_payment,
        # annotate된 최신 피드백 (없으면 빈 문자열)
        "latest_feedback": getattr(r, "latest_feedback_content", None) or "",
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
) -> list[dict]:
    """
    [전체 탭] 해당 월도에서 final_payment < 0 인 전체 환수 대상자 조회.

    반환 컬럼:
        emp_id / emp_name / part / bizmoon / branch / work_status
        / final_payment(당월) / latest_feedback
    """
    qs = (
        CollectRecord.objects
        .filter(ym=ym, final_payment__lt=0)
        .annotate(latest_feedback_content=_latest_feedback_subquery())
    )
    qs = _apply_scope(qs, part=part, bizmoon=bizmoon)
    return [
        _serialize_record(r)
        for r in qs.order_by("part", "branch", "emp_id")
    ]


def get_collect_new(
    ym: str,
    part: str = "",
    bizmoon: str = "",
) -> list[dict]:
    """
    [신규 탭] 당월 final_payment < 0 AND 전월 final_payment >= 0 인 신규 환수 대상자.

    조건:
    - 당월 < 0 (이번 달 환수 발생)
    - 전월 >= 0 (전월은 정상 지급)
    - 전월 이력이 없으면 제외 (신규 입사 등 판단 불가)

    반환 추가 컬럼: prev_ym / prev_payment
    """
    prev_ym = offset_ym(ym, -1)

    # 당월 환수 대상자 emp_id 집합
    curr_neg: set[str] = set(
        CollectRecord.objects
        .filter(ym=ym, final_payment__lt=0)
        .values_list("emp_id", flat=True)
    )
    if not curr_neg:
        return []

    # 전월 정상 지급자 중 당월 환수 대상자와 교집합
    prev_ok: set[str] = set(
        CollectRecord.objects
        .filter(ym=prev_ym, emp_id__in=curr_neg, final_payment__gte=0)
        .values_list("emp_id", flat=True)
    )
    target_ids = curr_neg & prev_ok
    if not target_ids:
        return []

    # 당월 QS (스코프 필터 적용)
    curr_qs = (
        CollectRecord.objects
        .filter(ym=ym, emp_id__in=target_ids)
        .annotate(latest_feedback_content=_latest_feedback_subquery())
    )
    curr_qs = _apply_scope(curr_qs, part=part, bizmoon=bizmoon)

    # 전월 금액 딕셔너리 {emp_id: final_payment}
    prev_map: dict[str, int] = dict(
        CollectRecord.objects
        .filter(ym=prev_ym, emp_id__in=target_ids)
        .values_list("emp_id", "final_payment")
    )

    rows = []
    for r in curr_qs.order_by("part", "branch", "emp_id"):
        rows.append(_serialize_record(r, extra={
            "prev_ym":      prev_ym,
            "prev_payment": prev_map.get(r.emp_id, 0),
        }))
    return rows


def get_collect_long(
    ym: str,
    months: int,
    part: str = "",
    bizmoon: str = "",
) -> list[dict]:
    """
    [장기 탭] base_ym 포함 직전 months개월 모두 final_payment < 0 인 장기 환수 대상자.

    months: 3 / 6 / 12 중 하나.

    [쿼리 전략]
    1. 직전 months개월의 ym 목록 생성
    2. 각 월도별 final_payment < 0 인 emp_id 집합 구성
    3. 교집합 (모든 월도에서 음수인 emp_id)
    4. 당월 + oldest_ym QS 조회

    [이력 부족 처리]
    테이블 생성 초기에는 이력이 부족하므로 빈 결과를 반환한다. 정상 동작.

    반환 추가 컬럼: oldest_ym / oldest_payment
    """
    if months not in (3, 6, 12):
        raise ValueError(f"months는 3, 6, 12 중 하나여야 합니다. 입력값: {months}")

    # 대상 월도 목록: base_ym 포함 역순 months개
    # 예) ym="202603", months=3 → ["202603", "202602", "202601"]
    ym_range = [offset_ym(ym, -i) for i in range(months)]
    oldest_ym = ym_range[-1]   # (months-1)개월 전

    # 각 월도별 final_payment < 0 인 emp_id 집합
    sets: list[set[str]] = [
        set(
            CollectRecord.objects
            .filter(ym=m, final_payment__lt=0)
            .values_list("emp_id", flat=True)
        )
        for m in ym_range
    ]

    # 모든 월도에서 음수인 emp_id (교집합)
    target_ids = set.intersection(*sets) if sets else set()
    if not target_ids:
        return []

    # 당월 QS (스코프 필터 적용)
    curr_qs = (
        CollectRecord.objects
        .filter(ym=ym, emp_id__in=target_ids)
        .annotate(latest_feedback_content=_latest_feedback_subquery())
    )
    curr_qs = _apply_scope(curr_qs, part=part, bizmoon=bizmoon)

    # oldest_ym 금액 딕셔너리 {emp_id: final_payment}
    oldest_map: dict[str, int] = dict(
        CollectRecord.objects
        .filter(ym=oldest_ym, emp_id__in=target_ids)
        .values_list("emp_id", "final_payment")
    )

    rows = []
    for r in curr_qs.order_by("part", "branch", "emp_id"):
        rows.append(_serialize_record(r, extra={
            "oldest_ym":      oldest_ym,
            "oldest_payment": oldest_map.get(r.emp_id, 0),
        }))
    return rows


def get_collect_list(
    ym: str,
    tab: str,
    part: str = "",
    bizmoon: str = "",
) -> list[dict]:
    """
    탭 키(tab)에 따라 해당 서비스 함수를 호출하는 dispatcher.
    API 뷰에서 단일 진입점으로 사용한다.
    """
    if tab == "all":
        return get_collect_all(ym, part=part, bizmoon=bizmoon)
    elif tab == "new":
        return get_collect_new(ym, part=part, bizmoon=bizmoon)
    elif tab == "long3":
        return get_collect_long(ym, months=3, part=part, bizmoon=bizmoon)
    elif tab == "long6":
        return get_collect_long(ym, months=6, part=part, bizmoon=bizmoon)
    elif tab == "long12":
        return get_collect_long(ym, months=12, part=part, bizmoon=bizmoon)
    else:
        raise ValueError(f"알 수 없는 탭입니다: {tab!r}")


# =============================================================================
# 피드백 CRUD 서비스
# =============================================================================

def get_feedbacks(emp_id: str) -> list[dict]:
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