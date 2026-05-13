# django_ma/commission/services/rate_example_normalizers/life_fubon.py
from __future__ import annotations

"""
푸본현대생명 PDF 환산율 정규화.

규칙:
- 보험사 컬럼은 "푸본현대"로 고정한다.
- PDF 내 "■" 상품 블록 제목을 정규화 상품명으로 사용한다.
- 다음 "■" 상품 블록 전까지는 직전 상품명을 전파한다.
- 상품명/테이블 행 라벨에 "특약", "패키지"가 포함된 행은 제외한다.
  단, "주계약/특약 동일"은 푸본현대 정기보험 스마트픽 주계약 표기이므로 포함한다.
- 구분은 상품유형 컬럼 우선, 상품유형이 없으면 보험기간을 사용한다.
- 상품유형이 둘로 분리된 표는 우측 상품유형에 해당하는 실제 가입유형을 사용한다.
- 초년도는 year1, 차년도는 year2/year3/year4에 동일 저장한다.
"""

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Iterable

from commission.models import RateExample, RateExampleConversionRow

logger = logging.getLogger(__name__)


_RATE_ROW_RE = re.compile(
    r"^(?P<prefix>.*?)\s+"
    r"(?P<total>\d+(?:\.\d+)?)%\s+"
    r"(?P<year1>\d+(?:\.\d+)?)%\s+"
    r"(?P<next_year>\d+(?:\.\d+)?)%\s*$"
)

_PAY_PERIOD_RE = re.compile(
    r"(?P<pay>\d+\s*년\s*납(?:\s*이상)?|\d+년납(?:이상)?|\d+년갱신|전기납)"
)

_TERM_RE = re.compile(
    r"(?P<term>\d+\s*년\s*만기|\d+년만기|\d+\s*~\s*\d+\s*년|\d+~\d+년|\d+년이상|종신)"
)

_BULLET_RE = re.compile(r"^■\s*(?P<title>.+?)\s*$")

_SECTION_NOISE = {
    "- 주계약",
    "- 선택특약",
    "- 주계약/선택특약 패키지",
    "- 주계약 및 선택특약",
    "- 끝",
}


def _extract_pdf_text(path: str) -> str:
    """
    PDF 텍스트 추출.

    우선순위:
    1. pdfplumber
    2. PyMuPDF(fitz)
    3. pypdf

    기존 PDF normalizer와 충돌하지 않도록 이 파일 내부 fallback으로 격리한다.
    """
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(path) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        logger.debug("pdfplumber extraction failed for fubon pdf", exc_info=True)

    try:
        import fitz  # type: ignore

        doc = fitz.open(path)
        try:
            return "\n".join(page.get_text("text") for page in doc)
        finally:
            doc.close()
    except Exception:
        logger.debug("PyMuPDF extraction failed for fubon pdf", exc_info=True)

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        logger.exception("Fubon PDF text extraction failed: path=%s", path)
        raise


def _clean_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\uFFFE", " ")
    text = text.replace("\u200b", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_product_title(raw: str) -> str:
    title = _clean_text(raw)
    title = re.sub(r"\s*-\s*(주계약|선택특약|주계약 및 선택특약).*$", "", title)
    return title.strip()


def _coverage_type(product_name: str) -> str:
    if "종신" in product_name or "정기" in product_name:
        return "종신/CI"
    if "연금" in product_name:
        return "연금"
    return "기타(보장성)"


def _to_decimal_percent(value: str) -> Decimal | None:
    text = _clean_text(value).replace(",", "")
    if not text:
        return None

    try:
        return Decimal(text).quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError):
        return None


def _is_header_or_noise(line: str) -> bool:
    if not line:
        return True
    if line in _SECTION_NOISE:
        return True
    if line.startswith("GA채널"):
        return True
    if line.startswith("(") and line.endswith(")"):
        return True
    if line.startswith("※"):
        return True
    if "환산성적" in line:
        return True
    if line in {"TOTAL", "Total", "초년도", "차년도"}:
        return True
    if line.startswith("상품명"):
        return True
    return False


def _is_excluded_label(label: str) -> bool:
    text = _clean_text(label)
    if "주계약/특약 동일" in text:
        return False
    return "특약" in text or "패키지" in text


def _split_rate_prefix(prefix: str, current_plan_type: str) -> tuple[str, str]:
    """
    환산율 행의 rate 앞 prefix에서 구분과 납기를 분리한다.

    예:
    - "1형(연금액강화형) 5년납" -> ("1형(연금액강화형)", "5년납")
    - "10년만기 10년납" -> ("10년만기", "10년납")
    - "일반 가입 10년납" -> ("일반 가입", "10년납")
    """
    text = _clean_text(prefix)
    pay_matches = list(_PAY_PERIOD_RE.finditer(text))

    if not pay_matches:
        return current_plan_type, text

    pay_match = pay_matches[-1]
    pay_period = _clean_text(pay_match.group("pay")).replace(" ", "")
    before_pay = _clean_text(text[: pay_match.start()])

    term_match = _TERM_RE.search(before_pay)
    if term_match:
        term = _clean_text(term_match.group("term")).replace(" ", "")
        before_term = _clean_text(before_pay[: term_match.start()])

        if before_term and not _is_excluded_label(before_term):
            return before_term, pay_period

        return term, pay_period

    if before_pay and not _is_excluded_label(before_pay):
        return before_pay, pay_period

    return current_plan_type, pay_period


def _iter_lines(text: str) -> Iterable[str]:
    for raw in text.splitlines():
        line = _clean_text(raw)
        if line:
            yield line


def build_life_fubon_pdf_conversion_rows(
    example: RateExample,
) -> list[RateExampleConversionRow]:
    """
    푸본현대생명 PDF raw를 RateExampleConversionRow 목록으로 변환한다.
    """
    text = _extract_pdf_text(example.file.path)

    rows: list[RateExampleConversionRow] = []
    current_product = ""
    current_plan_type = ""

    for line in _iter_lines(text):
        bullet = _BULLET_RE.match(line)
        if bullet:
            current_product = _clean_product_title(bullet.group("title"))
            current_plan_type = ""
            continue

        if not current_product or _is_header_or_noise(line):
            continue

        # 상품명/상품유형/보험기간 등 단독 라인 처리
        if "%" not in line:
            if _is_excluded_label(line):
                current_plan_type = ""
                continue

            if line not in {"주계약", "비갱신형", "갱신형"}:
                current_plan_type = line

            continue

        match = _RATE_ROW_RE.match(line)
        if not match:
            continue

        prefix = _clean_text(match.group("prefix"))
        if _is_excluded_label(prefix):
            continue

        plan_type, pay_period = _split_rate_prefix(prefix, current_plan_type)
        if not pay_period:
            continue

        year1 = _to_decimal_percent(match.group("year1"))
        next_year = _to_decimal_percent(match.group("next_year"))
        if year1 is None or next_year is None:
            continue

        rows.append(
            RateExampleConversionRow(
                source_file=example,
                source_sheet="PDF",
                source_row_no=len(rows) + 1,
                insurer_type=example.insurer_type,
                category=example.category,
                insurer="푸본현대",
                coverage_type=_coverage_type(current_product),
                strategy_flag="",
                product_name=current_product,
                plan_type=plan_type or "",
                pay_period=pay_period,
                year1=year1,
                year2=next_year,
                year3=next_year,
                year4=next_year,
            )
        )

    deduped: list[RateExampleConversionRow] = []
    seen: set[tuple[str, str, str, Decimal, Decimal]] = set()

    for row in rows:
        key = (
            row.product_name,
            row.plan_type,
            row.pay_period,
            row.year1,
            row.year2,
        )
        if key in seen:
            continue

        seen.add(key)
        deduped.append(row)

    return deduped