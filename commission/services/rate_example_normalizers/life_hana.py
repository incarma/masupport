# django_ma/commission/services/rate_example_normalizers/life_hana.py
from __future__ import annotations

"""
하나생명 PDF 환산율 정규화 normalizer.

대상:
- 생명보험 / 환산율·수정률 / 하나 / PDF
- raw PDF 첫 번째 페이지만 정규화한다.

정규화 규칙:
- 보험사: "하나"
- PDF 첫 번째 페이지의 표만 사용
- PDF 테이블에서 병합/공백으로 표현된 셀은 상단 값을 carry-down 하여 전개
- 줄바꿈 텍스트:
  - 상품명: 줄을 한 줄로 결합
  - 심사유형: 줄을 ", "로 결합
  - 상품유형: 줄을 " "로 결합
- 상품명 = 상품명 + " (" + 심사유형 + ")"
- 구분 = 상품유형
- 납기 = raw 데이터의 납입기간 컬럼
- 1차년/2차년/3차년~ → year1/year2/year3
- 4차년은 3차년~ 값을 동일 저장
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example_normalizers._common import (
    clean_spaces,
    decimal_from_text,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HanaPdfLine:
    y: float
    x: float
    text: str


HEADER_ALIASES = {
    "product_name": ("상품명",),
    "plan_type": ("상품유형",),
    "review_type": ("심사유형",),
    "pay_period": ("납입기간", "납기"),
    "year1": ("1차년",),
    "year2": ("2차년",),
    "year3": ("3차년~", "3차년"),
}

SKIP_ROW_KEYWORDS = {
    "구분",
    "상품명",
    "상품유형",
    "심사유형",
    "납입기간",
    "환산율",
    "비고",
}


def build_life_hana_pdf_conversion_rows(
    example: RateExample,
) -> list[RateExampleConversionRow]:
    """
    하나생명 PDF 첫 번째 페이지를 RateExampleConversionRow 리스트로 변환한다.

    주의:
    - 파일 접근은 example.file.path만 사용한다.
    - DB 저장은 호출부(normalize_rate_example)가 담당한다.
    - 파싱 실패는 조용히 삼키지 않고 예외를 raise하여 transaction rollback을 보장한다.
    """
    if not example.file:
        return []

    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError(
            "하나생명 PDF 정규화에는 PyMuPDF(fitz)가 필요합니다."
        ) from exc

    rows: list[RateExampleConversionRow] = []

    doc = fitz.open(example.file.path)
    try:
        if doc.page_count < 1:
            return []

        page = doc[0]

        table_rows = _extract_first_page_table_rows(page)
        if not table_rows:
            rows = _build_rows_from_page_lines(example, page)
            if rows:
                return rows
            logger.warning("Hana PDF table not detected: file=%s", getattr(example, "original_name", ""))
            return []
        
        header_idx, colmap = _find_header_and_columns(table_rows)
        if header_idx < 0:
            rows = _build_rows_from_page_lines(example, page)
            if rows:
                return rows
            logger.warning("Hana PDF header not detected: file=%s", getattr(example, "original_name", ""))
            return []

        data_rows = _fill_merged_like_cells(table_rows[header_idx + 1 :])

        source_row_no = 1
        for raw_row in data_rows:
            parsed = _parse_table_row(raw_row, colmap)
            if parsed is None:
                continue

            product_name, plan_type, pay_period, y1, y2, y3 = parsed

            rows.append(
                RateExampleConversionRow(
                    source_file=example,
                    source_sheet="PDF Page 1",
                    source_row_no=source_row_no,
                    insurer_type=example.insurer_type,
                    category=example.category,
                    insurer="하나",
                    coverage_type=_infer_coverage_type(product_name),
                    strategy_flag="",
                    product_name=product_name,
                    plan_type=plan_type,
                    pay_period=pay_period,
                    year1=y1,
                    year2=y2,
                    year3=y3,
                    year4=y3,
                )
            )
            source_row_no += 1

    finally:
        doc.close()

    return rows


def _build_rows_from_page_lines(
    example: RateExample,
    page,
) -> list[RateExampleConversionRow]:
    """
    하나생명 PDF의 복합 헤더/시각적 병합 구조 대응 fallback.
    납입기간 텍스트를 anchor로 row를 만들고, 같은 y-band의 상품명/상품유형/심사유형/환산율을 결합한다.
    """
    lines = _extract_pdf_lines(page)
    if not lines:
        return []

    pay_lines = [
        line for line in lines
        if 340 <= line.x <= 410 and _looks_like_pay_period(line.text)
    ]
    pay_lines.sort(key=lambda line: (line.y, line.x))

    rows: list[RateExampleConversionRow] = []
    carry_division = ""
    carry_product = ""
    carry_plan = ""
    carry_review = ""
    prev_y = 70.0
    source_row_no = 1

    for pay_line in pay_lines:
        y = pay_line.y
        band = [
            line for line in lines
            if prev_y + 0.1 <= line.y <= y + 8.5
        ]

        division = _join_col_text(band, 35, 90, sep=" ")
        product = _join_col_text(band, 90, 205, sep="")
        plan_type = _join_col_text(band, 205, 275, sep=" ")
        review_type = _join_col_text(band, 275, 345, sep=", ")

        if division:
            carry_division = division
        if product:
            carry_product = product
        if plan_type:
            carry_plan = plan_type
        if review_type:
            carry_review = review_type

        if not carry_product:
            prev_y = y
            continue

        if "판매중지" in carry_product or "특약" in carry_product:
            prev_y = y
            continue

        y1 = _nearest_percent(lines, y, 405, 448)
        y2 = _nearest_percent(lines, y, 448, 485)
        y3 = _nearest_percent(lines, y, 485, 525)

        if y1 is None and y2 is None and y3 is None:
            prev_y = y
            continue

        product_name = carry_product
        if carry_review:
            product_name = f"{product_name} ({carry_review})"

        rows.append(
            RateExampleConversionRow(
                source_file=example,
                source_sheet="PDF Page 1",
                source_row_no=source_row_no,
                insurer_type=example.insurer_type,
                category=example.category,
                insurer="하나",
                coverage_type=_infer_coverage_type(product_name),
                strategy_flag="",
                product_name=product_name,
                plan_type=carry_plan,
                pay_period=_clean_cell(pay_line.text),
                year1=y1,
                year2=y2,
                year3=y3,
                year4=y3,
            )
        )
        source_row_no += 1
        prev_y = y

    logger.info(
        "Hana PDF coordinate fallback parsed rows=%s file=%s",
        len(rows),
        getattr(example, "original_name", ""),
    )
    return rows


def _extract_pdf_lines(page) -> list[HanaPdfLine]:
    data = page.get_text("dict")
    lines: list[HanaPdfLine] = []

    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            texts = []
            for span in line.get("spans", []):
                text = _clean_cell(span.get("text", ""))
                if text:
                    texts.append(text)
            text = _clean_cell("".join(texts))
            if not text:
                continue
            x0, y0, *_ = line.get("bbox", [0, 0, 0, 0])
            lines.append(HanaPdfLine(y=float(y0), x=float(x0), text=text))

    return sorted(lines, key=lambda line: (line.y, line.x))


def _join_col_text(
    lines: list[HanaPdfLine],
    x_min: float,
    x_max: float,
    *,
    sep: str,
) -> str:
    selected = [
        line for line in lines
        if x_min <= line.x < x_max
        and "%" not in line.text
        and not _looks_like_pay_period(line.text)
        and not _is_noise_row(line.text)
    ]
    selected.sort(key=lambda line: (line.y, line.x))

    parts = [_clean_inline(line.text) for line in selected]
    parts = [part for part in parts if part]
    if not parts:
        return ""

    value = sep.join(parts)
    value = re.sub(r"\s{2,}", " ", value)
    value = value.replace("( ", "(").replace(" )", ")")
    return value.strip()


def _nearest_percent(
    lines: list[HanaPdfLine],
    y: float,
    x_min: float,
    x_max: float,
) -> Decimal | None:
    candidates = [
        line for line in lines
        if x_min <= line.x < x_max
        and abs(line.y - y) <= 2.2
        and "%" in line.text
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda line: abs(line.y - y))
    return _to_decimal_percent(candidates[0].text)


def _looks_like_pay_period(value: object) -> bool:
    text = _clean_cell(value)
    if not text:
        return False
    return bool(re.search(r"(?:\d+년납|전기납|일시납|전납기|非일시납)", text))


def _extract_first_page_table_rows(page) -> list[list[str]]:
    """
    PyMuPDF table detector로 첫 페이지 표를 추출한다.

    PDF에는 실제 Excel 병합셀 정보가 없으므로, table detector가 반환한
    빈 셀을 이후 carry-down 방식으로 전개한다.
    """
    finder = getattr(page, "find_tables", None)
    if finder is None:
        raise RuntimeError(
            "현재 PyMuPDF 버전이 page.find_tables()를 지원하지 않습니다. "
            "PyMuPDF 1.23 이상을 사용해 주세요."
        )

    tables = finder()
    candidates = getattr(tables, "tables", None) or []
    if not candidates:
        return []

    extracted: list[list[list[str]]] = []
    for table in candidates:
        matrix = table.extract()
        normalized = [_normalize_row(row) for row in matrix]
        if _looks_like_hana_table(normalized):
            extracted.append(normalized)

    if not extracted:
        return []

    # 첫 페이지에 여러 테이블이 잡히면 가장 많은 행을 가진 표를 사용한다.
    extracted.sort(key=len, reverse=True)
    return extracted[0]


def _normalize_row(row: Iterable[object]) -> list[str]:
    return [_clean_cell(v) for v in row]


def _looks_like_hana_table(rows: list[list[str]]) -> bool:
    joined = "\n".join(" ".join(row) for row in rows[:10])
    return (
        "상품명" in joined
        and "상품유형" in joined
        and "심사유형" in joined
        and ("납입기간" in joined or "납기" in joined)
        and "1차년" in joined
        and "2차년" in joined
    )


def _find_header_and_columns(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
    for idx, row in enumerate(rows):
        colmap: dict[str, int] = {}
        for col_idx, cell in enumerate(row):
            compact = _compact(cell)
            for key, aliases in HEADER_ALIASES.items():
                if key in colmap:
                    continue
                if any(_compact(alias) in compact for alias in aliases):
                    colmap[key] = col_idx

        required = {"product_name", "plan_type", "review_type", "pay_period", "year1", "year2", "year3"}
        if required.issubset(colmap):
            return idx, colmap

    return -1, {}


def _fill_merged_like_cells(rows: list[list[str]]) -> list[list[str]]:
    """
    PDF table detector의 병합 셀/시각적 병합 셀은 빈 문자열로 내려오는 경우가 많다.
    상품명/상품유형/심사유형/납입기간은 상단 값을 carry-down 하여 실제 구획 단위로 전개한다.

    환산율 컬럼은 carry-down하지 않는다.
    """
    if not rows:
        return rows

    max_cols = max(len(r) for r in rows)
    filled: list[list[str]] = []
    carry = [""] * max_cols

    for row in rows:
        current = list(row) + [""] * (max_cols - len(row))

        for idx, value in enumerate(current):
            value = _clean_cell(value)
            if value:
                carry[idx] = value
                current[idx] = value
            else:
                # 앞쪽 텍스트성 컬럼만 carry-down.
                # 숫자 환산율 컬럼까지 carry-down하면 잘못된 중복 row가 생긴다.
                if idx < max_cols - 3:
                    current[idx] = carry[idx]

        filled.append(current)

    return filled


def _parse_table_row(
    row: list[str],
    colmap: dict[str, int],
) -> tuple[str, str, str, Decimal | None, Decimal | None, Decimal | None] | None:
    product_raw = _get(row, colmap["product_name"])
    plan_raw = _get(row, colmap["plan_type"])
    review_raw = _get(row, colmap["review_type"])
    pay_period = _join_lines(_get(row, colmap["pay_period"]), sep=" ")

    y1 = _to_decimal_percent(_get(row, colmap["year1"]))
    y2 = _to_decimal_percent(_get(row, colmap["year2"]))
    y3 = _to_decimal_percent(_get(row, colmap["year3"]))

    product = _join_lines(product_raw, sep="")
    plan_type = _join_lines(plan_raw, sep=" ")
    review_type = _join_lines(review_raw, sep=", ")

    if not product or not pay_period:
        return None

    if _is_noise_row(product, plan_type, review_type, pay_period):
        return None

    # 최소 하나 이상의 환산율이 있어야 정규화 row로 인정한다.
    if y1 is None and y2 is None and y3 is None:
        return None

    product_name = product
    if review_type:
        product_name = f"{product_name} ({review_type})"

    return product_name, plan_type, pay_period, y1, y2, y3


def _get(row: list[str], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    return _clean_cell(row[idx])


def _clean_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def _join_lines(value: object, *, sep: str) -> str:
    text = _clean_cell(value)
    if not text:
        return ""

    parts = [_clean_inline(part) for part in text.split("\n")]
    parts = [p for p in parts if p]

    if not parts:
        return ""

    joined = sep.join(parts)
    joined = re.sub(r"\s{2,}", " ", joined)
    joined = joined.replace("( ", "(").replace(" )", ")")
    return joined.strip()


def _clean_inline(value: str) -> str:
    return clean_spaces(value)


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _to_decimal_percent(value: object) -> Decimal | None:
    text = _clean_cell(value)
    if not text:
        return None

    # "-", "–" 등은 비율 없음으로 본다.
    if text.strip() in {"-", "–", "—"}:
        return None

    # PDF 추출 중 주석/비고가 섞이는 경우 첫 번째 퍼센트 또는 숫자만 사용.
    m = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    if not m:
        return None

    return decimal_from_text(m.group(0))


def _infer_coverage_type(product_name: str) -> str:
    name = product_name or ""

    if "종신" in name:
        return "종신/CI"

    if "연금" in name and "변액" in name:
        return "변액연금"

    if "연금" in name:
        return "연금"

    return "기타(보장성)"


def _is_noise_row(*values: str) -> bool:
    joined = " ".join(values)
    compact = _compact(joined)

    if not compact:
        return True

    if compact in {_compact(v) for v in SKIP_ROW_KEYWORDS}:
        return True

    # 표 제목/기준일/비고성 행 방어
    if "하나생명GA채널상품별환산율" in compact:
        return True
    if "2026.4.1.기준" in compact:
        return True
    if compact.startswith("※"):
        return True

    return False