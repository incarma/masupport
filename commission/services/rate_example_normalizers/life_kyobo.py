# commission/services/rate_example_normalizers/life_kyobo.py
from __future__ import annotations

"""
교보 생명보험 환산율/수정률 정규화 parser.

역할:
- 교보 raw 예시표 중 "주계약(종속특약포함)" 시트만 정규화한다.
- 현재는 B열~F열 범위의 종신보험 테이블만 정규화한다.
- 정규화 결과는 RateExampleConversionRow master 테이블에 적재할 row 객체 목록으로 반환한다.

정규화 정책:
- 보험사: "교보"
- 시트: "주계약(종속특약포함)"
- 범위: B열~F열
- 데이터 행: 6행부터 F열(총환산월초)의 마지막 데이터 행까지
- 5행(B5~F5)은 헤더로 보고 정규화 제외
- 보종: "종신/CI" 고정
- 상품명: B열
  - "판매중지" 포함 상품 제외
  - 상품명 공란 시 상단의 마지막 상품명 전파
  - 마지막 상품명이 판매중지 상품이면 공란 행도 제외
- 구분: E열 월납보험료
- 납기: D열 납입기간
- 환산률: F열 총환산월초 값을 1차년~4차년에 동일 저장
- Excel % 셀은 number_format에 "%"가 있으면 ×100 보정하여 백분율 수치로 저장한다.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl.workbook.workbook import Workbook

from commission.models import RateExample, RateExampleConversionRow


TARGET_SHEET_NAME = "주계약(종속특약포함)"

# 주요기능: 교보 종신보험 테이블 고정 컬럼 매핑
# B5~F5는 헤더이므로 실제 데이터는 6행부터 처리한다.
DATA_START_ROW = 6
PRODUCT_COL = 2      # B: 상품명
PAY_PERIOD_COL = 4   # D: 납입기간
PLAN_TYPE_COL = 5    # E: 월납보험료
RATE_COL = 6         # F: 총환산월초

COVERAGE_TYPE = "종신/CI"


def _text(value: Any) -> str:
    """Excel 셀 값을 문자열로 안전하게 정규화한다."""
    if value is None:
        return ""
    return str(value).strip()


def _should_exclude(product_name: str) -> bool:
    """
    상품명에 판매중지 또는 특약이 포함되어 있는지 판정한다.
    해당 상품 및 그 하위 공란 행은 정규화에서 제외한다.
    """
    name = _text(product_name)
    return "판매중지" in name or "특약" in name


def _is_subtype_keyword(value: str) -> bool:
    """
    B열 값이 상품명이 아니라 직전 상품명의 서브타입 키워드인지 판정한다.
    판정 기준: 문자열 전체가 "(" 로 시작하고 ")" 로 끝나는 경우.
    예: "(기본형)", "(체증형)" → True
    예: "교보K-밸류업종신보험(무배당)(베이직형)" → False (앞에 다른 문자 있음)
    """
    v = value.strip()
    return v.startswith("(") and v.endswith(")")


def _to_decimal_percent(cell) -> Decimal | None:
    """
    총환산월초 셀 값을 DB 저장 정책에 맞는 백분율 수치 Decimal로 변환한다.

    예:
    - Excel 표시 150%, 실제 value=1.5, number_format="0%" → Decimal("150")
    - 일반 숫자 150 → Decimal("150")
    """
    value = getattr(cell, "value", None)
    if value is None or value == "":
        return None

    try:
        dec = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None

    number_format = str(getattr(cell, "number_format", "") or "")
    if "%" in number_format:
        dec = dec * Decimal("100")

    return dec


def _last_rate_row(ws) -> int:
    """
    주요기능: F열(총환산월초)의 마지막 데이터 행을 찾는다.
    """
    for row_no in range(ws.max_row, DATA_START_ROW - 1, -1):
        if _to_decimal_percent(ws.cell(row_no, RATE_COL)) is not None:
            return row_no
    return DATA_START_ROW - 1


def build_life_kyobo_conversion_rows(
    example: RateExample,
    wb: Workbook,
) -> list[RateExampleConversionRow]:
    """
    교보 생명보험 환산율/수정률 정규화 row 객체 목록을 생성한다.

    저장/replace/append 처리는 rate_example_normalizer.normalize_rate_example()이 담당한다.
    """
    if TARGET_SHEET_NAME not in wb.sheetnames:
        return []

    ws = wb[TARGET_SHEET_NAME]
    end_row = _last_rate_row(ws)

    rows: list[RateExampleConversionRow] = []

    last_product_name = ""
    last_product_is_stopped = False

    for row_no in range(DATA_START_ROW, end_row + 1):
        product_raw = _text(ws.cell(row_no, PRODUCT_COL).value)
        pay_period = _text(ws.cell(row_no, PAY_PERIOD_COL).value)
        plan_type = _text(ws.cell(row_no, PLAN_TYPE_COL).value)
        rate_value = _to_decimal_percent(ws.cell(row_no, RATE_COL))

        # 주요기능: 총환산월초가 없는 행은 정규화 대상이 아니다.
        if rate_value is None:
            continue

        # 주요기능: 상품명 공란 시 상단의 마지막 상품명을 전파한다.
        # 주요기능: "(기본형)"/"(체증형)" 등 괄호형 단독 키워드는
        #           직전 상품명의 서브타입으로 보고 상품명에 합성한다.
        #           예) "교보하이브리드변액종신보험(무배당)_판매중지" + "(체증형)"
        #             → "교보하이브리드변액종신보험(무배당)_판매중지(체증형)"
        if product_raw:
            if _is_subtype_keyword(product_raw):
                # 서브타입 키워드: 직전 상품명 뒤에 합성하여 새 상품명으로 교체
                current_product_name = last_product_name + product_raw
                current_product_is_stopped = _should_exclude(current_product_name)
            else:
                current_product_name = product_raw
                current_product_is_stopped = _should_exclude(product_raw)

            last_product_name = current_product_name
            last_product_is_stopped = current_product_is_stopped
        else:
            current_product_name = last_product_name
            current_product_is_stopped = last_product_is_stopped

        if not current_product_name:
            continue

        # 주요기능: 판매중지/특약 상품 및 그 하위 공란 행 제외
        if current_product_is_stopped:
            continue

        rows.append(
            RateExampleConversionRow(
                source_file=example,
                source_sheet=TARGET_SHEET_NAME,
                source_row_no=row_no,
                insurer_type=example.insurer_type,
                category=example.category,
                insurer="교보",
                coverage_type=COVERAGE_TYPE,
                strategy_flag="",
                product_name=current_product_name,
                plan_type=plan_type,
                pay_period=pay_period,
                year1=rate_value,
                year2=rate_value,
                year3=rate_value,
                year4=rate_value,
            )
        )

    return rows