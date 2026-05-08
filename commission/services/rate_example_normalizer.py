# commission/services/rate_example_normalizer.py.py
from __future__ import annotations

"""
RateExample 정규화 서비스.

역할:
- 업로드된 예시표 원본 파일을 보험사별 규칙에 따라 정규화 테이블로 적재한다.
- 현재 1차 대상: 생명보험 / 환산률·수정률 / ABL
- 원본 파일 저장/검증은 RateExampleService가 담당하고, 이 파일은 정규화만 담당한다.

보안/운영 원칙:
- 파일 URL 직접 접근 금지. FieldFile.path만 서버 내부에서 사용.
- 파싱 실패 시 예외를 삼키지 않고 호출부에서 rollback 가능하도록 raise.
- 동일 보험사·구분 정규화 데이터는 최신 업로드 기준으로 교체한다.
"""

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Iterable

from openpyxl import load_workbook

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example_normalizers.db_life import (
    build_db_life_conversion_rows,
)

logger = logging.getLogger(__name__)

SHEET_ABL_SAVING = "주계약(저축성)"
SHEET_ABL_PROTECTION = "주계약(보장성)_12개월 선지급"


def _clean_text(value) -> str:
    """엑셀 셀 값을 화면 표시용 문자열로 정규화."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\r", "\n").replace("\n", " ")).strip()


def _to_decimal(value):
    """정수/실수/문자 퍼센트 값을 DecimalField 저장값으로 변환."""
    if value is None or value == "":
        return None

    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(Decimal("0.0001"))

    text = _clean_text(value).replace(",", "").replace("%", "")
    if not text:
        return None

    try:
        return Decimal(text).quantize(Decimal("0.0001"))
    except InvalidOperation:
        logger.warning("[rate_example] decimal parse skipped value=%r", value)
        return None


def _has_any_rate(*values) -> bool:
    """연차별 환산률 값이 하나라도 있으면 데이터 행으로 판단."""
    return any(_to_decimal(v) is not None for v in values)


def _normalize_abl_saving(example: RateExample, ws) -> Iterable[RateExampleConversionRow]:
    """
    ABL [주계약(저축성)] 시트 정규화.

    사용자 규칙:
    - 보험사: ABL
    - 보종: 연금
    - 상품명: A열
    - 구분: B열(형태)
    - 납기: C열
    - 1차년: D열
    - 2차년: E열
    - 3차년: F열
    - 4차년: 없음(null)
    """
    rows: list[RateExampleConversionRow] = []
    last_product = ""
    last_plan = ""

    for row_no in range(5, ws.max_row + 1):
        product = _clean_text(ws.cell(row_no, 1).value) or last_product
        plan = _clean_text(ws.cell(row_no, 2).value) or last_plan
        pay_period = _clean_text(ws.cell(row_no, 3).value)

        y1_raw = ws.cell(row_no, 4).value
        y2_raw = ws.cell(row_no, 5).value
        y3_raw = ws.cell(row_no, 6).value

        if _clean_text(ws.cell(row_no, 1).value):
            last_product = product
        if _clean_text(ws.cell(row_no, 2).value):
            last_plan = plan

        if not product and not pay_period and not _has_any_rate(y1_raw, y2_raw, y3_raw):
            continue
        if not pay_period and not _has_any_rate(y1_raw, y2_raw, y3_raw):
            continue

        rows.append(RateExampleConversionRow(
            source_file=example,
            source_sheet=SHEET_ABL_SAVING,
            source_row_no=row_no,
            insurer_type=example.insurer_type,
            category=example.category,
            insurer="ABL",
            coverage_type="연금",
            strategy_flag="",
            product_name=product,
            plan_type=plan,
            pay_period=pay_period,
            year1=_to_decimal(y1_raw),
            year2=_to_decimal(y2_raw),
            year3=_to_decimal(y3_raw),
            year4=None,
        ))

    return rows


def _coverage_type_for_abl_protection(product_name: str) -> str:
    """상품명에 '종신' 포함 여부로 보종 분기."""
    return "종신/CI" if "종신" in product_name else "기타(보장성)"


def _normalize_abl_protection(example: RateExample, ws) -> Iterable[RateExampleConversionRow]:
    """
    ABL [주계약(보장성)_12개월 선지급] 시트 정규화.

    사용자 규칙:
    - 보험사: ABL
    - 보종: 상품명에 '종신' 포함 시 종신/CI, 아니면 기타(보장성)
    - 상품명: A열
    - 구분: B열(형태)
    - 납기: E열
    - 1차년: F열
    - 2차년: G열
    - 3차년: H열
    - 4차년: I열
    """
    rows: list[RateExampleConversionRow] = []
    last_product = ""
    last_plan = ""

    for row_no in range(5, ws.max_row + 1):
        product = _clean_text(ws.cell(row_no, 1).value) or last_product
        plan = _clean_text(ws.cell(row_no, 2).value) or last_plan
        pay_period = _clean_text(ws.cell(row_no, 5).value)

        y1_raw = ws.cell(row_no, 6).value
        y2_raw = ws.cell(row_no, 7).value
        y3_raw = ws.cell(row_no, 8).value
        y4_raw = ws.cell(row_no, 9).value

        if _clean_text(ws.cell(row_no, 1).value):
            last_product = product
        if _clean_text(ws.cell(row_no, 2).value):
            last_plan = plan

        if not product and not pay_period and not _has_any_rate(y1_raw, y2_raw, y3_raw, y4_raw):
            continue
        if not pay_period and not _has_any_rate(y1_raw, y2_raw, y3_raw, y4_raw):
            continue

        rows.append(RateExampleConversionRow(
            source_file=example,
            source_sheet=SHEET_ABL_PROTECTION,
            source_row_no=row_no,
            insurer_type=example.insurer_type,
            category=example.category,
            insurer="ABL",
            coverage_type=_coverage_type_for_abl_protection(product),
            strategy_flag="",
            product_name=product,
            plan_type=plan,
            pay_period=pay_period,
            year1=_to_decimal(y1_raw),
            year2=_to_decimal(y2_raw),
            year3=_to_decimal(y3_raw),
            year4=_to_decimal(y4_raw),
        ))

    return rows


def normalize_rate_example(example: RateExample) -> int:
    """
    RateExample 업로드 파일을 정규화한다.

    현재 지원:
    - 생명보험 / 환산률·수정률 / DB / xlsx

    반환:
    - 생성된 RateExampleConversionRow 수
    """
    if not (
        example.insurer_type == RateExample.TYPE_LIFE
        and example.category == RateExample.CAT_CONV
        and example.insurer in {"ABL", "DB"}
    ):
        return 0

    if not example.file:
        return 0

    # 정규화 대상은 xlsx 기준이다. xls/pdf는 원본 보관만 수행한다.
    if not str(example.original_name or "").lower().endswith(".xlsx"):
        return 0

    wb = load_workbook(example.file.path, data_only=True, read_only=True)

    normalized_rows: list[RateExampleConversionRow] = []
    
    # ── ABL 생명 환산률/수정률 정규화 ─────────────────────────────
    # 기존 규칙 유지: 필수 시트 2개를 대상으로 고정 매핑한다.
    if example.insurer == "ABL":
        missing = [
            sheet_name
            for sheet_name in (SHEET_ABL_SAVING, SHEET_ABL_PROTECTION)
            if sheet_name not in wb.sheetnames
        ]
        if missing:
            raise ValueError(f"ABL 환산률/수정률 필수 시트가 없습니다: {', '.join(missing)}")

        normalized_rows.extend(_normalize_abl_saving(example, wb[SHEET_ABL_SAVING]))
        normalized_rows.extend(_normalize_abl_protection(example, wb[SHEET_ABL_PROTECTION]))

    # ── DB 생명 환산률/수정률 정규화 ──────────────────────────────
    # 신규 규칙:
    # - 특약/방카교차 시트 제외
    # - 각 시트 첫 번째 테이블만 정규화
    # - 상품명은 A1, 보종은 시트명 기반 판정
    elif example.insurer == "DB":
        normalized_rows.extend(build_db_life_conversion_rows(example, wb))

    # 동일 보험사/구분의 정규화 master는 최신 업로드 기준으로 교체한다.
    RateExampleConversionRow.objects.filter(
        insurer_type=example.insurer_type,
        category=example.category,
        insurer=example.insurer,
    ).delete()

    if normalized_rows:
        RateExampleConversionRow.objects.bulk_create(normalized_rows, batch_size=500)

    return len(normalized_rows)