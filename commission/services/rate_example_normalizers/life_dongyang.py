# django_ma/commission/services/rate_example_normalizers/life_dongyang.py
from __future__ import annotations

"""
동양생명 RateExample 환산율 정규화 parser.

역할:
- '환산율 업데이트' 모달에서 보험사='동양' 선택 후 업로드된 raw xlsx를
  RateExampleConversionRow 표준 스키마로 변환한다.

정규화 정책:
- 대상 시트: '주계약' only
- 제외 영역: 1~14행
- 보험사: '동양' 고정
- 상품: 대표상품명(B열)
- 보종:
  - 상품명에 '종신' 포함 → '종신/CI'
  - 상품명에 '연금' 포함 → '연금'
  - 그 외 → '기타(보장성)'
- 구분: 세부상품명(C열) 중 첫 번째 '_' 뒤 텍스트
- 납기: 납입기간(G열)
- 환산률:
  - 1차년: 초년도 환산 변경후(J열)
  - 2~4차년: 차년도 환산 변경후(L열)

주의:
- DB 저장값은 백분율 수치 기준이다.
  예: Excel 표시 70% → openpyxl value 0.7 → DB Decimal("70")
"""

from decimal import Decimal, InvalidOperation

from commission.models import RateExampleConversionRow

TARGET_SHEET_NAME = "주계약"
INSURER_NAME = "동양"

# raw 컬럼 번호
COL_PRODUCT_NAME = 2      # B: 대표상품명
COL_DETAIL_NAME = 3       # C: 세부상품명
COL_PAY_PERIOD = 7        # G: 납입기간
COL_YEAR1_AFTER = 10      # J: 초년도 환산 변경후
COL_NEXT_AFTER = 12       # L: 차년도 환산 변경후

DATA_START_ROW = 15


def _text(value) -> str:
    """
    Excel cell value를 안전한 문자열로 변환한다.
    None은 공란으로 처리하고, 앞뒤 공백을 제거한다.
    """
    if value is None:
        return ""
    return str(value).strip()


def _coverage_type(product_name: str) -> str:
    """
    동양 보종 판정 정책.

    우선순위:
    1. 종신
    2. 연금
    3. 기타(보장성)
    """
    name = _text(product_name)

    if "종신" in name:
        return "종신/CI"
    if "연금" in name:
        return "연금"
    return "기타(보장성)"


def _plan_type_from_detail(detail_name: str) -> str:
    """
    세부상품명(C열)에서 첫 번째 언더스코어(_) 뒤 텍스트를 구분값으로 사용한다.

    예:
    '상품명_보장형_평준납입형' → '보장형_평준납입형'

    '_'가 없으면 구분을 안정적으로 만들 수 없으므로 공란 저장한다.
    """
    detail = _text(detail_name)
    if "_" not in detail:
        return ""
    return detail.split("_", 1)[1].strip()


def _to_decimal_percent(cell) -> Decimal | None:
    """
    Excel 환산률 cell을 DB 저장용 백분율 수치 Decimal로 변환한다.

    정책:
    - Excel 서식에 '%'가 있으면 openpyxl value에 100을 곱한다.
      예: 0.7 + '0%' → 70
    - 서식에 '%'가 없으면 원 숫자를 그대로 사용한다.
    - 빈 값/문자 변환 실패는 None으로 처리한다.
    """
    value = getattr(cell, "value", None)
    if value is None or value == "":
        return None

    try:
        dec = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None

    number_format = getattr(cell, "number_format", "") or ""
    if "%" in number_format:
        dec = dec * Decimal("100")

    # 기존 모달 표시 정책과 맞추기 위해 불필요한 지수 표기만 제거한다.
    return dec.normalize() if dec == dec.to_integral() else dec


def _has_any_rate(year1: Decimal | None, next_year: Decimal | None) -> bool:
    """
    1차년/차년도 환산률이 모두 비어 있으면 정규화 대상에서 제외한다.
    """
    return year1 is not None or next_year is not None


def build_life_dongyang_conversion_rows(example, workbook) -> list[RateExampleConversionRow]:
    """
    동양생명 raw workbook을 RateExampleConversionRow 리스트로 변환한다.

    반환만 담당하고 DB 저장/삭제/transaction은 상위 normalizer가 담당한다.
    """
    if TARGET_SHEET_NAME not in workbook.sheetnames:
        raise ValueError(f"동양 정규화 대상 시트를 찾을 수 없습니다: {TARGET_SHEET_NAME}")

    ws = workbook[TARGET_SHEET_NAME]
    rows: list[RateExampleConversionRow] = []

    current_product_name = ""

    for row_no in range(DATA_START_ROW, ws.max_row + 1):
        raw_product_name = _text(ws.cell(row_no, COL_PRODUCT_NAME).value)
        detail_name = _text(ws.cell(row_no, COL_DETAIL_NAME).value)
        pay_period = _text(ws.cell(row_no, COL_PAY_PERIOD).value)

        # 대표상품명(B열)은 병합/공란으로 내려오는 경우가 있어 직전 상품명을 전파한다.
        if raw_product_name:
            current_product_name = raw_product_name

        product_name = current_product_name

        # 상품명 또는 세부상품명이 없으면 실제 상품 row로 보기 어렵다.
        if not product_name or not detail_name:
            continue

        year1 = _to_decimal_percent(ws.cell(row_no, COL_YEAR1_AFTER))
        next_year = _to_decimal_percent(ws.cell(row_no, COL_NEXT_AFTER))

        # 환산률이 전부 비어 있는 헤더/비고/공란 행 방어.
        if not _has_any_rate(year1, next_year):
            continue

        rows.append(
            RateExampleConversionRow(
                source_file=example,
                source_sheet=TARGET_SHEET_NAME,
                source_row_no=row_no,
                insurer_type=example.insurer_type,
                category=example.category,
                insurer=INSURER_NAME,
                coverage_type=_coverage_type(product_name),
                product_name=product_name,
                plan_type=_plan_type_from_detail(detail_name),
                pay_period=pay_period,
                year1=year1,
                year2=next_year,
                year3=next_year,
                year4=next_year,
            )
        )

    return rows