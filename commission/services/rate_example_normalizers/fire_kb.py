# django_ma/commission/services/rate_example_normalizers/fire_kb.py
from __future__ import annotations

"""
KB 손해보험 수정률 정규화.

역할:
- KB 손해보험 raw 수정률 파일의 [GA채널_수정률] 시트만 정규화한다.
- 정규화 결과는 RateExampleConversionRow에 저장한다.
- 손해보험 수정률은 기존 환산율/수정률 master 테이블을 재사용한다.

정규화 컬럼 매핑:
- 보험사: KB
- 상품군: coverage_type
- 상품명: product_name
- 구분: plan_type
- 납기: pay_period
- 수정률: year1

중요:
- 수정률은 raw 데이터에 기재된 백분율 숫자를 그대로 저장한다.
  예: raw 160 → DB Decimal("160") → 화면 160%
- year2~year4는 사용하지 않으므로 None으로 둔다.
"""

from decimal import Decimal, InvalidOperation
import re
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example_normalizers._common.excel import (
    build_merged_value_map,
    cell_value_with_merged,
)
from commission.services.rate_example_normalizers._common.text import clean_spaces


TARGET_SHEET_NAME = "GA채널_수정률"


# =============================================================================
# 공통 텍스트/숫자 정규화 유틸
# =============================================================================


def _to_text(value: Any) -> str:
    """셀 값을 사용자 표시 기준 문자열로 정리한다."""
    return clean_spaces(
        str(value or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u00a0", " ")
    )


def _one_line(value: Any, *, sep: str = " ") -> str:
    """줄바꿈이 포함된 텍스트를 한 줄로 정리한다."""
    text = _to_text(value)
    if not text:
        return ""

    parts = [p.strip() for p in text.split("\n") if p.strip()]
    return sep.join(parts).strip()


def _decimal_from_value(value: Any) -> Decimal | None:
    """숫자/문자 셀을 Decimal로 변환한다."""
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float)):
        return Decimal(str(value))

    text = _to_text(value)
    if not text or text in {"-", "–", "—"}:
        return None

    text = text.replace(",", "").replace("%", "").strip()
    if not text:
        return None

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _rate_to_percent_value(value: Any) -> Decimal | None:
    """
    raw 수정률 값을 DB 저장용 백분율 숫자로 변환한다.

    예:
    - raw 160    → 160
    - raw "160%" → 160

    주의:
    - KB 손해보험 raw는 이미 사용자 표시용 백분율 숫자 기준이다.
    - 따라서 100을 곱하거나 나누지 않는다.
    """
    if value is None:
        return None

    text = _to_text(value)
    has_percent_mark = "%" in text

    raw = _decimal_from_value(value)
    if raw is None:
        return None

    return raw


# =============================================================================
# 병합 셀 처리
# =============================================================================


def _merged_value_map(ws: Worksheet) -> dict[tuple[int, int], Any]:
    """
    병합 셀 범위 전체에 좌상단 값을 전파하기 위한 lookup map을 만든다.

    openpyxl에서 병합 범위의 좌상단 외 셀은 None으로 보이므로,
    정규화 전 별도 map을 구성해 raw 병합 의미를 보존한다.
    """
    return build_merged_value_map(ws)


def _cell_value(
    ws: Worksheet,
    merged_map: dict[tuple[int, int], Any],
    row: int,
    col: int,
) -> Any:
    """병합 셀 전파값을 우선 반환한다."""
    return cell_value_with_merged(ws, merged_map, row, col)


# =============================================================================
# 도메인 규칙
# =============================================================================


def _normalize_product_name(value: Any) -> str:
    """상품명(C열)을 한 줄로 정규화한다."""
    return _one_line(value, sep=" ")


def _normalize_plan_type(group_value: Any) -> str:
    """당보그룹(G열)을 구분 컬럼으로 정규화한다."""
    group = _one_line(group_value, sep=" ")
    if group == "단일":
        return ""
    return group


def _normalize_coverage_type(raw_kind: str, group: str, renewal_value: Any) -> list[str]:
    """
    상품군을 정규화한다.

    반환값이 list인 이유:
    - 실손 + 갱신값 존재 시 초회/갱신 2행을 생성해야 하기 때문.
    """
    if raw_kind == "재물":
        return []

    if "신생아" in group or "태아" in group:
        return ["보장(태아)"]

    if raw_kind == "저축":
        return ["저축"]

    if raw_kind == "연금":
        return ["연금"]

    if raw_kind == "실손":
        renewal_text = _one_line(renewal_value, sep=" ")
        if not renewal_text or renewal_text == "-":
            return ["단독실손(초회)"]
        return ["단독실손(초회)", "단독실손(갱신)"]

    return ["보장"]


def _normalize_payment_period(pay_period_value: Any) -> str:
    """
    납입기간(F열)을 납기 텍스트로 정규화한다.

    규칙:
    - raw 값에 '납'이 없으면 '년' 뒤에 '납'을 삽입한다.
    - 예: 10년 → 10년납
    """
    text = _one_line(pay_period_value, sep=" ")
    if not text:
        return ""

    if "납" in text:
        return text

    # 가장 일반적인 형태: 10년, 20년, 30년 등
    text = re.sub(r"(년)(?!납)", r"\1납", text, count=1)
    return text


def _normalize_insurance_period(insurance_period_value: Any) -> str:
    """
    보험기간(E열)을 괄호 안에 넣을 한 줄 텍스트로 정규화한다.

    규칙:
    - 여러 줄은 이어붙인다.
    - 각 줄 사이에는 '/'를 삽입한다.
    - 단, 뒤에 붙는 줄이 이미 '/'로 시작하면 추가 '/'를 넣지 않는다.
    """
    text = _to_text(insurance_period_value)
    if not text:
        return ""

    parts = [p.strip() for p in text.split("\n") if p.strip()]
    if not parts:
        return ""

    result = parts[0]
    for part in parts[1:]:
        if part.startswith("/"):
            result += part
        else:
            result += "/" + part

    return result


def _build_pay_period(pay_period_value: Any, insurance_period_value: Any) -> str:
    """납입기간(F) + 보험기간(E)을 최종 납기 값으로 결합한다."""
    pay_period = _normalize_payment_period(pay_period_value)
    insurance_period = _normalize_insurance_period(insurance_period_value)

    if pay_period and insurance_period:
        return f"{pay_period} ({insurance_period})"

    if pay_period:
        return pay_period

    if insurance_period:
        return f"({insurance_period})"

    return ""


def _is_effective_data_row(product_name: str, raw_kind: str) -> bool:
    """헤더/빈 행을 제외한다."""
    if not product_name:
        return False

    if product_name in {"상품명", "상품"}:
        return False

    if raw_kind in {"구분", "상품군"}:
        return False

    return True


# =============================================================================
# Public builder
# =============================================================================


def build_fire_kb_conversion_rows(
    example: RateExample,
    wb,
) -> list[RateExampleConversionRow]:
    """
    KB 손해보험 수정률 정규화 row를 생성한다.

    Parameters:
        example:
            RateExample 인스턴스. insurer_type='fire', category='conv', insurer='KB' 전제.
        wb:
            openpyxl Workbook. rate_example_normalizer.py에서 read_only=False로 로드한다.

    Returns:
        RateExampleConversionRow 인스턴스 목록.
    """
    if TARGET_SHEET_NAME not in wb.sheetnames:
        return []

    ws: Worksheet = wb[TARGET_SHEET_NAME]
    merged_map = _merged_value_map(ws)

    rows: list[RateExampleConversionRow] = []

    for row_no in range(1, ws.max_row + 1):
        # raw 컬럼:
        # B 구분, C 상품명, E 보험기간, F 납입기간, G 당보그룹, I 최초, J 갱신
        raw_kind = _one_line(_cell_value(ws, merged_map, row_no, 2), sep=" ")
        product_name = _normalize_product_name(_cell_value(ws, merged_map, row_no, 3))
        insurance_period = _cell_value(ws, merged_map, row_no, 5)
        payment_period = _cell_value(ws, merged_map, row_no, 6)
        group_value = _cell_value(ws, merged_map, row_no, 7)
        first_rate_value = _cell_value(ws, merged_map, row_no, 9)
        renewal_rate_value = _cell_value(ws, merged_map, row_no, 10)

        if not _is_effective_data_row(product_name, raw_kind):
            continue

        group = _one_line(group_value, sep=" ")
        coverage_types = _normalize_coverage_type(raw_kind, group, renewal_rate_value)

        # 재물 등 제외 대상은 coverage_types가 빈 list로 반환된다.
        if not coverage_types:
            continue

        plan_type = _normalize_plan_type(group_value)
        pay_period = _build_pay_period(payment_period, insurance_period)

        for coverage_type in coverage_types:
            if coverage_type == "단독실손(갱신)":
                rate_value = _rate_to_percent_value(renewal_rate_value)
            else:
                rate_value = _rate_to_percent_value(first_rate_value)

            if rate_value is None:
                continue

            rows.append(
                RateExampleConversionRow(
                    source_file=example,
                    source_sheet=TARGET_SHEET_NAME,
                    source_row_no=row_no,
                    insurer_type=RateExample.TYPE_FIRE,
                    category=RateExample.CAT_CONV,
                    insurer="KB",
                    coverage_type=coverage_type,
                    strategy_flag="",
                    product_name=product_name,
                    plan_type=plan_type,
                    pay_period=pay_period,
                    year1=rate_value,
                    year2=None,
                    year3=None,
                    year4=None,
                )
            )

    return rows