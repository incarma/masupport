# commission/services/rate_example/life/heungkuk/parser.py
from __future__ import annotations

"""
흥국생명 PDF 환산율 정규화.

대상:
- 보험사: 흥국
- 파일 형식: PDF
- 정규화 범위: "흥국생명 보장성(주보험) 환산율" 키워드가 있는 raw PDF의 두 번째 페이지

핵심 규칙:
- 정규화 테이블 insurer = "흥국" 고정
- 상품코드/비고 컬럼은 정규화에서 제외
- PDF 표의 병합 셀은 행 구획 기준으로 carry-down 전개
- 상품명 줄바꿈은 한 줄로 결합
- 보험종목 → plan_type
- 상품명에 "종신" 포함 시 coverage_type = "종신/CI", 그 외 "기타(보장성)"
- 환산율(GA)의 각 납기 컬럼에 숫자 데이터가 있는 경우만 row 생성
- 각 납기 환산율은 year1~year4에 동일 저장
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example.common import (
    clean_spaces,
    decimal_from_text,
)
from commission.services.rate_example.common.pdf import PdfTextItem

logger = logging.getLogger(__name__)

TARGET_KEYWORD = "흥국생명 보장성(주보험) 환산율"
TARGET_PAGE_INDEX = 1  # PDF 두 번째 페이지, 0-based

PAY_PERIOD_HEADERS = ("20년↑", "15년↑", "10년↑", "5년↑")
PLAN_TYPE_KEYWORDS = (
    "해약환급금미지급형",
    "해약환급금일부지급형",
    "표준형",
    "갱신형",
)

_HEADER_NOISE = {
    "구분",
    "상품명",
    "보험종목",
    "상품코드",
    "상품코드(개정)",
    "환산율",
    "GA",
    "비고",
    "보종",
}


@dataclass(frozen=True)
class _Word(PdfTextItem):
    """흥국생명 PDF word 좌표.

    공통 PdfTextItem 좌표 계약을 재사용하되,
    기존 parser의 cx/cy convenience property는 유지한다.
    """

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class _RawLine:
    y: float
    words: list[_Word]

    @property
    def text(self) -> str:
        return _join_tokens(w.text for w in sorted(self.words, key=lambda w: w.x0))


def build_life_heungkuk_pdf_conversion_rows(
    example: RateExample,
) -> list[RateExampleConversionRow]:
    """
    흥국생명 보장성(주보험) PDF 2페이지를 RateExampleConversionRow 목록으로 정규화한다.

    PyMuPDF(fitz)의 word 좌표를 사용해 PDF 표 구획을 복원한다.
    좌표 기반으로 환산율 납기 헤더와 데이터 셀을 매칭하므로,
    단순 줄바꿈 텍스트 흐름에 의존하지 않는다.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("흥국 PDF 정규화에는 PyMuPDF(fitz)가 필요합니다.") from exc

    if not example.file:
        return []

    pdf_path = example.file.path
    rows: list[RateExampleConversionRow] = []

    with fitz.open(pdf_path) as doc:
        if len(doc) <= TARGET_PAGE_INDEX:
            logger.warning(
                "Heungkuk PDF normalize skipped: page 2 missing. example_id=%s file=%s",
                example.pk,
                getattr(example, "original_name", ""),
            )
            return []

        page = doc[TARGET_PAGE_INDEX]
        page_text = _compact_text(page.get_text("text") or "")
        if _compact_text(TARGET_KEYWORD) not in page_text:
            logger.warning(
                "Heungkuk PDF page 2 keyword mismatch: example_id=%s file=%s",
                example.pk,
                getattr(example, "original_name", ""),
            )
            return []

        words = _extract_words(page)
        if not words:
            return []

        rate_header_x = _detect_rate_header_x(words)
        if not rate_header_x:
            logger.warning(
                "Heungkuk PDF rate headers not detected: example_id=%s file=%s",
                example.pk,
                getattr(example, "original_name", ""),
            )
            return []

        lines = _group_words_to_lines(words)
        table_top_y = _detect_table_top_y(lines)
        body_lines = [line for line in lines if line.y > table_top_y]

        current_product = ""
        current_section = ""
        source_row_no = 0
        seen: set[tuple[str, str, str, Decimal]] = set()

        for line in body_lines:
            line_text = _normalize_space(line.text)
            if not line_text or _is_noise_line(line_text):
                continue

            # 왼쪽 병합 구분 컬럼(건강/종신 등)은 보종 판단에 쓰지 않지만,
            # 상품명 carry-down 경계 판단 보조용으로 보관한다.
            section_candidate = _extract_section_candidate(line.words)
            if section_candidate:
                current_section = section_candidate

            product_candidate = _extract_product_candidate(line.words)
            if product_candidate:
                current_product = _normalize_product_name(product_candidate)

            plan_type = _extract_plan_type(line_text)
            if not plan_type:
                continue

            product_name = current_product
            if not product_name:
                # PDF 좌표상 상품명이 행 중앙에만 찍히는 병합 셀 방어:
                # 같은 y 주변 또는 직전 상품명 후보를 다시 탐색한다.
                product_name = _nearest_product_above(lines, line.y)

            product_name = _normalize_product_name(product_name)
            if not product_name:
                continue

            rates = _extract_rates_by_header(line.words, rate_header_x)
            if not rates:
                continue

            coverage_type = _coverage_type(product_name)

            for pay_period, rate in rates.items():
                if rate is None:
                    continue

                dedupe_key = (product_name, plan_type, pay_period, rate)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                source_row_no += 1
                rows.append(
                    RateExampleConversionRow(
                        source_file=example,
                        source_sheet="PDF 2p",
                        source_row_no=source_row_no,
                        insurer_type=example.insurer_type,
                        category=example.category,
                        insurer="흥국",
                        coverage_type=coverage_type,
                        strategy_flag="",
                        product_name=product_name,
                        plan_type=plan_type,
                        pay_period=pay_period,
                        year1=rate,
                        year2=rate,
                        year3=rate,
                        year4=rate,
                    )
                )

        logger.info(
            "Heungkuk PDF normalized: example_id=%s rows=%s section_hint=%s",
            example.pk,
            len(rows),
            current_section,
        )

    return rows


def _extract_words(page) -> list[_Word]:
    """
    PyMuPDF page.get_text("words") 결과를 내부 Word 구조로 변환한다.

    반환 tuple 구조:
    (x0, y0, x1, y1, text, block_no, line_no, word_no)
    """
    raw_words = page.get_text("words") or []
    words: list[_Word] = []

    for item in raw_words:
        if len(item) < 5:
            continue
        text = _normalize_space(str(item[4] or ""))
        if not text:
            continue
        words.append(
            _Word(
                text=text,
                x0=float(item[0]),
                y0=float(item[1]),
                x1=float(item[2]),
                y1=float(item[3]),
            )
        )

    return sorted(words, key=lambda w: (w.y0, w.x0))


def _group_words_to_lines(words: list[_Word], *, y_tolerance: float = 3.2) -> list[_RawLine]:
    """
    y 좌표가 가까운 단어들을 같은 행으로 묶는다.

    PDF 표에서 줄바꿈된 상품명 자체를 행으로 판단하지 않기 위해
    실제 word 좌표 y 중심 기준으로만 1차 라인을 만든 뒤,
    상품명/보험종목 carry-down은 별도 로직에서 처리한다.
    """
    lines: list[_RawLine] = []

    for word in words:
        matched = None
        for line in lines:
            if abs(line.y - word.cy) <= y_tolerance:
                matched = line
                break

        if matched is None:
            lines.append(_RawLine(y=word.cy, words=[word]))
        else:
            matched.words.append(word)
            matched.y = (matched.y * (len(matched.words) - 1) + word.cy) / len(matched.words)

    for line in lines:
        line.words.sort(key=lambda w: w.x0)

    return sorted(lines, key=lambda line: line.y)


def _detect_rate_header_x(words: list[_Word]) -> dict[str, float]:
    """
    환산율(GA) 하위 납기 헤더의 x 좌표를 감지한다.

    일부 PDF에서는 "20년↑"가 "20년"과 "↑"로 분리될 수 있어
    compact 비교로 탐지한다.
    """
    header_x: dict[str, float] = {}
    compact_targets = {_compact_text(h): h for h in PAY_PERIOD_HEADERS}

    for word in words:
        compact = _compact_text(word.text)
        if compact in compact_targets:
            header_x[compact_targets[compact]] = word.cx

    # 헤더가 단어 분리로 일부만 잡히는 경우를 대비해 y 라인 텍스트에서 재탐색한다.
    if len(header_x) < 2:
        lines = _group_words_to_lines(words)
        for line in lines:
            line_text = _compact_text(line.text)
            if not any(_compact_text(h) in line_text for h in PAY_PERIOD_HEADERS):
                continue
            for header in PAY_PERIOD_HEADERS:
                target = _compact_text(header)
                candidates = [w for w in line.words if target in _compact_text(w.text)]
                if candidates:
                    header_x[header] = candidates[0].cx

    return header_x


def _detect_table_top_y(lines: list[_RawLine]) -> float:
    """
    본문 시작 y 좌표를 찾는다.
    납기 헤더 라인 또는 '상품명/보험종목/상품코드' 헤더 라인 이후부터 본문으로 본다.
    """
    top_y = 0.0
    for line in lines:
        compact = _compact_text(line.text)
        if any(_compact_text(h) in compact for h in PAY_PERIOD_HEADERS):
            top_y = max(top_y, line.y)
        if "상품명" in compact and "보험종목" in compact:
            top_y = max(top_y, line.y)
    return top_y


def _extract_section_candidate(words: list[_Word]) -> str:
    """
    좌측 구분 컬럼 후보를 추출한다.
    실제 저장 컬럼은 아니며, 병합 구조 경계 감지 보조용이다.
    """
    left_words = [w.text for w in words if w.x0 < 70]
    text = _normalize_space(" ".join(left_words))
    if text in {"건강", "종신", "연금", "저축"}:
        return text
    return ""


def _extract_product_candidate(words: list[_Word]) -> str:
    """
    상품명 컬럼 후보를 추출한다.

    PDF 좌표는 파일마다 약간 흔들릴 수 있으므로,
    상품명 컬럼의 대략적 영역을 사용하되 보험종목/상품코드/환산율 영역은 제외한다.
    """
    product_tokens: list[str] = []

    for word in words:
        text = _normalize_space(word.text)
        if not text or text in _HEADER_NOISE:
            continue
        if _is_plan_type_text(text):
            continue
        if _looks_like_code(text):
            continue
        if _looks_like_rate(text):
            continue

        # 페이지 2 표 기준 상품명 컬럼은 왼쪽 구분 컬럼 다음부터 보험종목 컬럼 전까지다.
        # 좌표값은 A4 landscape/portrait PDF 변환 차이를 감안해 넓게 잡는다.
        if 65 <= word.cx <= 230:
            product_tokens.append(text)

    product = _join_tokens(product_tokens)

    # 보험종목 단어만 잡힌 경우 상품명이 아니다.
    if _is_plan_type_text(product):
        return ""

    return product


def _nearest_product_above(lines: list[_RawLine], y: float) -> str:
    """
    병합 상품명 셀이 행 중앙에만 추출되는 경우를 위한 fallback.
    현재 행 위쪽에서 가장 가까운 상품명 후보를 찾는다.
    """
    for line in reversed([line for line in lines if line.y <= y]):
        product = _extract_product_candidate(line.words)
        if product:
            return product
    return ""


def _extract_plan_type(line_text: str) -> str:
    for keyword in PLAN_TYPE_KEYWORDS:
        if keyword in line_text:
            return keyword
    return ""


def _extract_rates_by_header(
    words: list[_Word],
    header_x: dict[str, float],
) -> dict[str, Decimal]:
    """
    행 내 환산율 값을 가장 가까운 납기 헤더 x 좌표에 매칭한다.

    빈 셀과 '-'는 words에 없거나 rate로 인정하지 않으므로 자연 제외된다.
    """
    rates: dict[str, Decimal] = {}

    if not header_x:
        return rates

    rate_words = [w for w in words if _looks_like_rate(w.text)]
    if not rate_words:
        return rates

    for word in rate_words:
        value = _to_decimal_percent(word.text)
        if value is None:
            continue

        nearest_header = min(
            header_x.items(),
            key=lambda item: abs(item[1] - word.cx),
        )[0]
        rates[nearest_header] = value

    return rates


def _to_decimal_percent(value: str) -> Decimal | None:
    text = _normalize_space(value)
    if not text or text == "-":
        return None

    text = text.replace("%", "").replace(",", "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None

    return decimal_from_text(text)


def _looks_like_rate(value: str) -> bool:
    text = _normalize_space(value)
    if text == "-":
        return False
    return bool(re.fullmatch(r"\d+(?:\.\d+)?%?", text)) and "%" in text


def _looks_like_code(value: str) -> bool:
    text = _normalize_space(value)
    if not text:
        return False
    # 상품코드는 5자리 숫자 또는 쉼표로 이어진 숫자 묶음이다.
    return bool(re.fullmatch(r"\d{5}(?:,\s*\d{5})*", text))


def _is_plan_type_text(value: str) -> bool:
    text = _normalize_space(value)
    return any(keyword in text for keyword in PLAN_TYPE_KEYWORDS)


def _is_noise_line(value: str) -> bool:
    compact = _compact_text(value)
    if not compact:
        return True

    if TARGET_KEYWORD.replace(" ", "") in compact:
        return True

    if any(_compact_text(h) in compact for h in PAY_PERIOD_HEADERS):
        return True

    if compact in {_compact_text(v) for v in _HEADER_NOISE}:
        return True

    if "상품명" in compact and "보험종목" in compact:
        return True

    return False


def _coverage_type(product_name: str) -> str:
    return "종신/CI" if "종신" in product_name else "기타(보장성)"


def _normalize_product_name(value: str) -> str:
    text = _normalize_space(value)
    text = text.replace("(무)", "").strip()
    return _normalize_space(text)


def _normalize_space(value: str) -> str:
    return clean_spaces(value)


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _join_tokens(tokens: Iterable[str]) -> str:
    return _normalize_space(" ".join(str(t or "").strip() for t in tokens if str(t or "").strip()))
