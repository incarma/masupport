# django_ma/commission/services/rate_example_normalizers/fire_aig.py
from __future__ import annotations

"""
AIG손해보험 수정률 PDF 정규화.

정규화 정책:
- insurer_type = fire
- category = conv
- insurer = AIG
- coverage_type = "보장" 고정
- plan_type = "" 고정
- "시행시기(종기)" 값이 "판매 종료"인 행은 제외
- "상 품 명" → product_name
- "납입 주기" → pay_period
- "수정율" → year1
- 손보 수정률 단일 컬럼 구조에 따라 year2~year4는 None
"""

import logging
import re
from decimal import Decimal, InvalidOperation

from commission.models import RateExample, RateExampleConversionRow

logger = logging.getLogger(__name__)

_ROW_RE = re.compile(
    r"(?P<rate>[\d,]+(?:\.\d+)?)\s*%"
    r"(?P<status>판매\s*종료|\d{4}\s*년\s*\d{1,2}\s*월)"
    r"(?P<product>\(무\).*?)"
    r"(?=(?:[\d,]+(?:\.\d+)?\s*%(?:판매\s*종료|\d{4}\s*년\s*\d{1,2}\s*월))|$)"
)
_PAY_PERIOD_RE = re.compile(r"(?P<pay>\d+\s*년\s*자동\s*갱신)")


def _clean_text(value: object) -> str:
    """PDF 추출 텍스트의 공백/줄바꿈을 정규화한다."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _to_decimal_percent(value: object) -> Decimal | None:
    """수정율 표시값을 Decimal로 변환한다. 예: '180%' → Decimal('180')."""
    text = _clean_text(value).replace("%", "").replace(",", "")
    if not text:
        return None

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        logger.warning("AIG 수정률 변환 실패: %r", value, exc_info=True)
        return None


def _extract_pdf_text(path: str) -> str:
    """
    PDF 텍스트 추출.

    우선순위:
    1. pypdf
    2. PyPDF2

    운영 원칙:
    - 파일 URL 직접 접근 금지
    - 업로드된 FieldFile.path만 내부 서버 경로로 읽는다.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        PdfReader = None

    if PdfReader is None:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "AIG PDF 정규화를 위해 pypdf 또는 PyPDF2가 필요합니다."
            ) from exc

    reader = PdfReader(path)
    chunks: list[str] = []

    for page in reader.pages:
        chunks.append(page.extract_text() or "")

    return "\n".join(chunks)


def _parse_aig_pdf_rows(text: str) -> list[dict[str, object]]:
    """
    PDF 추출 결과를 상품/시행시기/수정율 컬럼 배열로 복원한다.

    AIG PDF는 추출기별로 다음 두 형태가 모두 발생한다.
    1) 한 줄형: 상품명 + 시행시기 + 수정율
    2) 컬럼형: 상품명 목록, 시행시기 목록, 수정율 목록이 따로 추출

    따라서 line 단위 row 매칭에만 의존하지 않고,
    상품명/시행시기/수정율 토큰을 각각 수집한 뒤 순서대로 zip 한다.
    """
    parsed_rows: list[dict[str, object]] = []
    compact_text = _clean_text(text)
    pay_match = _PAY_PERIOD_RE.search(compact_text)
    pay_period = _clean_text(pay_match.group("pay")) if pay_match else ""

    for match in _ROW_RE.finditer(compact_text):
        parsed_rows.append({
            "product_name": _clean_text(match.group("product")),
            "status": _clean_text(match.group("status")),
            "pay_period": pay_period,
            "rate": _to_decimal_percent(match.group("rate")),
        })

    return parsed_rows


def build_fire_aig_pdf_conversion_rows(example: RateExample) -> list[RateExampleConversionRow]:
    """
    AIG손해보험 PDF 원본을 RateExampleConversionRow 목록으로 변환한다.

    저장 매핑:
    - coverage_type: "보장"
    - product_name: PDF "상 품 명"
    - plan_type: ""
    - pay_period: PDF "납입 주기"
    - year1: PDF "수정율"
    """
    if not example.file:
        return []

    rows: list[RateExampleConversionRow] = []
    seen: set[tuple[str, str, Decimal]] = set()

    text = _extract_pdf_text(example.file.path)
    parsed_rows = _parse_aig_pdf_rows(text)

    for idx, parsed in enumerate(parsed_rows, start=1):
        product_name = parsed["product_name"]
        status = _clean_text(parsed["status"]).replace(" ", "")
        pay_period = parsed["pay_period"]
        rate = parsed["rate"]

        if status == "판매종료":
            continue

        if not product_name or not pay_period or rate is None:
            continue

        dedupe_key = (product_name, pay_period, rate)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        rows.append(
            RateExampleConversionRow(
                source_file=example,
                source_sheet="PDF",
                source_row_no=idx,
                insurer_type=RateExample.TYPE_FIRE,
                category=RateExample.CAT_CONV,
                insurer="AIG",
                coverage_type="보장",
                strategy_flag="",
                product_name=product_name,
                plan_type="",
                pay_period=pay_period,
                year1=rate,
                year2=None,
                year3=None,
                year4=None,
            )
        )

    logger.info("AIG fire normalizer: created %s rows. pk=%s", len(rows), example.pk)
    return rows