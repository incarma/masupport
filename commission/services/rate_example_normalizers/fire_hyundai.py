# django_ma/commission/services/rate_example_normalizers/fire_hyundai.py
from __future__ import annotations

"""
현대해상 손해보험 수정률 정규화.

대상:
- insurer_type = fire
- category = conv
- insurer = 현대

정규화 대상 시트:
1. G A
2. 태아보험
3. 실손의료비

저장 구조:
- 보험사      → insurer = "현대"
- 상품군      → coverage_type
- 상품명      → product_name
- 구분        → plan_type
- 납기        → pay_period
- 수정률      → year1
- year2~year4 → None

주의:
- 손해보험 수정률은 단일 컬럼 구조이므로 RateExampleConversionRow.year1에만 저장한다.
- 파일 URL 직접 접근 없이 normalize_rate_example()에서 전달받은 workbook만 사용한다.
"""

import re
from decimal import Decimal, InvalidOperation

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example_normalizers._common import (
    build_worksheet_value_map,
)


INSURER = "현대"


def _text(value) -> str:
    """셀 값을 비교·저장 가능한 단일 문자열로 정규화한다."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _one_line(value, *, sep: str = " ") -> str:
    """줄바꿈이 있는 셀을 한 줄 텍스트로 정규화한다."""
    text = _text(value)
    if not text:
        return ""
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    return sep.join(parts).strip()


def _strip_symbol(value: str, symbol: str) -> str:
    return _text(value).replace(symbol, "").strip()


def _clean_fetus_product_name(value: str) -> str:
    """
    태아보험 시트 상품명 정리.

    규칙:
    - "□" 제거
    - "수정률 및 수수료" 문구 제거
    - 다중 공백 정리
    """
    text = _text(value)
    text = text.replace("□", "")
    text = text.replace("수정률 및 수수료", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _to_decimal_percent(cell) -> Decimal | None:
    """
    수정률 셀을 화면 표시 기준 백분율 숫자로 변환한다.

    - Excel 내부값 1.6 + percent format → 160
    - Excel 내부값 160 일반 숫자        → 160
    - 문자열 "160%"                    → 160
    """
    value = cell.value
    if value is None or value == "":
        return None

    try:
        if isinstance(value, str):
            raw = value.replace("%", "").replace(",", "").strip()
            if not raw:
                return None
            dec = Decimal(raw)
        else:
            dec = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

    number_format = str(getattr(cell, "number_format", "") or "")
    if "%" in number_format:
        dec = dec * Decimal("100")

    return dec


def _merged_value_map(ws) -> dict[tuple[int, int], object]:
    """
    병합 셀 값을 병합 범위 전체 좌표에 전파한 map을 만든다.

    openpyxl worksheet 자체를 수정하지 않아 원본 workbook side effect를 만들지 않는다.
    """
    return build_worksheet_value_map(ws)


def _mv(values: dict[tuple[int, int], object], row_no: int, col_no: int) -> str:
    return _text(values.get((row_no, col_no)))


def _mv_one_line(
    values: dict[tuple[int, int], object],
    row_no: int,
    col_no: int,
    *,
    sep: str = " ",
) -> str:
    return _one_line(values.get((row_no, col_no)), sep=sep)


def _join_with_paren(base: str, suffix: str, *, no_space_values: set[str] | None = None) -> str:
    """base 끝에 suffix를 괄호로 결합한다."""
    base = _one_line(base)
    suffix = _one_line(suffix)
    if not base:
        return ""
    if not suffix:
        return base
    if base == suffix:
        return base

    no_space_values = no_space_values or set()
    sep = "" if suffix in no_space_values else " "
    return f"{base}{sep}({suffix})"


def _coverage_from_product(product_name: str) -> str:
    """현대 GA 시트 상품군 규칙."""
    product_name = _text(product_name)
    if "연금" in product_name:
        return "연금"
    if "저축" in product_name:
        return "저축"
    return "보장"


def _build_row(
    example: RateExample,
    *,
    sheet_name: str,
    row_no: int,
    coverage_type: str,
    product_name: str,
    plan_type: str,
    pay_period: str,
    rate: Decimal,
) -> RateExampleConversionRow:
    """RateExampleConversionRow 생성 SSOT."""
    return RateExampleConversionRow(
        source_file=example,
        source_sheet=sheet_name,
        source_row_no=row_no,
        insurer_type=RateExample.TYPE_FIRE,
        category=RateExample.CAT_CONV,
        insurer=INSURER,
        coverage_type=_text(coverage_type),
        strategy_flag="",
        product_name=_one_line(product_name),
        plan_type=_one_line(plan_type),
        pay_period=_one_line(pay_period, sep="/"),
        year1=rate,
        year2=None,
        year3=None,
        year4=None,
    )


def _build_ga_rows(example: RateExample, wb) -> list[RateExampleConversionRow]:
    """
    [G A] 시트 정규화.

    핵심 변경 반영:
    - E열 상품명에 현재 행과 다음 행 모두 텍스트가 있으면,
      다음 행 텍스트를 현재 행 상품명에 이어붙인다.
    - 이어붙인 다음 행의 상품명은 공란으로 간주한다.
    - 공란 상품명은 위쪽 마지막 상품명으로 carry-down 한다.
    """
    sheet_name = "G A"
    if sheet_name not in wb.sheetnames:
        return []

    ws = wb[sheet_name]
    rows: list[RateExampleConversionRow] = []

    data_start = 15
    data_end = ws.max_row

    # ── 1) 상품명(E열) 연속 텍스트 결합 전처리 ─────────────────────────────
    product_by_row: dict[int, str] = {
        row_no: _one_line(ws.cell(row=row_no, column=5).value)
        for row_no in range(data_start, data_end + 1)
    }

    row_no = data_start
    while row_no <= data_end:
        current_product = product_by_row.get(row_no, "")
        next_product = product_by_row.get(row_no + 1, "")

        if current_product and next_product:
            # 현대 [G A] raw는 상품명이 E열에서 여러 행으로 분리될 수 있다.
            # 다음 행에 수정률(K열)이 있어도 E열 텍스트는 상품명 continuation으로 먼저 결합한다.
            # 예:
            #   48행: (무)퍼펙트플러스종합보험
            #   49행: (일반심사/건강고지형)
            # → 48행 상품명: (무)퍼펙트플러스종합보험 (일반심사/건강고지형)
            # → 49행 상품명: 공란 취급 후 carry-down
            product_by_row[row_no] = f"{current_product} {next_product}".strip()
            product_by_row[row_no + 1] = ""

        row_no += 1

    # ── 2) 상품명/구분/납기 carry-down 후 row 생성 ────────────────────────
    last_product = ""
    last_maturity = ""   # G열 만기구분
    last_jong = ""       # H열 종형
    last_etc = ""        # I열 만 기 / 기타구분값
    last_pay = ""        # J열 납기

    for row_no in range(data_start, data_end + 1):
        raw_product = product_by_row.get(row_no, "")
        if raw_product:
            last_product = raw_product

        maturity = _one_line(ws.cell(row=row_no, column=7).value)
        jong = _one_line(ws.cell(row=row_no, column=8).value)
        etc = _one_line(ws.cell(row=row_no, column=9).value)
        pay = _one_line(ws.cell(row=row_no, column=10).value)
        rate = _to_decimal_percent(ws.cell(row=row_no, column=11))

        if maturity:
            last_maturity = maturity
        if jong:
            last_jong = jong
        if etc:
            last_etc = etc
        if pay:
            last_pay = pay

        if not last_product or rate is None:
            continue

        plan_type = _join_with_paren(
            last_maturity,
            last_jong,
            no_space_values={"무해지"},
        )
        pay_period = _join_with_paren(
            last_pay,
            last_etc,
            no_space_values=set(),
        )

        if not plan_type or not pay_period:
            continue

        rows.append(
            _build_row(
                example,
                sheet_name=sheet_name,
                row_no=row_no,
                coverage_type=_coverage_from_product(last_product),
                product_name=last_product,
                plan_type=plan_type,
                pay_period=pay_period,
                rate=rate,
            )
        )

    return rows


def _build_fetus_rows(example: RateExample, wb) -> list[RateExampleConversionRow]:
    """[태아보험] 시트 정규화."""
    sheet_name = "태아보험"
    if sheet_name not in wb.sheetnames:
        return []

    ws = wb[sheet_name]
    values = _merged_value_map(ws)
    rows: list[RateExampleConversionRow] = []

    # 예:
    # "□ 무배당굿앤굿어린이종합보험Q 수정률 및 수수료"
    # → "무배당굿앤굿어린이종합보험Q"
    product_name = _clean_fetus_product_name(_mv(values, 2, 1))

    if not product_name:
        return rows

    data_start = 14

    for row_no in range(data_start, ws.max_row + 1):
        plan_base = _mv_one_line(values, row_no, 2)
        jong = _mv_one_line(values, row_no, 3)
        maturity = _mv_one_line(values, row_no, 4, sep="/")
        pay = _mv_one_line(values, row_no, 5, sep="/")
        # 기본 규칙은 수정률(F열) 사용.
        # 단, 현대 태아보험 raw의 "태아보장" 행은 F열이 "-"이고
        # 실제 수치가 별도 모집수수료(G열)에 기재되어 있어 보장(태아) 누락 방지를 위해 fallback 적용.
        rate = _to_decimal_percent(ws.cell(row=row_no, column=6))
        if rate is None and "태아" in plan_base:
            rate = _to_decimal_percent(ws.cell(row=row_no, column=7))

        if rate is None:
            continue

        plan_type = _join_with_paren(plan_base, jong)
        pay_period = _join_with_paren(pay, maturity)

        if not plan_type or not pay_period:
            continue

        coverage_type = "보장(태아)" if "태아" in plan_type else "보장"

        rows.append(
            _build_row(
                example,
                sheet_name=sheet_name,
                row_no=row_no,
                coverage_type=coverage_type,
                product_name=product_name,
                plan_type=plan_type,
                pay_period=pay_period,
                rate=rate,
            )
        )

    return rows


def _build_actual_loss_rows(example: RateExample, wb) -> list[RateExampleConversionRow]:
    """[실손의료비] 시트 정규화."""
    sheet_name = "실손의료비"
    if sheet_name not in wb.sheetnames:
        return []

    ws = wb[sheet_name]
    values = _merged_value_map(ws)
    rows: list[RateExampleConversionRow] = []

    data_start = 11

    for row_no in range(data_start, ws.max_row + 1):
        # 실손의료비 raw는 B/C열 병합 헤더가 "가입유형" 구조다.
        # 기존 A/B열 참조 시 A열이 공란이라 plan_type이 비어 전체 skip된다.
        plan_a = _mv_one_line(values, row_no, 2)
        plan_b = _mv_one_line(values, row_no, 3)
        product_name = _mv_one_line(values, row_no, 4)
        pay_period = _mv_one_line(values, row_no, 5, sep="/")
        rate = _to_decimal_percent(ws.cell(row=row_no, column=7))

        if rate is None:
            continue

        plan_type = _join_with_paren(plan_a, plan_b)

        if not product_name or not plan_type or not pay_period:
            continue

        coverage_type = "단독실손(갱신)" if "갱신" in pay_period else "단독실손(초회)"

        rows.append(
            _build_row(
                example,
                sheet_name=sheet_name,
                row_no=row_no,
                coverage_type=coverage_type,
                product_name=product_name,
                plan_type=plan_type,
                pay_period=pay_period,
                rate=rate,
            )
        )

    return rows


def build_fire_hyundai_conversion_rows(example: RateExample, wb) -> list[RateExampleConversionRow]:
    """
    현대해상 손해보험 수정률 정규화 진입점.

    반환:
    - bulk_create 가능한 RateExampleConversionRow 리스트
    """
    rows: list[RateExampleConversionRow] = []
    rows.extend(_build_ga_rows(example, wb))
    rows.extend(_build_fetus_rows(example, wb))
    rows.extend(_build_actual_loss_rows(example, wb))
    return rows