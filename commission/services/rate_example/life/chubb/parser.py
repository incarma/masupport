# commission/services/rate_example/life/chubb/parser.py
from __future__ import annotations

"""
처브생명 RateExample PDF 정규화.

역할:
- 처브 PDF 환산율 raw 파일을 RateExampleConversionRow 표준 구조로 변환한다.
- 주계약 섹션만 정규화하고, "특약" 섹션 감지 시 해당 페이지와 이후 페이지는 제외한다.

핵심 정책:
- insurer = "처브"
- PDF 원본은 public URL로 접근하지 않고 FieldFile.open("rb")로만 읽는다.
- 상품명 줄바꿈은 공백 1칸으로 결합한다.
- 1종/2종이 함께 있는 상품은 상품명을 1종/2종으로 분리해 row를 복제한다.
- 환산율은 raw % 값에 12를 곱해 year1~year4에 동일 저장한다.
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example.common import (
    append_unique,
    clean_spaces,
    clean_pdf_text,
)

logger = logging.getLogger(__name__)

INSURER = "처브"
PDF_SOURCE_SHEET = "pdf"

PRODUCT_START_RE = re.compile(r"^Chubb\s+", re.IGNORECASE)
PPP_RE = re.compile(r"PPP\s*=\s*(\d+)")
PPP_RANGE_LEFT_RE = re.compile(r"(?P<left>\d+)\s*[≤<=]\s*PPP\s*(?:<\s*\d+)?")
PPP_RANGE_RIGHT_RE = re.compile(r"PPP\s*[≥>=]\s*(?P<value>\d+)")
PPP_RIGHT_OPEN_RE = re.compile(r"(?P<left>\d+)\s*[≤<=]\s*PPP")

RATE_RE = re.compile(r"(?P<rate>\d+(?:\.\d+)?)\s*%")
FA_P_CP_TOKEN_RE = re.compile(r"\b(FA|P|CP)\b", re.IGNORECASE)


@dataclass(frozen=True)
class _ParsedLine:
    page_no: int
    line_no: int
    text: str


@dataclass(frozen=True)
class _ChubbRawRow:
    page_no: int
    line_no: int
    product_name: str
    raw_pay_period: str
    raw_plan_type: str
    rate_1: Decimal | None
    rate_2: Decimal | None


def build_life_chubb_pdf_conversion_rows(
    example: RateExample,
) -> list[RateExampleConversionRow]:
    """
    처브 PDF 파일을 정규화 row 목록으로 변환한다.

    주의:
    - DB 저장은 이 함수에서 하지 않는다.
    - dispatcher(normalize_rate_example)가 replace/append 및 bulk_create를 담당한다.
    """
    lines = list(_iter_main_contract_lines(example))
    raw_rows = _parse_lines_to_raw_rows(lines)

    rows: list[RateExampleConversionRow] = []
    seen: set[tuple[str, str, str, Decimal | None, Decimal | None]] = set()

    for raw in raw_rows:
        expanded = _expand_product_type_rows(raw)

        for product_name, selected_rate in expanded:
            if selected_rate is None:
                continue

            plan_type = _normalize_plan_type(raw.raw_plan_type)
            pay_period = _normalize_pay_period(raw.raw_pay_period)
            coverage_type = _resolve_coverage_type(product_name)
            normalized_rate = _to_year_rate(selected_rate)

            key = (product_name, plan_type, pay_period, normalized_rate, normalized_rate)
            append_unique(
                rows,
                seen,
                RateExampleConversionRow(
                    source_file=example,
                    source_sheet=f"{PDF_SOURCE_SHEET}:page-{raw.page_no}",
                    source_row_no=raw.line_no,
                    insurer_type=RateExample.TYPE_LIFE,
                    category=RateExample.CAT_CONV,
                    insurer=INSURER,
                    coverage_type=coverage_type,
                    strategy_flag="",
                    product_name=product_name,
                    plan_type=plan_type,
                    pay_period=pay_period,
                    year1=normalized_rate,
                    year2=normalized_rate,
                    year3=normalized_rate,
                    year4=normalized_rate,
                ),
                key,
            )

    return rows


def _iter_main_contract_lines(example: RateExample) -> Iterable[_ParsedLine]:
    """
    PDF 텍스트를 page/line 단위로 읽는다.

    "특약" 섹션이 등장한 페이지부터는 정규화에서 제외한다.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("처브 PDF 정규화에는 pypdf 패키지가 필요합니다.") from exc

    with example.file.open("rb") as fp:
        reader = PdfReader(fp)

        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            normalized_page_text = _compact_spaces(text)

            if _is_rider_page(normalized_page_text):
                logger.info(
                    "[rate_example][chubb] rider page detected. stop parsing. example_id=%s page=%s",
                    getattr(example, "id", None),
                    page_index,
                )
                break

            for line_no, raw_line in enumerate(text.splitlines(), start=1):
                line = _compact_spaces(raw_line)
                if not line:
                    continue

                # 헤더/푸터/문서 장식 라인은 정규화 대상에서 제외한다.
                if _is_noise_line(line):
                    continue

                yield _ParsedLine(page_no=page_index, line_no=line_no, text=line)


def _parse_lines_to_raw_rows(lines: list[_ParsedLine]) -> list[_ChubbRawRow]:
    """
    PDF 텍스트 라인을 정규화 전 raw row로 복원한다.

    구현 방향:
    - 단순 줄바꿈을 행으로 보지 않는다.
    - 상품명/납기/조건/환산율 상태를 유지하면서 table row를 복원한다.
    - 병합 셀처럼 반복 생략된 상품명/납기/조건은 직전 유효값을 전파한다.
    - 단, 환산율은 전파하지 않는다.
    """
    rows: list[_ChubbRawRow] = []

    current_product = ""
    current_pay_period = ""
    current_plan_type = ""

    product_buffer: list[str] = []
    pending_plan_fragment = ""

    for item in lines:
        text = item.text

        if _looks_like_product_line(text):
            if product_buffer:
                current_product = _normalize_product_name(" ".join(product_buffer))
                product_buffer = []

            product_buffer.append(text)
            continue

        # 상품명 continuation: 상품 시작 후 다음 조건/납기/rate 라인이 나오기 전까지 병합
        if product_buffer and not _contains_table_signal(text):
            product_buffer.append(text)
            continue

        if product_buffer:
            current_product = _normalize_product_name(" ".join(product_buffer))
            product_buffer = []

        if not current_product:
            continue

        parsed = _parse_data_line(text)

        if parsed["pay_period"]:
            current_pay_period = parsed["pay_period"]

        parsed_plan_type = str(parsed["plan_type"] or "")

        # ── PDF 줄 분리 보정 ─────────────────────────────────────────────
        # 예: "FA=70m, 100m," 다음 줄이 "200m 26% 26%"로 추출되는 경우
        #     두 줄을 "FA=70m, 100m, 200m"으로 결합한다.
        if parsed_plan_type:
            if pending_plan_fragment and _is_amount_only_continuation(parsed_plan_type):
                parsed_plan_type = _merge_plan_fragments(
                    pending_plan_fragment,
                    parsed_plan_type,
                )
                pending_plan_fragment = ""
            elif _is_incomplete_plan_fragment(parsed_plan_type):
                pending_plan_fragment = parsed_plan_type
            else:
                pending_plan_fragment = ""

            current_plan_type = parsed_plan_type

        rate_1 = parsed["rate_1"]
        rate_2 = parsed["rate_2"]

        if rate_1 is None and rate_2 is None:
            continue

        rows.append(
            _ChubbRawRow(
                page_no=item.page_no,
                line_no=item.line_no,
                product_name=current_product,
                raw_pay_period=current_pay_period or "-",
                raw_plan_type=current_plan_type or "-",
                rate_1=rate_1,
                rate_2=rate_2,
            )
        )

    return rows


def _parse_data_line(text: str) -> dict[str, str | Decimal | None]:
    """
    table row 후보 라인에서 납기/구분/환산율을 추출한다.
    """
    rates = [Decimal(m.group("rate")) for m in RATE_RE.finditer(text)]

    text_wo_rates = RATE_RE.sub(" ", text)
    text_wo_rates = _compact_spaces(text_wo_rates)

    pay_period = _extract_pay_period_token(text_wo_rates)
    plan_type = _extract_plan_type_token(text_wo_rates, pay_period)

    rate_1: Decimal | None = None
    rate_2: Decimal | None = None

    if len(rates) >= 2:
        rate_1 = rates[0]
        rate_2 = rates[1]
    elif len(rates) == 1:
        rate_1 = rates[0]
        rate_2 = None

    return {
        "pay_period": pay_period,
        "plan_type": plan_type,
        "rate_1": rate_1,
        "rate_2": rate_2,
    }


def _expand_product_type_rows(raw: _ChubbRawRow) -> list[tuple[str, Decimal | None]]:
    """
    1종/2종 상품을 별도 row로 확장한다.

    - 1종/2종 컬럼이 모두 있으면 각각 해당 rate를 사용한다.
    - 단일 rate 상품은 상품명 그대로 1개 row만 만든다.
    """
    product_name = _normalize_product_name(raw.product_name)

    if _has_both_type_1_and_2(product_name) and raw.rate_2 is not None:
        p1 = _product_name_for_type(product_name, "1종")
        p2 = _product_name_for_type(product_name, "2종")
        return [(p1, raw.rate_1), (p2, raw.rate_2)]

    return [(product_name, raw.rate_1)]


def _product_name_for_type(product_name: str, type_label: str) -> str:
    """
    상품명 괄호 안의 1종/2종 설명을 분리한다.
    """
    match = re.search(r"\(([^)]*1\s*종[^)]*2\s*종[^)]*)\)", product_name)
    if not match:
        return f"{product_name} ({type_label})"

    inside = match.group(1)
    parts = [p.strip() for p in re.split(r"\s*,\s*", inside) if p.strip()]
    selected = ""

    for part in parts:
        compact = part.replace(" ", "")
        if type_label.replace(" ", "") in compact:
            selected = part
            break

    if not selected:
        selected = type_label

    start, end = match.span()
    return _compact_spaces(f"{product_name[:start]}({selected}){product_name[end:]}")


def _normalize_product_name(value: str) -> str:
    """
    상품명 줄바꿈/다중 공백을 공백 1칸으로 정리한다.
    """
    value = _compact_spaces(value)
    value = value.replace("(1 종", "(1종").replace("2 종", "2종")
    value = value.replace("1 종", "1종").replace("2 종", "2종")
    return _compact_spaces(value)


def _resolve_coverage_type(product_name: str) -> str:
    """
    보종 정규화.
    """
    if "종신" in product_name:
        return "종신/CI"
    return "기타(보장성)"


def _normalize_plan_type(value: str) -> str:
    """
    보장금액(FA)/보험료(P)/보험기간(CP) 조건을 구분값으로 변환한다.
    """
    value = _compact_spaces(value)
    if not value or value == "-":
        return "-"

    # 콤마 나열형: FA=50m, 70m
    eq_match = re.match(r"^(FA|P|CP)\s*=\s*(.+)$", value, re.IGNORECASE)
    if eq_match:
        label = _translate_metric(eq_match.group(1))
        amounts = [_normalize_amount_token(v) for v in _split_csv_values(eq_match.group(2))]
        amounts = [v for v in amounts if v]
        return f"{label} {', '.join(amounts)}" if amounts else label

    # 단측 이상: FA≥20m / P≥10,000원
    ge_match = re.match(r"^(FA|P|CP)\s*[≥>=]\s*(.+)$", value, re.IGNORECASE)
    if ge_match:
        label = _translate_metric(ge_match.group(1))
        amount = _normalize_amount_token(ge_match.group(2))
        return f"{label} {amount} 이상"

    # 단측 미만: P<10,000원
    lt_match = re.match(r"^(FA|P|CP)\s*<\s*(.+)$", value, re.IGNORECASE)
    if lt_match:
        label = _translate_metric(lt_match.group(1))
        amount = _normalize_amount_token(lt_match.group(2))
        return f"{label} {amount} 미만"

    # 양측 부등호: 30m≤FA<100m → 이상 조건만 사용
    range_match = re.match(
        r"^(?P<left>.+?)\s*[≤<=]\s*(?P<label>FA|P|CP)\s*<\s*(?P<right>.+)$",
        value,
        re.IGNORECASE,
    )
    if range_match:
        label = _translate_metric(range_match.group("label"))
        amount = _normalize_amount_token(range_match.group("left"))
        return f"{label} {amount} 이상"

    return value


def _normalize_pay_period(value: str) -> str:
    """
    납입기간(PPP)/가입연령 조건을 납기값으로 변환한다.
    """
    value = _compact_spaces(value)
    if not value or value == "-":
        return "-"

    eq_match = PPP_RE.search(value)
    if eq_match:
        return f"{eq_match.group(1)}년"

    left_match = PPP_RANGE_LEFT_RE.search(value)
    if left_match:
        return f"{left_match.group('left')}년 이상"

    right_open_match = PPP_RIGHT_OPEN_RE.search(value)
    if right_open_match:
        return f"{right_open_match.group('left')}년 이상"

    right_match = PPP_RANGE_RIGHT_RE.search(value)
    if right_match:
        return f"{right_match.group('value')}년 이상"

    return value


def _to_year_rate(raw_rate: Decimal) -> Decimal:
    """
    처브 환산율 저장 정책: raw % 값 × 12.

    예:
    - 47% → Decimal("564")
    - 11% → Decimal("132")
    """
    try:
        return (Decimal(raw_rate) * Decimal("12")).quantize(Decimal("0.0001")).normalize()
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Invalid Chubb rate: {raw_rate}") from exc


def _extract_pay_period_token(text: str) -> str:
    """
    라인에서 PPP 조건만 추출한다.
    """
    # 처브 PDF에서 "-"는 납기/조건 placeholder로 추출된다.
    # 예: "- P<10,000원 23%" → 납기 "-", 구분 "P<10,000원"
    if text.startswith("- ") and FA_P_CP_TOKEN_RE.search(text):
        return "-"

    patterns = [
        r"PPP\s*=\s*\d+",
        r"\d+\s*[≤<=]\s*PPP\s*<\s*\d+",
        r"\d+\s*[≤<=]\s*PPP",
        r"PPP\s*[≥>=]\s*\d+",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _compact_spaces(match.group(0))

    return ""


def _extract_plan_type_token(text: str, pay_period: str) -> str:
    """
    라인에서 FA/P/CP 조건만 추출한다.
    """
    candidate = text
    if pay_period:
        if pay_period == "-":
            candidate = re.sub(r"^\s*-\s*", " ", candidate, count=1)
        else:
            candidate = candidate.replace(pay_period, " ")

    candidate = _compact_spaces(candidate)
    candidate = _strip_placeholder_dash(candidate)
    if not candidate or candidate == "-":
        return ""

    if FA_P_CP_TOKEN_RE.search(candidate):
        return candidate

    # 직전 조건의 continuation일 수 있는 "FA=70m, 100m, 200m" 형태 보정
    if re.search(r"\d+\s*m", candidate, re.IGNORECASE):
        return candidate

    return ""


def _is_incomplete_plan_fragment(value: str) -> bool:
    """
    다음 줄과 결합해야 하는 구분 조각인지 판정한다.

    예:
    - "FA=70m, 100m," → 다음 줄 "200m 26% 26%"와 결합 필요
    """
    value = _compact_spaces(value)
    return bool(
        value.endswith(",")
        and FA_P_CP_TOKEN_RE.search(value)
    )


def _is_amount_only_continuation(value: str) -> bool:
    """
    "200m"처럼 앞선 FA/P/CP 조건의 continuation인지 판정한다.
    """
    value = _strip_placeholder_dash(_compact_spaces(value))
    return bool(re.fullmatch(r"\d+(?:\.\d+)?\s*m", value, re.IGNORECASE))


def _merge_plan_fragments(left: str, right: str) -> str:
    """
    PDF 줄 분리로 끊긴 구분값을 결합한다.
    """
    left = _compact_spaces(left).rstrip(", ")
    right = _strip_placeholder_dash(_compact_spaces(right))
    return _compact_spaces(f"{left}, {right}")


def _strip_placeholder_dash(value: str) -> str:
    """
    PDF 표의 빈 셀 placeholder '-'를 구분값에서 제거한다.

    예:
    - "- P≥10,000원" → "P≥10,000원"
    - "FA≥100m -" → "FA≥100m"
    - "30m≤FA<100m -" → "30m≤FA<100m"
    """
    value = _compact_spaces(value)
    value = re.sub(r"^\s*-\s*", "", value)
    value = re.sub(r"\s*-\s*$", "", value)
    return _compact_spaces(value)


def _looks_like_product_line(text: str) -> bool:
    return bool(PRODUCT_START_RE.match(text))


def _contains_table_signal(text: str) -> bool:
    return bool(
        PPP_RE.search(text)
        or RATE_RE.search(text)
        or FA_P_CP_TOKEN_RE.search(text)
        or text.strip() == "-"
    )


def _is_rider_page(page_text: str) -> bool:
    """
    특약 페이지 감지.

    헤더의 "특약" 또는 특약 안내 문구가 나오면 해당 페이지부터 제외한다.
    """
    return "■ 특약" in page_text or re.search(r"\b특약\b", page_text) and "주계약" not in page_text


def _is_noise_line(text: str) -> bool:
    noise_keywords = (
        "Channel Compensation",
        "Confidential",
        "General Agency",
        "Production Credit Rate",
        "2026.04.01",
        "상품",
        "납입기간",
        "가입연령",
        "보장금액",
        "보험료",
        "보험기간",
        "환산율",
        "PC Rate",
        "주1)",
        "상기 표에",
        "수수료를 지급하지 않습니다",
        "■ 주계약",
    )
    return any(keyword in text for keyword in noise_keywords)


def _has_both_type_1_and_2(product_name: str) -> bool:
    compact = product_name.replace(" ", "")
    return "1종" in compact and "2종" in compact


def _translate_metric(value: str) -> str:
    key = value.upper()
    if key == "FA":
        return "가입금액"
    if key == "P":
        return "보험료"
    if key == "CP":
        return "보험기간"
    return value


def _normalize_amount_token(value: str) -> str:
    """
    금액/조건 토큰을 한글 표시값으로 변환한다.

    예:
    - 20m → 2,000만
    - 100m → 1억
    - 10,000원 → 10,000원
    """
    value = _compact_spaces(value)
    value = value.strip(", ")

    m_match = re.match(r"^(?P<num>\d+(?:\.\d+)?)\s*m$", value, re.IGNORECASE)
    if m_match:
        million = Decimal(m_match.group("num"))
        manwon = int(million * Decimal("100"))
        if manwon >= 10000 and manwon % 10000 == 0:
            return f"{manwon // 10000}억"
        return f"{manwon:,}만"

    return value


def _split_csv_values(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _compact_spaces(value: str) -> str:
    return clean_pdf_text(value)
