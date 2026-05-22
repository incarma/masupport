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
from decimal import Decimal
from typing import Any, Iterable

from commission.services.rate_example_normalizers._common.decimal import decimal_from_text
from commission.services.rate_example_normalizers._common.text import clean_spaces


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