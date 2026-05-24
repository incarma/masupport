# commission/services/rate_example/fire/nh/parser.py
from __future__ import annotations

"""
농협손해보험 수정률 정규화.

역할:
- 농협손해보험 raw xlsx 파일을 RateExampleConversionRow로 정규화한다.
- 손해보험 수정률(conv) master에 저장한다.

핵심 정책:
- 색상 기준 판별을 사용하지 않는다.
- 병합 셀은 parser 내부 matrix에서만 전개한다.
- 테이블은 B~F열 헤더:
  납입기간 / 보험기간 / 계약구분 / 모집(ㄱ) / 수금(ㄴ)
  기준으로 판별한다.
- 테이블 내부 공란 셀은 현재 셀과 헤더 사이 같은 컬럼의 마지막 텍스트로 채운다.
"""

import re
from decimal import Decimal
from typing import Any

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example.common import (
    append_unique,
    build_worksheet_value_map,
    clean_spaces,
    decimal_from_text,
    filled_value_above,
)


HEADER_LABELS = ("납입기간", "보험기간", "계약구분", "모집(ㄱ)", "수금(ㄴ)")


def _text(value: Any) -> str:
    """셀 값을 공백 정리된 단일 문자열로 변환한다."""
    if value is None:
        return ""
    return clean_spaces(str(value).replace("　", " "))


def _multiline_text(value: Any) -> str:
    """보험기간처럼 줄바꿈 의미가 있는 값은 '/'로 결합한다."""
    if value is None:
        return ""
    parts = [
        re.sub(r"\s+", " ", str(part).strip())
        for part in str(value).replace("　", " ").splitlines()
        if str(part).strip()
    ]
    return "/".join(parts)


def _decimal_or_none(value: Any) -> Decimal | None:
    """수정률 값을 Decimal로 변환한다. raw 백분율 수치를 그대로 저장한다."""
    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float)):
        return Decimal(str(value))

    return decimal_from_text(value)


def _strip_bracket_text(value: str) -> str:
    """【...】 텍스트에서 내부 값만 추출한다."""
    s = _text(value)
    m = re.search(r"【\s*(.*?)\s*】", s)
    return _text(m.group(1)) if m else ""


def _product_name_from_marker(value: str) -> str:
    """A열 '◈ 상품명'에서 상품명만 추출한다."""
    s = _text(value)
    if "◈" not in s:
        return ""
    return _text(s.split("◈", 1)[1])


def _expanded_matrix(ws) -> dict[tuple[int, int], Any]:
    """
    병합 셀 값을 병합 범위 전체에 전파한 value matrix를 만든다.

    주의:
    - 실제 worksheet는 unmerge하지 않는다.
    - 정규화 parser 내부에서만 전개 matrix를 사용한다.
    """
    return build_worksheet_value_map(ws)


def _is_header_row(values: dict[tuple[int, int], Any], row_no: int) -> bool:
    """B~F열이 농협 수정률 테이블 헤더인지 확인한다."""
    labels = tuple(_text(values.get((row_no, col))) for col in range(2, 7))
    return labels == HEADER_LABELS


def _filled_table_value(
    values: dict[tuple[int, int], Any],
    *,
    header_row: int,
    row_no: int,
    col_no: int,
) -> Any:
    """
    테이블 내부 공란 보정.

    현재 셀이 비어 있으면 현재 행과 헤더 행 사이의 같은 컬럼에서
    가장 가까운 상단 텍스트를 사용한다.
    """
    return filled_value_above(
        values,
        header_row=header_row,
        row_no=row_no,
        col_no=col_no,
        is_filled=lambda value: bool(_text(value)),
    )


def _is_header_or_note_row(pay_period: str, insurance_period: str, rate: Decimal | None) -> bool:
    """헤더/안내/비율 없는 행을 제외한다."""
    joined = f"{pay_period} {insurance_period}"
    if "납입기간" in joined or "보험기간" in joined:
        return True
    return rate is None


def _build_pay_period(pay_period: str, insurance_period: Any) -> str:
    """납입기간 + 보험기간을 최종 납기 문자열로 결합한다."""
    pay = _text(pay_period)
    ins = _multiline_text(insurance_period)

    if pay and ins:
        return f"{pay} ({ins})"
    if pay:
        return pay
    if ins:
        return f"({ins})"
    return ""


def _coverage_type(product_name: str, plan_type: str, contract_type: str) -> str:
    """상품명/구분/계약구분에 따라 상품군을 산출한다."""
    product = _text(product_name)
    plan = _text(plan_type)
    contract = _text(contract_type)

    if "실손" in product:
        if "갱신" in contract:
            return "단독실손(갱신)"
        if "신규" in contract:
            return "단독실손(초회)"

    if "태아" in plan:
        return "보장(태아)"

    return "보장"


def _collect_plan_parts(values: dict[tuple[int, int], Any], row_no: int, max_col: int) -> list[str]:
    """해당 행에서 【...】 형태의 구분 텍스트를 수집한다."""
    parts: list[str] = []

    for col in range(1, max_col + 1):
        text = _text(values.get((row_no, col)))
        if "【" not in text or "】" not in text:
            continue

        part = _strip_bracket_text(text)
        if part and part not in parts:
            parts.append(part)

    return parts


def _combine_plan_parts(parts: list[str]) -> str:
    """1줄 또는 2줄 구분 텍스트를 최종 구분값으로 결합한다."""
    clean = [_text(p) for p in parts if _text(p)]

    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]

    return f"{clean[0]} ({clean[1]})"


def build_fire_nh_conversion_rows(example: RateExample, wb) -> list[RateExampleConversionRow]:
    """
    농협손해보험 수정률 raw workbook을 정규화 행 목록으로 변환한다.

    반환:
    - 아직 DB에 저장하지 않은 RateExampleConversionRow 인스턴스 목록
    """
    rows: list[RateExampleConversionRow] = []

    for ws in wb.worksheets:
        values = _expanded_matrix(ws)

        current_product = ""
        current_plan = ""
        pending_plan_parts: list[str] = []
        active_header_row: int | None = None
        seen_keys: set[tuple[str, str, str, Decimal]] = set()

        for row_no in range(1, ws.max_row + 1):
            a_text = _text(values.get((row_no, 1)))

            # ── 상품 블록 시작: A열 "◈" 기준 ───────────────────────────
            if "◈" in a_text:
                current_product = _product_name_from_marker(a_text)
                current_plan = ""
                pending_plan_parts = []
                active_header_row = None
                continue

            if not current_product:
                continue

            # ── 구분 후보 수집: "【...】" 행 ───────────────────────────
            plan_parts = _collect_plan_parts(values, row_no, ws.max_column)
            if plan_parts:
                pending_plan_parts.extend(plan_parts)
                pending_plan_parts = list(dict.fromkeys(pending_plan_parts))
                current_plan = _combine_plan_parts(pending_plan_parts)
                active_header_row = None
                continue

            # ── 테이블 시작: B~F 헤더 기준 ────────────────────────────
            if _is_header_row(values, row_no):
                active_header_row = row_no
                pending_plan_parts = []
                continue

            if active_header_row is None:
                continue

            # 다음 상품 시작 행이 나오기 전까지 현재 헤더 기준 테이블로 처리한다.
            pay_period_raw = _filled_table_value(
                values,
                header_row=active_header_row,
                row_no=row_no,
                col_no=2,
            )
            insurance_raw = _filled_table_value(
                values,
                header_row=active_header_row,
                row_no=row_no,
                col_no=3,
            )
            contract_raw = _filled_table_value(
                values,
                header_row=active_header_row,
                row_no=row_no,
                col_no=4,
            )
            rate_raw = _filled_table_value(
                values,
                header_row=active_header_row,
                row_no=row_no,
                col_no=5,
            )

            pay_period = _text(pay_period_raw)
            insurance_period = _multiline_text(insurance_raw)
            contract_type = _text(contract_raw)
            rate = _decimal_or_none(rate_raw)

            if _is_header_or_note_row(pay_period, insurance_period, rate):
                continue

            final_pay_period = _build_pay_period(pay_period, insurance_raw)
            if not final_pay_period:
                continue

            coverage = _coverage_type(current_product, current_plan, contract_type)

            dedupe_key = (current_product, current_plan, final_pay_period, rate)
            append_unique(
                rows,
                seen_keys,
                RateExampleConversionRow(
                    source_file=example,
                    source_sheet=ws.title,
                    source_row_no=row_no,
                    insurer_type=example.insurer_type,
                    category=example.category,
                    insurer="농협",
                    coverage_type=coverage,
                    strategy_flag="",
                    product_name=current_product,
                    plan_type=current_plan,
                    pay_period=final_pay_period,
                    # 손보 수정률은 year1에 저장한다.
                    # 농협 raw는 DB/KB 손보와 동일하게 백분율 표시값 그대로 저장한다.
                    year1=rate,
                    year2=None,
                    year3=None,
                    year4=None,
                ),
                dedupe_key,
            )

    return rows
