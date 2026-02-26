# django_ma/commission/upload_handlers/efficiency.py
from __future__ import annotations

from accounts.models import CustomUser
from commission.models import EfficiencyPayExcess
from commission.upload_utils import _norm_emp_id, _read_excel_raw_matrix, _to_int

# =============================================================================
# EfficiencyPayExcess Upload (kind=efficiency)
# =============================================================================

def _find_header_row_and_col_indices(df_raw):
    """
    raw matrix(header=None)에서
    - 헤더 행(구분/금액 키워드 포함)을 찾아
    - 구분열/금액열 index를 리턴한다.

    탐색 범위:
    - 상단 0~5행(최대 6행)만 검사(파일 편차 대응)
    """
    def _norm(x):
        s = "" if x is None else str(x).strip()
        return s.replace(" ", "")

    for r in range(min(6, len(df_raw.index))):
        row = df_raw.iloc[r].tolist()
        normed = [_norm(c) for c in row]

        has_div = any("구분" in c for c in normed)
        has_amt = any(("금액" in c) or ("지급액" in c) for c in normed)
        if not (has_div and has_amt):
            continue

        div_idx = None
        amt_idx = None
        for i, c in enumerate(normed):
            if div_idx is None and "구분" in c:
                div_idx = i
            if amt_idx is None and (("금액" in c) or ("지급액" in c)):
                amt_idx = i

        if div_idx is not None and amt_idx is not None:
            return r, div_idx, amt_idx

    return None, None, None


def handle_upload_efficiency_pay_excess(
    file_path: str,
    original_name: str,
    ym: str,
    part: str = "",
):
    """
    지점효율(kind=efficiency) 업로드

    - 사번: 사원번호(E열)
    - 지급금액합계: 구분 == '지급' 인 금액 합계
    - 저장: EfficiencyPayExcess(ym+user unique)
    - part가 있으면 해당 part 사용자만 저장(스코프 안전장치)
    """
    df = _read_excel_raw_matrix(file_path, original_name=original_name, skiprows=0, header_none=True)

    IDX_E = 4  # 사원번호(E열)

    header_row, div_idx, amt_idx = _find_header_row_and_col_indices(df)
    if header_row is None:
        raise ValueError("엑셀에서 '구분'/'금액' 헤더를 찾지 못했습니다. (지점효율 파일 형식을 확인해주세요)")

    # uid -> 지급 합계
    bucket = {}

    for r in range(header_row + 1, len(df.index)):
        row = df.iloc[r]

        if len(row) <= max(IDX_E, div_idx, amt_idx):
            continue

        uid = _norm_emp_id(row[IDX_E])
        if not uid or not uid.isdigit():
            continue

        div_val = ("" if row[div_idx] is None else str(row[div_idx])).strip()
        if div_val.lower() in ("nan", "none"):
            div_val = ""

        if div_val != "지급":
            continue

        amt = _to_int(row[amt_idx], default=0)
        if amt == 0:
            continue

        bucket[uid] = bucket.get(uid, 0) + amt

    if not bucket:
        return {"inserted_or_updated": 0, "missing_users": 0, "missing_sample": []}

    qs = CustomUser.objects.filter(pk__in=bucket.keys())
    if part:
        qs = qs.filter(part=part)
    user_map = qs.in_bulk()

    missing = [uid for uid in bucket.keys() if uid not in user_map]
    missing_sample = missing[:10]

    objs = []
    for uid, s in bucket.items():
        u = user_map.get(uid)
        if not u:
            continue
        objs.append(
            EfficiencyPayExcess(
                ym=ym,
                user=u,
                pay_amount_sum=int(s or 0),
            )
        )

    EfficiencyPayExcess.objects.bulk_create(
        objs,
        batch_size=1000,
        update_conflicts=True,
        unique_fields=["ym", "user"],
        update_fields=["pay_amount_sum", "updated_at"],
    )

    return {
        "inserted_or_updated": len(objs),
        "missing_users": len(missing),
        "missing_sample": missing_sample,
    }


# ---------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------
_handle_upload_efficiency_pay_excess = handle_upload_efficiency_pay_excess