# commission/services/rate_example/life/met/parser.py
from __future__ import annotations

"""
메트라이프 생명 환산율/수정률 정규화 parser.

대상:
- 시트: 주계약 CSC
- 데이터 시작: 11행

매핑:
- 보험사: 메트 고정
- 상품명: C열
- 보종: 상품명 기반 판정
- 납기: E열
- 구분: F열 보험료 또는 G열 가입금액
- 1차년: K열
- 2차년: L열
- 3차년: M열
- 4차년: N열
"""

import logging

from commission.models import RateExampleConversionRow
from commission.services.rate_example.common.decimal import decimal_percent_cell
from commission.services.rate_example.common.text import clean_text

logger = logging.getLogger(__name__)


TARGET_SHEET = "주계약 CSC"
DATA_START_ROW = 11


def _clean(value) -> str:
    return clean_text(value)

def _is_dash(value) -> bool:
    text = _clean(value)
    return text in {"", "-"}


def _coverage_type(product_name: str) -> str:
    """
    상품명 기반 보종 판정.

    우선순위:
    - 변액 포함: 변액연금
    - 경영 포함: CEO정기
    - 종신 포함: 종신/CI
    - 연금 포함: 연금
    - 미해당: 기타(보장성)
    """
    name = product_name or ""
    if "변액" in name:
        return "변액연금"
    if "경영" in name:
        return "CEO정기"
    if "종신" in name:
        return "종신/CI"
    if "연금" in name:
        return "연금"
    return "기타(보장성)"


def _plan_type(premium_text, amount_text) -> str:
    """
    구분(plan_type) 판정.

    - 보험료(F열)가 '-'가 아니면 F열 사용
    - 가입금액(G열)이 '-'가 아니면 G열 사용
    - 둘 다 '-'이면 공란
    """
    if not _is_dash(premium_text):
        return _clean(premium_text)
    if not _is_dash(amount_text):
        return _clean(amount_text)
    return ""


def _to_percent_decimal(cell) -> Decimal | None:
    """
    Excel 셀 값을 DB 저장용 백분율 수치 Decimal로 변환.

    저장 정책:
    - 100%는 Decimal("100")으로 저장한다.
    - Excel number_format에 %가 있으면 openpyxl raw 값에 100을 곱한다.
    """
    # 메트 정책: 100%는 DB Decimal("100") 기준으로 저장한다.
    return decimal_percent_cell(cell)


def build_life_met_conversion_rows(example, workbook) -> list[RateExampleConversionRow]:
    """
    메트 raw workbook → RateExampleConversionRow 리스트.
    """
    if TARGET_SHEET not in workbook.sheetnames:
        logger.warning(
            "MET normalizer: target sheet not found. pk=%s sheets=%s",
            example.pk,
            workbook.sheetnames,
        )
        return []

    ws = workbook[TARGET_SHEET]
    rows: list[RateExampleConversionRow] = []

    for row_no in range(DATA_START_ROW, ws.max_row + 1):
        product_name = _clean(ws.cell(row=row_no, column=3).value)   # C
        pay_period = _clean(ws.cell(row=row_no, column=5).value)     # E

        if not product_name:
            continue

        year1 = _to_percent_decimal(ws.cell(row=row_no, column=11))  # K
        year2 = _to_percent_decimal(ws.cell(row=row_no, column=12))  # L
        year3 = _to_percent_decimal(ws.cell(row=row_no, column=13))  # M
        year4 = _to_percent_decimal(ws.cell(row=row_no, column=14))  # N

        if year1 is None and year2 is None and year3 is None and year4 is None:
            continue

        rows.append(
            RateExampleConversionRow(
                source_file=example,
                source_sheet=TARGET_SHEET,
                source_row_no=row_no,
                insurer_type=example.insurer_type,
                category=example.category,
                insurer="메트",
                coverage_type=_coverage_type(product_name),
                product_name=product_name,
                plan_type=_plan_type(
                    ws.cell(row=row_no, column=6).value,  # F
                    ws.cell(row=row_no, column=7).value,  # G
                ),
                pay_period=pay_period,
                year1=year1,
                year2=year2,
                year3=year3,
                year4=year4,
            )
        )

    logger.info("MET normalizer: created %d rows. pk=%s", len(rows), example.pk)
    return rows
