# commission/services/rate_example_normalizers/life_cardif.py
from __future__ import annotations

"""
BNP파리바 카디프생명 PDF 환산율 정규화 parser.

정책:
- PDF 주계약 영역만 정규화한다.
- "□ 특약" 이후 테이블은 전부 제외한다.
- PDF raw 환산율(%) 값에 12를 곱해 정규화 테이블에 저장한다.
  예: 70.0% -> Decimal("840.0000")
- 파일 URL 직접 접근 없이 example.file.open("rb")만 사용한다.
"""

import logging
import os
import re
from decimal import Decimal, ROUND_HALF_UP
from tempfile import NamedTemporaryFile

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example_normalizers._common import (
    append_unique,
    clean_spaces,
    decimal_from_text,
)

logger = logging.getLogger(__name__)

INSURER = "카디프"
DEC4 = Decimal("0.0001")
MULTIPLIER = Decimal("12")
NO_PLAN_TYPE = "사용안함"


def _clean_text(value) -> str:
    return clean_spaces(value)


def _header_key(value: str) -> str:
    return re.sub(r"\s+", "", _clean_text(value))


def _to_decimal_x12(value):
    raw = decimal_from_text(value)
    if raw is None:
        return None

    return (raw * MULTIPLIER).quantize(DEC4, rounding=ROUND_HALF_UP)


def _coverage_type(product_name: str) -> str:
    name = product_name or ""

    if "연금" in name and "변액" in name:
        return "변액연금"
    if "연금" in name:
        return "연금"
    if "경영" in name:
        return "CEO정기"
    return "기타(보장성)"


def _normalize_plan_type(value: str, *, has_plan_col: bool) -> str:
    """
    카디프 구분(plan_type) 정규화.

    PDF raw에서 '체증형' 컬럼이 없는 상품은 기존에는 plan_type=""로 저장됐다.
    그러나 계산 입력 UI는 보험사 → 상품명 → 구분 → 납기 순서로 옵션을 조회하므로,
    공란 plan_type은 options API의 빈 값 제거 정책에 의해 선택지로 반환되지 않는다.

    따라서 카디프에 한해 체증형이 없는 row는 '사용안함' sentinel로 저장한다.
    계산 서비스는 '사용안함'을 빈 구분값과 동일하게 흡수한다.
    """
    text = _clean_text(value)
    if has_plan_col and text:
        return text
    return NO_PLAN_TYPE


def _normalize_pay_period(pay: str, maturity: str = "") -> str:
    pay = _clean_text(pay)
    maturity = _clean_text(maturity)

    if not pay and not maturity:
        return ""

    # 전기납(60세 미만), 5년납, 10년납 등은 원문 유지
    if not maturity:
        return pay

    if pay and not pay.endswith("납"):
        pay = f"{pay}납"

    if maturity and not maturity.endswith("만기"):
        maturity = f"{maturity} 만기"

    return f"{pay}, {maturity}".strip(", ")


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return _clean_text(row[idx])


def _find_col(
    rows: list[list[str]],
    *tokens: str,
    start: int = 0,
    limit: int = 4,
) -> int | None:
    for row in rows[start : start + limit]:
        for idx, value in enumerate(row):
            key = _header_key(value)
            if key and all(token in key for token in tokens):
                return idx
    return None


def _find_year_cols(rows: list[list[str]], start: int = 0, limit: int = 5) -> dict[str, int]:
    found: dict[str, int] = {}
    mapping = {
        "year1": "1차년",
        "year2": "2차년",
        "year3": "3차년",
        "year4": "4차년",
    }

    for row in rows[start : start + limit]:
        for idx, value in enumerate(row):
            key = _header_key(value)
            for field, token in mapping.items():
                if field not in found and token in key:
                    found[field] = idx

    return found


def _find_header_idx(rows: list[list[str]]) -> int | None:
    for idx, row in enumerate(rows):
        joined = " ".join(_clean_text(c) for c in row)
        key = _header_key(joined)

        if "상품" in key and ("환산율" in key or "1차년" in key):
            return idx

    return None


def _is_skip_row(row: list[str]) -> bool:
    joined = " ".join(_clean_text(c) for c in row)
    key = _header_key(joined)

    if not key:
        return True
    if "적용일" in key or "Classification" in joined or re.fullmatch(r"\d+/5", key):
        return True
    if "상 품" in joined or "상품코드" in key or "환산율" in key:
        return True

    return False


def _table_has_special_rider(table: list[list[str]]) -> bool:
    joined = " ".join(_clean_text(c) for row in table for c in row)
    key = _header_key(joined)

    if "□특약" in key:
        return True

    # 특약 섹션/특약 테이블 방어
    if "특약" in joined and "주계약" not in joined:
        return True

    return False


def _write_temp_pdf(example: RateExample) -> str:
    with example.file.open("rb") as src, NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            tmp.write(chunk)
        return tmp.name


def build_life_cardif_pdf_conversion_rows(example: RateExample) -> list[RateExampleConversionRow]:
    """
    카디프 PDF raw 환산율을 RateExampleConversionRow 목록으로 변환한다.

    year1~year4 저장 정책:
    - PDF raw % 값에 12를 곱한다.
    - 예: 70.0% -> Decimal("840.0000")
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "카디프 PDF 정규화에는 pdfplumber>=0.11.0 패키지가 필요합니다."
        ) from exc

    tmp_path = _write_temp_pdf(example)
    rows: list[RateExampleConversionRow] = []

    try:
        with pdfplumber.open(tmp_path) as pdf:
            stop_all = False

            for page_idx, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if "□ 특약" in page_text:
                    stop_all = True

                tables = page.extract_tables(
                    table_settings={
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 3,
                        "join_tolerance": 3,
                        "intersection_tolerance": 5,
                        "text_x_tolerance": 2,
                        "text_y_tolerance": 3,
                    }
                ) or []

                for table_idx, table in enumerate(tables, start=1):
                    table_rows = [[_clean_text(c) for c in row] for row in table if row]
                    if not table_rows:
                        continue

                    # page 3의 특약 이후 테이블 및 특약명 포함 테이블 제외
                    if _table_has_special_rider(table_rows):
                        continue

                    header_idx = _find_header_idx(table_rows)
                    if header_idx is None:
                        continue

                    product_col = _find_col(table_rows, "상품", start=header_idx)
                    code_col = _find_col(table_rows, "상품코드", start=header_idx)
                    plan_col = _find_col(table_rows, "체증형", start=header_idx)
                    pay_col = _find_col(table_rows, "납기", start=header_idx)
                    maturity_col = _find_col(table_rows, "만기", start=header_idx)
                    year_cols = _find_year_cols(table_rows, start=header_idx)

                    # 일시납 단일 환산율 테이블
                    single_rate_col = None
                    if not year_cols:
                        single_rate_col = _find_col(table_rows, "환산율", start=header_idx)

                    current_product = ""
                    current_code = ""
                    current_plan = ""
                    current_pay = ""
                    current_maturity = ""

                    data_start = header_idx + 1
                    for row_no, row in enumerate(table_rows[data_start:], start=data_start + 1):
                        if _is_skip_row(row):
                            continue

                        product = _cell(row, product_col)
                        code = _cell(row, code_col)
                        plan = _cell(row, plan_col)
                        pay = _cell(row, pay_col)
                        maturity = _cell(row, maturity_col)

                        if product:
                            current_product = product
                        if code:
                            current_code = code
                        if plan:
                            current_plan = plan
                        if pay:
                            current_pay = pay
                        if maturity:
                            current_maturity = maturity

                        product_name = current_product
                        if not product_name or "특약" in product_name:
                            continue

                        # 상품명 셀에 상품코드까지 섞이는 경우 방어적으로 정리
                        product_name = re.sub(r"\s+\d{3,5}(\s|$)", " ", product_name).strip()
                        if not product_name or "특약" in product_name:
                            continue

                        plan_type = _normalize_plan_type(
                            current_plan,
                            has_plan_col=(plan_col is not None),
                        )

                        if single_rate_col is not None:
                            pay_period = "일시납"
                            y1 = _to_decimal_x12(_cell(row, single_rate_col))
                            if y1 is None:
                                continue
                            y2 = y3 = y4 = None
                        else:
                            pay_period = _normalize_pay_period(
                                current_pay,
                                current_maturity if maturity_col is not None else "",
                            )
                            if not pay_period:
                                continue

                            y1 = _to_decimal_x12(_cell(row, year_cols.get("year1")))
                            y2 = _to_decimal_x12(_cell(row, year_cols.get("year2")))
                            y3 = _to_decimal_x12(_cell(row, year_cols.get("year3")))
                            y4 = _to_decimal_x12(_cell(row, year_cols.get("year4")))

                            if y1 is None and y2 is None and y3 is None and y4 is None:
                                continue

                        rows.append(
                            RateExampleConversionRow(
                                source_file=example,
                                source_sheet=f"PDF p{page_idx} table{table_idx}",
                                source_row_no=(page_idx * 1000) + row_no,
                                insurer_type=example.insurer_type,
                                category=example.category,
                                insurer=INSURER,
                                coverage_type=_coverage_type(product_name),
                                strategy_flag="",
                                product_name=product_name,
                                plan_type=plan_type,
                                pay_period=pay_period,
                                year1=y1,
                                year2=y2,
                                year3=y3,
                                year4=y4,
                            )
                        )

                if stop_all:
                    break

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            logger.warning("카디프 PDF 임시파일 삭제 실패: %s", tmp_path, exc_info=True)

    # PDF 테이블 추출 특성상 중복 행이 잡힐 수 있어 최종 dedupe
    deduped: list[RateExampleConversionRow] = []
    seen: set[tuple] = set()

    for row in rows:
        key = (
            row.product_name,
            row.plan_type,
            row.pay_period,
            row.year1,
            row.year2,
            row.year3,
            row.year4,
        )
        append_unique(deduped, seen, row, key)

    return deduped