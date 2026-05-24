# commission/services/rate_example/fire/hana/parser.py
from __future__ import annotations

"""
하나손해보험(FIRE) 수정률 PDF 정규화.

역할:
- 하나손보 PDF 원본의 상품별 수정률 표를 RateExampleConversionRow로 변환한다.
- PDF 테이블의 병합 상품명 셀은 좌측 상품명 블록의 세로 범위를 기준으로 행에 전파한다.
- 손보 수정률 단일 컬럼 정책에 따라 수정률은 year1에만 저장한다.

정규화 정책:
- insurer_type = fire
- category = conv
- insurer = "하나"
- coverage_type = "보장" 고정
- product_name = PDF "상품명"
- pay_period = "상품분류" 하위 왼쪽 열
- plan_type = "상품분류" 하위 오른쪽 열
- year1 = "수정율/수정률" raw 백분율 수치
- year2/year3/year4 = None

주의:
- raw 수정률에 ×100, /100, /0.97 보정을 하지 않는다.
- DB 저장값은 160이면 160이고, 화면에서 160%로 표시한다.
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example.common.pdf import (
    clean_pdf_text,
    decimal_from_pdf_percent,
    group_pdf_items_by_y,
    PdfTextItem,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ProductBlock:
    """병합 상품명 셀을 행 범위로 전파하기 위한 좌측 상품명 블록."""

    product_name: str
    y0: float
    y1: float


@dataclass(frozen=True)
class _RateLine:
    """상품분류/수정률 우측 테이블의 1개 행."""

    pay_period: str
    plan_type: str
    rate: Decimal
    y_mid: float


def _clean_text(value: object) -> str:
    """PDF 텍스트의 줄바꿈/중복 공백을 정리한다."""
    return clean_pdf_text(value)


def _to_decimal_percent(value: object) -> Decimal | None:
    """
    수정률 raw 값을 Decimal로 변환한다.

    하나손보 수정률 PDF는 160, 240처럼 이미 백분율 표시값이다.
    따라서 별도 보정 없이 숫자만 Decimal로 저장한다.
    """
    text = _clean_text(value)
    if not text:
        return None

    return decimal_from_pdf_percent(text)


def _is_product_name(text: str) -> bool:
    """
    좌측 상품명 블록 여부를 판정한다.

    상품명은 대부분 '무배당'으로 시작하며, 상품코드 숫자가 뒤따를 수 있다.
    헤더/본문 설명/납기 행은 제외한다.
    """
    if not text:
        return False
    if not text.startswith("무배당"):
        return False
    if re.search(r"\d+년납\s+(보장|적립)\s+\d+", text):
        return False
    return True


def _strip_product_code(text: str) -> str:
    """상품명 끝의 상품코드 숫자만 제거한다."""
    text = _clean_text(text)
    return re.sub(r"\s+\d{5,}$", "", text).strip()


_TextItem = PdfTextItem


def _extract_items_with_pymupdf(path: str) -> list[tuple[int, list[_TextItem]]]:
    """
    PyMuPDF(fitz) 기반 좌표 텍스트 추출.

    기존 PDF 정규화 파일들과 마찬가지로 서버 내부 FieldFile.path만 사용한다.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - 운영 의존성 누락 방어
        raise RuntimeError(
            "하나손보 PDF 정규화를 위해 PyMuPDF(fitz)가 필요합니다. "
            "requirements.txt에 PyMuPDF를 추가해 주세요."
        ) from exc

    pages: list[tuple[int, list[_TextItem]]] = []

    with fitz.open(path) as doc:
        for page_index, page in enumerate(doc, start=1):
            raw = page.get_text("dict")
            items: list[_TextItem] = []

            for block in raw.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = _clean_text(span.get("text", ""))
                        if not text:
                            continue
                        x0, y0, x1, y1 = span.get("bbox", (0, 0, 0, 0))
                        items.append(
                            PdfTextItem(
                                text=text,
                                x0=float(x0),
                                y0=float(y0),
                                x1=float(x1),
                                y1=float(y1),
                            )
                        )

            pages.append((page_index, items))

    return pages


def _build_product_blocks(rows: list[list[_TextItem]]) -> list[_ProductBlock]:
    """
    좌측 상품명 셀의 세로 병합 범위를 복원한다.

    PDF에는 병합 셀 개념이 없으므로, 상품명 텍스트의 y좌표와 다음 상품명 y좌표 사이를
    해당 상품의 범위로 본다.
    """
    candidates: list[tuple[str, float]] = []

    for row in rows:
        left_text = _clean_text(" ".join(item.text for item in row if item.x0 < 360))
        if _is_product_name(left_text):
            candidates.append((_strip_product_code(left_text), row[0].y0))

    blocks: list[_ProductBlock] = []
    for idx, (name, y0) in enumerate(candidates):
        next_y = candidates[idx + 1][1] if idx + 1 < len(candidates) else y0 + 220
        blocks.append(_ProductBlock(product_name=name, y0=y0 - 2, y1=next_y - 2))

    return blocks


def _extract_rate_lines(rows: list[list[_TextItem]]) -> list[_RateLine]:
    """
    우측 상품분류/수정률 행을 추출한다.

    기대 패턴:
        5년납 보장 20
        10년납 적립 33

    매핑:
        왼쪽 상품분류 하위 열  → pay_period
        오른쪽 상품분류 하위 열 → plan_type
        수정율/수정률          → year1
    """
    rate_lines: list[_RateLine] = []

    pattern = re.compile(
        r"(?P<pay>\d+\s*년납)\s+"
        r"(?P<plan>보장|적립)\s+"
        r"(?P<rate>-?\d+(?:\.\d+)?)"
    )

    for row in rows:
        text = _clean_text(" ".join(item.text for item in row))
        match = pattern.search(text)
        if not match:
            continue

        rate = _to_decimal_percent(match.group("rate"))
        if rate is None:
            continue

        y_mid = sum(item.y0 for item in row) / max(len(row), 1)
        rate_lines.append(
            _RateLine(
                pay_period=_clean_text(match.group("pay")),
                plan_type=_clean_text(match.group("plan")),
                rate=rate,
                y_mid=y_mid,
            )
        )

    return rate_lines


def _find_product_for_rate(blocks: list[_ProductBlock], rate_line: _RateLine) -> str:
    """
    수정률 행 y좌표가 속하는 상품명 블록을 찾는다.

    페이지 하단/추출 오차로 경계가 약간 어긋나는 경우를 대비해 가장 가까운
    직전 상품명 블록을 fallback으로 사용한다.
    """
    for block in blocks:
        if block.y0 <= rate_line.y_mid < block.y1:
            return block.product_name

    previous = [block for block in blocks if block.y0 <= rate_line.y_mid]
    if previous:
        return previous[-1].product_name

    return ""


def build_fire_hana_pdf_conversion_rows(example: RateExample) -> list[RateExampleConversionRow]:
    """
    하나손해보험 PDF 수정률을 RateExampleConversionRow 리스트로 변환한다.

    저장은 호출부(normalize_rate_example)가 담당한다.
    """
    if not example.file:
        return []

    pages = _extract_items_with_pymupdf(example.file.path)
    rows: list[RateExampleConversionRow] = []
    seen: set[tuple[str, str, str, Decimal]] = set()

    for page_no, items in pages:
        page_rows = group_pdf_items_by_y(items)
        product_blocks = _build_product_blocks(page_rows)
        rate_lines = _extract_rate_lines(page_rows)

        if not product_blocks or not rate_lines:
            continue

        for rate_line in rate_lines:
            product_name = _find_product_for_rate(product_blocks, rate_line)
            if not product_name:
                continue

            # 하나손보 요청 정책: 정규화 테이블의 상품군은 전건 '보장' 고정.
            coverage_type = "보장"

            dedupe_key = (
                product_name,
                rate_line.pay_period,
                rate_line.plan_type,
                rate_line.rate,
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            rows.append(
                RateExampleConversionRow(
                    source_file=example,
                    source_sheet=f"PDF p.{page_no}",
                    source_row_no=len(rows) + 1,
                    insurer_type=RateExample.TYPE_FIRE,
                    category=RateExample.CAT_CONV,
                    insurer="하나",
                    coverage_type=coverage_type,
                    strategy_flag="",
                    product_name=product_name,
                    plan_type=rate_line.plan_type,
                    pay_period=rate_line.pay_period,
                    year1=rate_line.rate,
                    year2=None,
                    year3=None,
                    year4=None,
                )
            )

    logger.info(
        "fire_hana normalizer: created %s rows. pk=%s file=%s",
        len(rows),
        getattr(example, "pk", None),
        getattr(example, "original_name", ""),
    )
    return rows
