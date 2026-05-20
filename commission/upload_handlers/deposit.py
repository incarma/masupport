# django_ma/commission/upload_handlers/deposit.py
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Sequence, Tuple

from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone

from commission.models import DepositOther, DepositSummary, DepositSurety, DepositUploadLog
from commission.upload_utils import (
    DEC2,
    _bulk_existing_user_ids,
    _detect_col,
    _detect_emp_id_col,
    _detect_refundpay_col,
    _extract_emp7_from_a,
    _find_exact_or_space_removed,
    _norm_emp_id,
    _read_excel_raw_matrix,
    _safe_decimal_q2,
    _to_date,
    _to_decimal,
    _to_div,
    _to_int,
)

# =============================================================================
# Internal helpers (SSOT within this module)
# =============================================================================

def _existing_ids(ids: Sequence[str]) -> Tuple[set, List[str]]:
    """
    CustomUser 존재하는 ID를 bulk 조회한다.

    row별 exists() 호출을 피하기 위한 성능 SSOT다.

    반환:
    - existing_set
    - missing_sample(최대 10개)
    """
    existing = _bulk_existing_user_ids(ids)
    missing_sample = [x for x in ids if x not in existing][:10]
    return set(existing), missing_sample


def _update_summary(uid: str, defaults: Dict):
    """
    DepositSummary(user_id=uid) upsert.

    Deposit 계열 handler는 이 helper를 통해 요약 테이블만 갱신한다.
    """
    DepositSummary.objects.update_or_create(user_id=uid, defaults=defaults)


# =============================================================================
# DepositSummary upload handlers (DataFrame)
# =============================================================================

def handle_upload_final_payment(df):
    """
    최종지급액 업로드
    - user_id + final_payment(최종지급액)
    """
    col_user = _detect_emp_id_col(df) or _detect_col(df, must_include=("사번",), any_include=())
    col_payment = _detect_col(df, must_include=("최종", "지급"), any_include=("금액",))
    if not col_user or not col_payment:
        raise ValueError("엑셀 컬럼을 찾지 못했습니다. (필수: 사번, 최종지급액)")

    df2 = df[[col_user, col_payment]].copy()
    df2.columns = ["user_id", "final_payment"]

    df2["user_id"] = df2["user_id"].apply(_norm_emp_id)
    df2 = df2[df2["user_id"].astype(str).str.len() > 0].copy()
    df2["final_payment"] = df2["final_payment"].apply(_to_int)

    ids = df2["user_id"].tolist()
    existing_ids, missing_sample = _existing_ids(ids)

    updated = 0
    missing_users = 0

    for r in df2.itertuples(index=False):
        uid = r.user_id
        if uid not in existing_ids:
            missing_users += 1
            continue
        _update_summary(uid, {"final_payment": int(r.final_payment or 0)})
        updated += 1

    return {
        "updated": updated,
        "missing_users": missing_users,
        "existing_users": len(existing_ids),
        "missing_sample": missing_sample,
    }


def handle_upload_refund_pay_expected(df):
    """
    환수/지급예상 업로드
    - 일반/보증(O)/보증(X) 환수/지급 손/생/합계 필드들을 DepositSummary에 반영
    """
    col_user = _detect_emp_id_col(df)
    if not col_user:
        raise ValueError("엑셀에서 사번 컬럼을 찾지 못했습니다. (사번/사원코드/등록번호/FC코드 등)")

    targets = {
        # 일반
        "refund_ns": (None, "refund", "ns"),
        "refund_ls": (None, "refund", "ls"),
        "refund_expected": (None, "refund", "total"),
        "pay_ns": (None, "pay", "ns"),
        "pay_ls": (None, "pay", "ls"),
        "pay_expected": (None, "pay", "total"),
        # 보증(O)
        "surety_o_refund_ns": ("o", "refund", "ns"),
        "surety_o_refund_ls": ("o", "refund", "ls"),
        "surety_o_refund_total": ("o", "refund", "total"),
        "surety_o_pay_ns": ("o", "pay", "ns"),
        "surety_o_pay_ls": ("o", "pay", "ls"),
        "surety_o_pay_total": ("o", "pay", "total"),
        # 보증(X)
        "surety_x_refund_ns": ("x", "refund", "ns"),
        "surety_x_refund_ls": ("x", "refund", "ls"),
        "surety_x_refund_total": ("x", "refund", "total"),
        "surety_x_pay_ns": ("x", "pay", "ns"),
        "surety_x_pay_ls": ("x", "pay", "ls"),
        "surety_x_pay_total": ("x", "pay", "total"),
    }

    found_cols: Dict[str, str] = {}
    missing = []
    for field, (flag, kind, line) in targets.items():
        col = _detect_refundpay_col(df, flag, kind, line)
        if not col:
            missing.append((field, flag, kind, line))
        else:
            found_cols[field] = col

    if missing:
        pretty = []
        for field, flag, kind, line in missing[:20]:
            sflag = "보증(O)" if flag == "o" else ("보증(X)" if flag == "x" else "일반")
            skind = "환수" if kind == "refund" else "지급"
            sline = "손보" if line == "ns" else ("생보" if line == "ls" else "합계")
            pretty.append(f"- {sflag} {skind} {sline} (필드: {field})")
        raise ValueError("엑셀 컬럼 매칭 실패:\n" + "\n".join(pretty))

    use_cols = [col_user] + list(found_cols.values())
    df2 = df[use_cols].copy()

    rename_map = {col_user: "user_id"}
    for field, col in found_cols.items():
        rename_map[col] = field
    df2.rename(columns=rename_map, inplace=True)

    df2["user_id"] = df2["user_id"].apply(_norm_emp_id)
    df2 = df2[df2["user_id"].astype(str).str.len() > 0].copy()

    for field in targets.keys():
        df2[field] = df2[field].apply(_to_int)

    ids = df2["user_id"].tolist()
    existing_ids, missing_sample = _existing_ids(ids)

    updated = 0
    missing_users = 0

    for r in df2.itertuples(index=False):
        uid = r.user_id
        if uid not in existing_ids:
            missing_users += 1
            continue

        defaults = {f: int(getattr(r, f, 0) or 0) for f in targets.keys()}
        _update_summary(uid, defaults)
        updated += 1

    return {
        "updated": updated,
        "missing_users": missing_users,
        "existing_users": len(existing_ids),
        "missing_sample": missing_sample,
        "matched_columns": {k: str(v) for k, v in found_cols.items()},
    }


# =============================================================================
# DepositSummary upload handlers (채권지표 / 보증증액 공용)
# =============================================================================

_DEPOSIT_METRICS_COL_MAP = {
    "3개월 장기 총수수료(지급월+직전2개월)": "comm_3m",
    "6개월 장기 총수수료(지급월+직전5개월)": "comm_6m",
    "9개월 장기 총수수료(지급월+직전8개월)": "comm_9m",
    "12개월 장기 총수수료(지급월+직전11개월)": "comm_12m",
    "당월 계속분 인정": "inst_current",
    "전월 계속분 인정": "inst_prev",
    "장기 총실적": "sales_total",
    "손생보 합산 통산유지율": "maint_total",
    "보증/채권 합계": "debt_total",
    "1개월전 분급여부": "div_1m",
    "2개월전 분급여부": "div_2m",
    "3개월전 분급여부": "div_3m",
    "최종 초과금액": "final_excess_amount",
}


def handle_upload_deposit_metrics(df):
    """
    채권지표 업로드 (사번 기준 주요 지표 업데이트)
    - 엑셀 컬럼(요청표) → DepositSummary 필드 업데이트
    - 기존 '보증증액'에서 쓰던 컬럼 매핑을 그대로 사용(호환)
    """
    col_user = (
        _detect_col(df, must_include=("사원", "코드"), any_include=())
        or _detect_col(df, must_include=("사번",), any_include=())
        or _detect_emp_id_col(df)
    )
    if not col_user:
        raise ValueError("엑셀 컬럼을 찾지 못했습니다. (필수: 사원코드/사번)")

    detected: Dict[str, str] = {}
    for excel_col in _DEPOSIT_METRICS_COL_MAP.keys():
        found = _find_exact_or_space_removed(df.columns, excel_col)
        if found is None:
            raise ValueError(f"엑셀 컬럼을 찾지 못했습니다: [{excel_col}]")
        detected[excel_col] = found

    use_cols = [col_user] + [detected[k] for k in _DEPOSIT_METRICS_COL_MAP.keys()]
    df2 = df[use_cols].copy()

    rename_map = {col_user: "user_id"}
    for excel_col, model_field in _DEPOSIT_METRICS_COL_MAP.items():
        rename_map[detected[excel_col]] = model_field
    df2.rename(columns=rename_map, inplace=True)

    df2["user_id"] = df2["user_id"].apply(_norm_emp_id)
    df2 = df2[df2["user_id"].astype(str).str.len() > 0].copy()

    int_fields = {
        "comm_3m",
        "comm_6m",
        "comm_9m",
        "comm_12m",
        "inst_current",
        "inst_prev",
        "sales_total",
        "debt_total",
        "final_excess_amount",
    }
    div_fields = {"div_1m", "div_2m", "div_3m"}

    for f in int_fields:
        df2[f] = df2[f].apply(_to_int)
    for f in div_fields:
        df2[f] = df2[f].apply(_to_div)
    df2["maint_total"] = df2["maint_total"].apply(_to_decimal)

    ids = df2["user_id"].tolist()
    existing_ids, missing_sample = _existing_ids(ids)

    updated = 0
    missing_users = 0

    for r in df2.itertuples(index=False):
        uid = r.user_id
        if uid not in existing_ids:
            missing_users += 1
            continue

        defaults = {
            "comm_3m": int(r.comm_3m or 0),
            "comm_6m": int(r.comm_6m or 0),
            "comm_9m": int(r.comm_9m or 0),
            "comm_12m": int(r.comm_12m or 0),
            "inst_current": int(r.inst_current or 0),
            "inst_prev": int(r.inst_prev or 0),
            "sales_total": int(r.sales_total or 0),
            "debt_total": int(r.debt_total or 0),
            "final_excess_amount": int(r.final_excess_amount or 0),
            "div_1m": r.div_1m or "",
            "div_2m": r.div_2m or "",
            "div_3m": r.div_3m or "",
            "maint_total": r.maint_total if r.maint_total is not None else Decimal("0.00"),
        }
        _update_summary(uid, defaults)
        updated += 1

    return {
        "updated": updated,
        "missing_users": missing_users,
        "existing_users": len(existing_ids),
        "missing_sample": missing_sample,
    }


def handle_upload_guarantee_increase(df):
    """
    보증증액 업로드 (기존 호환 유지)
    - 내부적으로는 채권지표 업로드 로직과 동일
    """
    return handle_upload_deposit_metrics(df)


# =============================================================================
# Due rates (DataFrame)
# =============================================================================

def _handle_due_common(df, *, field_2_6: str, field_2_13: str):
    col_user = _detect_col(df, must_include=("사원", "코드"), any_include=()) or _detect_emp_id_col(df)
    col_2_6 = _detect_col(df, must_include=("2~6", "합산"), any_include=())
    col_2_13 = _detect_col(df, must_include=("2~13", "합산"), any_include=())
    if not col_user or not col_2_6 or not col_2_13:
        raise ValueError("엑셀 컬럼을 찾지 못했습니다. (필수: 사원코드, 합산(2~6회차), 합산(2~13회차))")

    df2 = df[[col_user, col_2_6, col_2_13]].copy()
    df2.columns = ["user_id", field_2_6, field_2_13]

    df2["user_id"] = df2["user_id"].apply(_norm_emp_id)
    df2 = df2[df2["user_id"].astype(str).str.len() > 0].copy()
    df2[field_2_6] = df2[field_2_6].apply(_to_decimal)
    df2[field_2_13] = df2[field_2_13].apply(_to_decimal)

    ids = df2["user_id"].tolist()
    existing_ids, missing_sample = _existing_ids(ids)

    updated = 0
    missing_users = 0

    for r in df2.itertuples(index=False):
        uid = r.user_id
        if uid not in existing_ids:
            missing_users += 1
            continue
        _update_summary(uid, {field_2_6: getattr(r, field_2_6), field_2_13: getattr(r, field_2_13)})
        updated += 1

    return {
        "updated": updated,
        "missing_users": missing_users,
        "existing_users": len(existing_ids),
        "missing_sample": missing_sample,
    }


def handle_upload_ls_due(df):
    return _handle_due_common(df, field_2_6="ls_2_6_due", field_2_13="ls_2_13_due")


def handle_upload_ns_due(df):
    return _handle_due_common(df, field_2_6="ns_2_6_due", field_2_13="ns_2_13_due")


# =============================================================================
# Detail uploads (DataFrame)
# =============================================================================

def handle_upload_surety(df):
    """
    보증보험 상세 업로드
    - 파일 기준이 “현재 상태 스냅샷”이므로 해당 user_id들 기존 rows 삭제 후 재삽입
    """
    col_user = (
        _detect_col(df, must_include=("사원", "코드"), any_include=())
        or _detect_col(df, must_include=("사원", "번호"), any_include=())
        or _detect_col(df, must_include=("사원번호",), any_include=())
        or _detect_col(df, must_include=("사번",), any_include=())
        or _detect_emp_id_col(df)
    )
    if not col_user:
        raise ValueError("엑셀 컬럼을 찾지 못했습니다. (필수: 사원코드/사번)")

    required = {
        "보증기호명": "product_name",
        "증권번호": "policy_no",
        "가입금액": "amount",
        "상태": "status",
        "보험시작일": "start_date",
        "보험종료일": "end_date",
    }

    detected = {}
    for excel_col in required.keys():
        found = _find_exact_or_space_removed(df.columns, excel_col)
        if found is None:
            raise ValueError(f"엑셀 컬럼을 찾지 못했습니다: [{excel_col}]")
        detected[excel_col] = found

    use_cols = [col_user] + [detected[k] for k in required.keys()]
    df2 = df[use_cols].copy()

    rename_map = {col_user: "user_id"}
    for excel_col, model_field in required.items():
        rename_map[detected[excel_col]] = model_field
    df2.rename(columns=rename_map, inplace=True)

    df2["user_id"] = df2["user_id"].apply(_norm_emp_id)
    df2 = df2[df2["user_id"].astype(str).str.len() > 0].copy()

    df2["product_name"] = df2["product_name"].fillna("").astype(str).str.strip()
    df2["policy_no"] = df2["policy_no"].fillna("").astype(str).str.strip()
    df2["status"] = df2["status"].fillna("").astype(str).str.strip()
    df2["amount"] = df2["amount"].apply(_to_int)
    df2["start_date"] = df2["start_date"].apply(_to_date)
    df2["end_date"] = df2["end_date"].apply(_to_date)

    ids = df2["user_id"].tolist()
    existing_ids, missing_sample = _existing_ids(ids)

    valid_df = df2[df2["user_id"].isin(existing_ids)].copy()
    target_ids = valid_df["user_id"].unique().tolist()

    DepositSurety.objects.filter(user_id__in=target_ids).delete()

    objs = [
        DepositSurety(
            user_id=r.user_id,
            product_name=r.product_name or "",
            policy_no=r.policy_no or "",
            amount=int(r.amount or 0),
            status=r.status or "",
            start_date=r.start_date,
            end_date=r.end_date,
        )
        for r in valid_df.itertuples()
    ]
    if objs:
        DepositSurety.objects.bulk_create(objs, batch_size=1000)

    return {
        "updated": len(objs),
        "missing_users": (len(ids) - len(valid_df)),
        "existing_users": len(existing_ids),
        "missing_sample": missing_sample,
    }


def handle_upload_other_debt(df):
    """
    기타채권 상세 업로드
    - 일부 파일은 첫 행에 header가 또 들어가는 경우가 있어 1행 스킵 방어
    - 파일 기준 스냅샷: 대상 user_id별 delete 후 bulk_create
    """
    if len(df) > 0:
        first_row_text = " ".join([str(x) for x in df.iloc[0].tolist()])
        if ("사번" in first_row_text) and ("상품명" in first_row_text):
            df = df.iloc[1:].copy()

    col_user = _detect_emp_id_col(df) or (
        _detect_col(df, must_include=("사번",), any_include=())
        or _detect_col(df, must_include=("사원", "번호"), any_include=())
        or _detect_col(df, must_include=("사원번호",), any_include=())
    )
    if not col_user:
        raise ValueError("엑셀 컬럼을 찾지 못했습니다. (필수: 사번)")

    col_map = {
        "번호": "bond_no",
        "상품명": "product_name",
        "보증내용": "product_type",
        "가입금액": "amount",
        "상태": "status",
        "계약일": "start_date",
        "비고": "memo",
    }

    detected = {}
    for k in col_map:
        c = _find_exact_or_space_removed(df.columns, k)
        if not c and k == "계약일":
            c = _find_exact_or_space_removed(df.columns, "보험시작일")
        if not c:
            raise ValueError(f"엑셀 컬럼을 찾지 못했습니다: {k}")
        detected[k] = c

    use_cols = [col_user] + list(detected.values())
    df2 = df[use_cols].copy()

    rename_map = {col_user: "user_id"}
    for excel_col, model_field in col_map.items():
        rename_map[detected[excel_col]] = model_field
    df2.rename(columns=rename_map, inplace=True)

    df2["user_id"] = df2["user_id"].apply(_norm_emp_id)
    df2 = df2[df2["user_id"].astype(str).str.len() > 0].copy()

    df2["bond_no"] = df2["bond_no"].fillna("").astype(str).str.strip()
    df2["product_name"] = df2["product_name"].fillna("").astype(str).str.strip()
    df2["product_type"] = df2["product_type"].fillna("").astype(str).str.strip()
    df2["status"] = df2["status"].fillna("").astype(str).str.strip()
    df2["memo"] = df2["memo"].fillna("").astype(str).str.strip()

    df2["amount"] = df2["amount"].apply(_to_int)
    df2["start_date"] = df2["start_date"].apply(_to_date)

    all_ids = df2["user_id"].tolist()
    existing_ids, missing_sample = _existing_ids(all_ids)

    valid_df = df2[df2["user_id"].isin(existing_ids)].copy()
    target_ids = valid_df["user_id"].unique().tolist()

    DepositOther.objects.filter(user_id__in=target_ids).delete()

    objs = [
        DepositOther(
            user_id=r.user_id,
            product_name=r.product_name,
            product_type=r.product_type,
            amount=int(r.amount or 0),
            bond_no=r.bond_no or "",
            status=r.status,
            start_date=r.start_date,
            memo=r.memo,
        )
        for r in valid_df.itertuples()
    ]
    if objs:
        DepositOther.objects.bulk_create(objs, batch_size=1000)

    return {
        "updated": len(objs),
        "missing_users": (len(all_ids) - len(valid_df)),
        "existing_users": len(existing_ids),
        "missing_sample": missing_sample,
    }


# =============================================================================
# Raw matrix file handlers (통산손/생보)
# =============================================================================

def _handle_total_from_file_common(file_path: str, original_name: str, *, prefix: str):
    """
    통산손/생보 raw matrix 업로드 공통
    - prefix: "ns" or "ls"
    """
    df = _read_excel_raw_matrix(file_path, original_name=original_name, skiprows=5, header_none=True)

    IDX_A = 0
    IDX_K = 10
    IDX_P = 15
    IDX_AT = 45
    IDX_AY = 50

    rows: List[Tuple[str, Decimal, Decimal, Decimal, Decimal]] = []
    emp_ids: List[str] = []

    for _, row in df.iterrows():
        emp7 = _extract_emp7_from_a(row[IDX_A] if len(row) > IDX_A else None)
        if not emp7:
            continue

        v13 = _safe_decimal_q2(row[IDX_K]) if len(row) > IDX_K else DEC2
        v18 = _safe_decimal_q2(row[IDX_P]) if len(row) > IDX_P else DEC2
        t18 = _safe_decimal_q2(row[IDX_AT]) if len(row) > IDX_AT else DEC2
        t25 = _safe_decimal_q2(row[IDX_AY]) if len(row) > IDX_AY else DEC2

        emp_ids.append(emp7)
        rows.append((emp7, v13, v18, t18, t25))

    if not rows:
        return {"updated": 0, "missing_users": 0, "existing_users": 0, "missing_sample": []}

    existing_ids = set(_bulk_existing_user_ids(set(emp_ids)))

    updated = 0
    skipped = 0

    fields_round = [f"{prefix}_13_round", f"{prefix}_18_round", f"{prefix}_18_total", f"{prefix}_25_total"]

    for emp7, v13, v18, t18, t25 in rows:
        if emp7 not in existing_ids:
            skipped += 1
            continue

        summary, _ = DepositSummary.objects.get_or_create(user_id=emp7)
        setattr(summary, fields_round[0], v13)
        setattr(summary, fields_round[1], v18)
        setattr(summary, fields_round[2], t18)
        setattr(summary, fields_round[3], t25)
        summary.save(update_fields=fields_round)
        updated += 1

    return {
        "updated": updated,
        "missing_users": skipped,
        "existing_users": len(existing_ids),
        "missing_sample": [],
    }


def handle_upload_ns_total_from_file(file_path: str, original_name: str):
    return _handle_total_from_file_common(file_path, original_name, prefix="ns")


def handle_upload_ls_total_from_file(file_path: str, original_name: str):
    return _handle_total_from_file_common(file_path, original_name, prefix="ls")


# =============================================================================
# Backward-compatible aliases (underscore)
# =============================================================================
_handle_upload_final_payment = handle_upload_final_payment
_handle_upload_refund_pay_expected = handle_upload_refund_pay_expected
_handle_upload_guarantee_increase = handle_upload_guarantee_increase
_handle_upload_ls_due = handle_upload_ls_due
_handle_upload_ns_due = handle_upload_ns_due
_handle_upload_surety = handle_upload_surety
_handle_upload_other_debt = handle_upload_other_debt
_handle_upload_ns_total_from_file = handle_upload_ns_total_from_file
_handle_upload_ls_total_from_file = handle_upload_ls_total_from_file


# =============================================================================
# SSOT: DepositUploadLog update
# =============================================================================
def _update_upload_log(part: str, upload_type: str, excel_file_name: str, count: int) -> str:
    """
    DepositUploadLog(part + upload_type unique) 갱신 SSOT.

    - DB/모델 필드명이 row_count(rows_count) / file_name(filename) 등
      환경차가 있을 수 있어 _meta.get_field로 안전하게 매핑한다.
    - commission.upload_utils._update_upload_log는 이 함수를 호출하는 deprecated wrapper다.
    - 신규 코드는 이 함수를 직접 재구현하지 말고 commission.upload_handlers export를 경유한다.
    """
    def _pick_field(*candidates: str) -> str:
        for name in candidates:
            try:
                DepositUploadLog._meta.get_field(name)
                return name
            except FieldDoesNotExist:
                continue
        raise FieldDoesNotExist(f"DepositUploadLog has none of fields: {candidates}")

    count_field = _pick_field("row_count", "rows_count")
    file_field = _pick_field("file_name", "filename")

    defaults = {
        count_field: int(count or 0),
        file_field: (excel_file_name or "")[:255],
    }

    obj, _ = DepositUploadLog.objects.update_or_create(
        part=part,
        upload_type=upload_type,
        defaults=defaults,
    )

    ts = getattr(obj, "uploaded_at", None) or timezone.now()
    return ts.strftime("%Y-%m-%d %H:%M")