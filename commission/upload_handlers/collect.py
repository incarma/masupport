# django_ma/commission/upload_handlers/collect.py
"""
환수관리(Collect) 전용 엑셀 업로드 핸들러 — Step 3

[엑셀 구조 (분석 완료)]
- 헤더 : 1행 (index 0)
- 합계행: 2행 (index 1) — 사번이 None인 행 → 파싱 후 emp_id 정규화 단계에서 자동 스킵
- 실데이터: 3행 (index 2)부터 1,524건
- 전체 컬럼: 36개

[처리 흐름]
1. 필수 컬럼 탐지 (사번, 월도, 최종지급액)
2. 전체 컬럼 탐지 (COL_MAP 기준, 없는 컬럼은 기본값 적용)
3. 행별 파싱 (emp_id 정규화 → 빈 문자열이면 스킵, ym 정규화 → 6자리 아니면 스킵)
4. CollectRecord bulk_create(update_conflicts=True)
5. CollectUploadLog update_or_create (월도 기준 1건 유지)
6. Audit 로그 기록은 api_collect.py 뷰에서 수행 (핸들러는 순수 처리만)

[SSOT 재사용]
- _norm_emp_id, _to_int: commission/upload_handlers/deposit.py에서 import
- 컬럼 탐지는 COL_MAP의 정확한 컬럼명을 직접 매핑 (엑셀 헤더가 고정이므로 _detect_col 불필요)
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
from django.db import transaction

from commission.models import CollectRecord, CollectUploadLog

# deposit.py의 공용 유틸 재사용 (SSOT)
from commission.upload_handlers.deposit import (
    _norm_emp_id,
    _to_int,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 컬럼 → 모델 필드 매핑 (가이드맵 v2 COL_MAP 기준)
# key: 엑셀 헤더 컬럼명, value: (모델 필드명, 타입)
# =============================================================================
COL_MAP: dict[str, tuple[str, str]] = {
    "월도":         ("ym",               "ym_str"),
    "부문총괄":     ("bizmoon_total",    "str"),
    "부문":         ("bizmoon",          "str"),
    "총괄":         ("total",            "str"),
    "부서":         ("part",             "str"),
    "영업가족":     ("branch",           "str"),
    "영업가족코드": ("branch_code",      "str"),
    "소속":         ("affiliation",      "str"),
    "등록구분":     ("regist_type",      "str"),
    "사원명":       ("emp_name",         "str"),
    "재직(설계사)": ("work_status",      "str"),
    "입사일":       ("enter_date",       "date"),
    "사번":         ("emp_id",           "emp_id"),
    "최종지급액":   ("final_payment",    "int"),
    "결재":         ("approval",         "str"),
    "지급":         ("pay_flag",         "str"),
    "보증채권합계": ("surety_bond_total", "int"),
    "보증/채권":    ("surety_bond_detail","str"),
    "환수조치":     ("collect_action",   "str"),
    "상태":         ("status",           "str"),
    "조치상세":     ("action_detail",    "str"),
    "자동차":       ("car",              "int"),
    "일반":         ("general",          "int"),
    "손보초회":     ("ns_init",          "int"),
    "손보계속":     ("ns_cont",          "int"),
    "손보합계":     ("ns_total",         "int"),
    "생보초회":     ("ls_init",          "int"),
    "생보계속":     ("ls_cont",          "int"),
    "생보합계":     ("ls_total",         "int"),
    "기타지급":     ("etc_pay",          "int"),
    "기타공제":     ("etc_deduct",       "int"),
    "선지급":       ("prepay",           "int"),
    "1차지급":      ("first_pay",        "int"),
    "세금":         ("tax",              "int"),
    "실지급액":     ("actual_pay",       "int"),
    "자체정산":     ("self_settle",      "int"),
}

# update_conflicts 시 갱신할 필드 목록 (emp_id, ym 제외한 데이터 필드 전체)
UPDATE_FIELDS = [
    field
    for col, (field, _) in COL_MAP.items()
    if field not in ("emp_id", "ym")
] + ["uploaded_at"]


# =============================================================================
# 내부 헬퍼
# =============================================================================

def _norm_ym(val) -> str:
    """
    월도 값을 YYYYMM 6자리 문자열로 정규화한다.
    - "202603"  → "202603" (str 그대로)
    - 202603.0  → "202603" (float → str 변환 후 소수점 제거)
    - 6자리가 아니면 "" 반환 (해당 행 스킵)
    """
    if val is None:
        return ""
    s = str(val).strip()
    # "202603.0" 같은 float 표현 처리
    if "." in s:
        s = s.split(".")[0]
    return s if len(s) == 6 and s.isdigit() else ""


def _norm_str(val, maxlen: int = 100) -> str:
    """값을 문자열로 변환하고 maxlen 이내로 자른다. None → ""."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()[:maxlen]


def _norm_date(val) -> date | None:
    """
    입사일 값을 date 객체로 변환한다.
    - "2026-01-14" (str) → date(2026, 1, 14)
    - datetime 객체 → .date()
    - 변환 실패 → None
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, date):
        return val
    try:
        return pd.to_datetime(str(val)).date()
    except Exception:
        return None


# =============================================================================
# 메인 핸들러
# =============================================================================

@transaction.atomic
def handle_upload_collect(df: pd.DataFrame) -> dict:
    """
    환수관리 전용 엑셀 업로드 핸들러.

    [파라미터]
        df: _read_excel_safely()로 읽은 DataFrame
            (헤더=1행, 합계행=2행은 emp_id None으로 자동 스킵)

    [반환값]
        {
            "inserted_or_updated": int,  # CollectRecord upsert 건수
            "skipped":             int,  # emp_id/ym 정규화 실패로 스킵된 행 수
            "ym":                  str,  # 처리된 월도 (예: "202603")
            "missing_sample":      list, # 스킵된 emp_id 샘플 (최대 10개)
            "matched_columns":     dict, # 탐지된 컬럼 매핑 정보
        }
    """

    # ──────────────────────────────────────────────────────────────────
    # 1. 컬럼 탐지 — DataFrame의 실제 컬럼명과 COL_MAP 교차 확인
    # ──────────────────────────────────────────────────────────────────
    # 공백 제거 후 비교 (컬럼명 앞뒤 공백 방어)
    df_cols_normalized = {str(c).strip(): c for c in df.columns}

    # 필수 컬럼 존재 확인
    REQUIRED_COLS = {"사번", "월도", "최종지급액"}
    missing_required = REQUIRED_COLS - set(df_cols_normalized.keys())
    if missing_required:
        raise ValueError(
            f"필수 컬럼을 찾지 못했습니다: {sorted(missing_required)}\n"
            f"발견된 컬럼: {list(df_cols_normalized.keys())[:10]}"
        )

    # COL_MAP 기준으로 실제 DataFrame 컬럼명 매핑
    # {엑셀 컬럼명: 실제 df 컬럼명} — 없는 컬럼은 None
    matched_columns: dict[str, str | None] = {
        excel_col: df_cols_normalized.get(excel_col)
        for excel_col in COL_MAP
    }

    logger.info(
        "[collect_upload] 컬럼 탐지 완료: 매핑=%d/%d개",
        sum(1 for v in matched_columns.values() if v is not None),
        len(COL_MAP),
    )

    # ──────────────────────────────────────────────────────────────────
    # 2. 행별 파싱
    # ──────────────────────────────────────────────────────────────────
    objs: list[CollectRecord] = []
    skipped = 0
    skipped_ids: list[str] = []
    ym_set: set[str] = set()

    # itertuples 대신 iterrows 사용 (특수문자 컬럼명 "보증/채권", "재직(설계사)" 대응)
    for _, row in df.iterrows():

        # ── emp_id 정규화 (None인 합계행 자동 스킵) ──
        raw_emp = matched_columns.get("사번") and row.get(matched_columns["사번"])
        emp_id = _norm_emp_id(raw_emp) if raw_emp is not None else ""
        if not emp_id:
            skipped += 1
            if raw_emp is not None:
                skipped_ids.append(str(raw_emp)[:20])
            continue

        # ── ym 정규화 (6자리 아니면 스킵) ──
        raw_ym = matched_columns.get("월도") and row.get(matched_columns["월도"])
        ym = _norm_ym(raw_ym)
        if not ym:
            skipped += 1
            skipped_ids.append(emp_id)
            continue

        ym_set.add(ym)

        # ── 나머지 필드 파싱 (COL_MAP 기준) ──
        kwargs: dict = {"emp_id": emp_id, "ym": ym}

        for excel_col, (field, col_type) in COL_MAP.items():
            if field in ("emp_id", "ym"):   # 이미 처리
                continue

            df_col = matched_columns.get(excel_col)
            raw_val = row.get(df_col) if df_col else None

            if col_type == "int":
                kwargs[field] = _to_int(raw_val)
            elif col_type == "date":
                kwargs[field] = _norm_date(raw_val)
            elif col_type == "str":
                # 필드별 maxlen 설정 (모델 정의와 일치)
                maxlen_map = {
                    "affiliation":       300,
                    "action_detail":     500,
                    "surety_bond_detail":200,
                    "collect_action":    200,
                    "status":            100,
                    "bizmoon_total":     100,
                    "emp_name":          100,
                    "branch":            100,
                }
                maxlen = maxlen_map.get(field, 50)
                kwargs[field] = _norm_str(raw_val, maxlen=maxlen)
            else:
                kwargs[field] = _norm_str(raw_val)

        objs.append(CollectRecord(**kwargs))

    logger.info(
        "[collect_upload] 파싱 완료: 처리=%d건, 스킵=%d건, 월도=%s",
        len(objs), skipped, ym_set,
    )

    # ──────────────────────────────────────────────────────────────────
    # 3. CollectRecord bulk upsert
    # ──────────────────────────────────────────────────────────────────
    if objs:
        CollectRecord.objects.bulk_create(
            objs,
            batch_size=500,
            update_conflicts=True,
            unique_fields=["emp_id", "ym"],
            update_fields=UPDATE_FIELDS,
        )

    inserted_or_updated = len(objs)

    # ──────────────────────────────────────────────────────────────────
    # 4. CollectUploadLog update_or_create (월도별 1건 유지)
    #    - file_name / uploaded_by 는 호출 뷰(api_collect_upload)에서 주입
    #    - 핸들러는 순수 파싱/저장만 담당
    # ──────────────────────────────────────────────────────────────────
    for ym in ym_set:
        CollectUploadLog.objects.update_or_create(
            ym=ym,
            defaults={
                "row_count": inserted_or_updated,
                # file_name / uploaded_by 는 뷰에서 after-hook으로 갱신
            },
        )

    logger.info(
        "[collect_upload] 완료: upsert=%d건, 스킵=%d건",
        inserted_or_updated, skipped,
    )

    return {
        "inserted_or_updated": inserted_or_updated,
        "skipped":             skipped,
        "ym":                  next(iter(ym_set), ""),
        "missing_sample":      skipped_ids[:10],
        "matched_columns":     {k: v for k, v in matched_columns.items() if v},
    }