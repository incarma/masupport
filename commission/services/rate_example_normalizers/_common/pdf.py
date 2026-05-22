# django_ma/commission/services/rate_example_normalizers/_common/pdf.py
from __future__ import annotations

"""
RateExample PDF parser 공통 helper.

주의:
- 보험사별 좌표/테이블 해석 정책은 이 모듈로 강제 통합하지 않는다.
- 파일 접근은 FieldFile.open("rb") 또는 서버 내부 path만 사용한다.
- .file.url 직접 접근 금지.
"""

import re
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from commission.services.rate_example_normalizers._common.decimal import decimal_from_text
from commission.services.rate_example_normalizers._common.text import clean_spaces

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfTextItem:
    """PDF 텍스트 조각. 좌표 기반 parser 공통 row grouping용."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float


def clean_pdf_text(value: Any) -> str:
    """PDF 추출 텍스트의 중복 공백/줄바꿈을 1칸으로 정리한다."""
    return clean_spaces(str(value or "").replace("\u00a0", " "))


def decimal_from_pdf_percent(value: Any) -> Decimal | None:
    """PDF 텍스트에서 백분율 숫자만 Decimal로 추출한다."""
    text = clean_pdf_text(value)
    if not text:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", "").replace("%", ""))
    if not match:
        return None

    return decimal_from_text(match.group(0))


def extract_pdf_lines_with_pypdf(example) -> list[tuple[int, int, str]]:
    """
    FieldFile.open("rb") 기반 PDF 라인 추출.

    반환:
    - (page_no, line_no, text)
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF 정규화를 위해 pypdf 패키지가 필요합니다.") from exc

    lines: list[tuple[int, int, str]] = []

    with example.file.open("rb") as f:
        reader = PdfReader(f)
        for page_no, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            for line_no, raw_line in enumerate(text.splitlines(), start=1):
                line = clean_pdf_text(raw_line)
                if line:
                    lines.append((page_no, line_no, line))

    return lines


def dedupe_by_key(items: Iterable, key_fn) -> list:
    """순서 유지 중복 제거."""
    seen: set[tuple] = set()
    result: list = []

    for item in items:
        key = key_fn(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)

    return result


def group_pdf_items_by_y(
    items: Iterable[PdfTextItem],
    *,
    y_tolerance: float = 3.0,
) -> list[list[PdfTextItem]]:
    """PDF 텍스트 조각을 y좌표 기준 행 단위로 묶는다."""
    rows: list[list[PdfTextItem]] = []

    for item in sorted(items, key=lambda it: (it.y0, it.x0)):
        if not item.text:
            continue

        if rows and abs(rows[-1][0].y0 - item.y0) <= y_tolerance:
            rows[-1].append(item)
        else:
            rows.append([item])

    for row in rows:
        row.sort(key=lambda it: it.x0)

    return rows


def extract_pdf_text_with_fallback(path: str) -> str:
    """
    PDF 전체 텍스트 추출 fallback chain.

    우선순위:
    1. pdfplumber
    2. PyMuPDF
    3. pypdf
    """
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(path) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        logger.debug("pdfplumber extraction failed: path=%s", path, exc_info=True)

    try:
        import fitz  # type: ignore

        doc = fitz.open(path)
        try:
            return "\n".join(page.get_text("text") for page in doc)
        finally:
            doc.close()
    except Exception:
        logger.debug("PyMuPDF extraction failed: path=%s", path, exc_info=True)

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        logger.exception("PDF text extraction failed: path=%s", path)
        raise