# django_ma/commission/upload_handlers/approval.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from accounts.models import CustomUser
from commission.models import ApprovalPending
from commission.upload_handlers._common import safe_cell_text, upload_result
from commission.upload_utils import _norm_emp_id, _read_excel_raw_matrix, _to_int

# =============================================================================
# ApprovalPending Upload (kind=approval)
# =============================================================================

@dataclass(frozen=True)
class _ApprovalRowSpec:
    """
    수수료결재 raw matrix 기반 컬럼 인덱스(0-based).

    원본 엑셀 구조가 고정된 파일이므로 컬럼명 탐지 대신 위치 기반으로 읽는다.
    위치 정책을 이 dataclass에 모아두어 magic number가 핸들러 본문에 퍼지지 않게 한다.
    """
    idx_emp_name: int = 1   # B
    idx_user_id: int = 2    # C
    idx_pay: int = 13       # N
    idx_flag: int = 14      # O


_SPEC = _ApprovalRowSpec()

# ✅ 유자격 조건(DB)
_ELIGIBLE_REGIST = {"손생등록", "생보등록", "손보등록"}


# ✅ 코랩 기준: 실지급액 10,000원 이상만 미결재 대상으로 저장
APPROVAL_PENDING_MIN_ACTUAL_PAY = 10_000


def _new_excluded_summary() -> Dict[str, int]:
    return {
        "user_not_found": 0,
        "part_mismatch": 0,
        "regist_invalid": 0,
        "amount_below_min": 0,
    }


def _append_excluded(
    rows: List[dict],
    summary: Dict[str, int],
    *,
    user_id: str,
    emp_name: str,
    actual_pay: int,
    reason_code: str,
    reason: str,
    user_part: str = "",
    selected_part: str = "",
    user_regist: str = "",
) -> None:
    """
    업로드 대상에서 제외된 raw 후보를 사유별로 누적한다.

    저장 모델은 변경하지 않고, 업로드 결과 fail-token Excel로만 제공한다.
    """
    summary[reason_code] = int(summary.get(reason_code) or 0) + 1
    rows.append(
        {
            "user_id": user_id,
            "emp_name": emp_name,
            "actual_pay": actual_pay,
            "reason_code": reason_code,
            "reason": reason,
            "selected_part": selected_part,
            "user_part": user_part,
            "user_regist": user_regist,
        }
    )


def _safe_cell(row: Sequence[object], idx: int) -> str:
    """
    raw matrix row에서 cell을 안전하게 문자열로 변환한다.

    - None / NaN / "none" / "nan" / "-" -> ""
    - 실제 공란 판정은 upload_handlers._common.safe_cell_text()를 경유한다.
    - 이 wrapper는 approval 파일의 위치 기반 접근(len 방어)을 담당한다.
    """
    if len(row) <= idx:
        return ""
    return safe_cell_text(row[idx])


def handle_upload_commission_approval(
    file_path: str,
    original_name: str,
    ym: str,
    part: str = "",
) -> Dict[str, object]:
    """
    수수료결재(kind=approval) 업로드

    조건:
    - N열(실지급액) >= 10,000
    - O열(결재값) == 'N'
    - ✅ 유자격(DB): user.regist in ['손생등록','생보등록','손보등록']
    - 동일 사번이 여러 행이면 실지급액 합산

    part:
    - 주어지면 해당 part 사용자만 저장(스코프 안전장치)

    return contract:
    - inserted_or_updated: 저장/upsert 건수
    - missing_users: 사용자 미존재 건수(레거시 호환)
    - missing_sample: 실패 샘플 최대 10건
    - excluded_rows: 제외 사유별 상세 row
    - excluded_summary: 제외 사유별 건수
    """
    df = _read_excel_raw_matrix(file_path, original_name=original_name, skiprows=0, header_none=True)
    if df is None or getattr(df, "empty", False):
        return upload_result()

    # uid -> {emp_name:str, paid_sum:int}
    bucket: Dict[str, Dict[str, object]] = {}

    for _, row in df.iterrows():
        raw_uid = _safe_cell(row, _SPEC.idx_user_id)
        uid = _norm_emp_id(raw_uid)
        if not uid or not uid.isdigit():
            continue

        pay = _to_int(_safe_cell(row, _SPEC.idx_pay), default=0)
        flag = _safe_cell(row, _SPEC.idx_flag).strip().upper()

        if pay <= 0 or flag != "N":
            continue

        emp_name = _safe_cell(row, _SPEC.idx_emp_name)

        rec = bucket.get(uid)
        if rec is None:
            bucket[uid] = {"emp_name": emp_name, "paid_sum": pay}
        else:
            # emp_name이 비어있던 경우만 채움
            if emp_name and not rec.get("emp_name"):
                rec["emp_name"] = emp_name
            rec["paid_sum"] = int(rec.get("paid_sum") or 0) + pay

    if not bucket:
        return upload_result()

    # ✅ DB(CustomUser)를 SSOT로 삼아 미매칭/부서불일치/유자격불일치/금액미달을 분리한다.
    user_map = CustomUser.objects.filter(pk__in=bucket.keys()).in_bulk()
    excluded_rows: List[dict] = []
    excluded_summary = _new_excluded_summary()
    missing: List[str] = []

    objs: List[ApprovalPending] = []
    for uid, rec in bucket.items():
        emp_name = str(rec.get("emp_name") or "")
        paid_sum = int(rec.get("paid_sum") or 0)

        if paid_sum < APPROVAL_PENDING_MIN_ACTUAL_PAY:
            _append_excluded(
                excluded_rows,
                excluded_summary,
                user_id=uid,
                emp_name=emp_name,
                actual_pay=paid_sum,
                reason_code="amount_below_min",
                reason="실지급액 10,000원 미만",
                selected_part=part,
            )
            continue

        u = user_map.get(uid)
        if not u:
            missing.append(uid)
            _append_excluded(
                excluded_rows,
                excluded_summary,
                user_id=uid,
                emp_name=emp_name,
                actual_pay=paid_sum,
                reason_code="user_not_found",
                reason="CustomUser 미매칭",
                selected_part=part,
            )
            continue

        user_part = str(getattr(u, "part", "") or "")
        user_regist = str(getattr(u, "regist", "") or "")

        if part and user_part != part:
            _append_excluded(
                excluded_rows,
                excluded_summary,
                user_id=uid,
                emp_name=emp_name,
                actual_pay=paid_sum,
                reason_code="part_mismatch",
                reason="선택 부서와 CustomUser.part 불일치",
                user_part=user_part,
                selected_part=part,
                user_regist=user_regist,
            )
            continue

        if user_regist not in _ELIGIBLE_REGIST:
            _append_excluded(
                excluded_rows,
                excluded_summary,
                user_id=uid,
                emp_name=emp_name,
                actual_pay=paid_sum,
                reason_code="regist_invalid",
                reason="CustomUser.regist 유자격 조건 불일치",
                user_part=user_part,
                selected_part=part,
                user_regist=user_regist,
            )

            continue

        objs.append(
            ApprovalPending(
                ym=ym,
                user=u,
                emp_name=emp_name,
                actual_pay=paid_sum,
                approval_flag="N",
            )
        )

    missing_sample = missing[:10]

    if not objs:
        return upload_result(
            missing_users=len(missing),
            missing_sample=missing_sample,
            excluded_rows=excluded_rows,
            excluded_summary=excluded_summary,
        )

    ApprovalPending.objects.bulk_create(
        objs,
        batch_size=1000,
        update_conflicts=True,
        unique_fields=["ym", "user"],
        update_fields=["emp_name", "actual_pay", "approval_flag", "updated_at"],
    )

    return upload_result(
        inserted_or_updated=len(objs),
        missing_users=len(missing),
        missing_sample=missing_sample,
        excluded_rows=excluded_rows,
        excluded_summary=excluded_summary,
    )


# ---------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------
_handle_upload_commission_approval = handle_upload_commission_approval