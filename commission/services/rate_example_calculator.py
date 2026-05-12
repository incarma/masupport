# commission/services/rate_example_calculator.py
from __future__ import annotations

"""
수수료 예시표 계산 서비스.

역할:
- 환산율 정규화 데이터(RateExampleConversionRow)와
  지급률 정규화 데이터(RateExamplePayRow)를 조합하여 회차별 수수료를 계산한다.
- 계산은 Decimal 기반으로 수행한다.
- 1차 구현에서는 DB/IBK/처브/카디프를 제외한다.

주의:
- DB 저장값은 123.4%를 Decimal("123.4") 형태로 보관한다.
- 계산 시 반드시 /100 하여 배수로 변환한다.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from commission.models import RateExample, RateExampleConversionRow, RateExamplePayRow


EXCLUDED_CALC_INSURERS = {"DB", "IBK", "처브", "카디프"}
DEFAULT_PAY_TIER = "5천만↑"


class RateExampleCalcError(ValueError):
    """사용자에게 노출 가능한 계산 검증 오류."""


@dataclass(frozen=True)
class CalcInput:
    insurer: str
    product_name: str
    plan_type: str
    pay_period: str
    premium: Decimal
    commission_rate: Decimal


def _to_decimal(value: Any, *, field_name: str) -> Decimal:
    raw = str(value or "").replace(",", "").strip()
    if not raw:
        raise RateExampleCalcError(f"{field_name} 값이 필요합니다.")
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        raise RateExampleCalcError(f"{field_name} 값이 올바르지 않습니다.")


def _pct_to_multiplier(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value) / Decimal("100")


def _money_round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _ratio_round(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _amount_or_none(
    *,
    premium: Decimal,
    conversion_rate: Decimal | None,
    pay_rate: Decimal | None,
    commission_rate: Decimal,
) -> int | None:
    """
    선택 회차 계산.
    - 환산율 또는 지급률이 None이면 해당 회차는 계산 제외(None).
    """
    conv = _pct_to_multiplier(conversion_rate)
    pay = _pct_to_multiplier(pay_rate)
    comm = _pct_to_multiplier(commission_rate)

    if conv is None or pay is None or comm is None:
        return None

    return _money_round(premium * conv * pay * comm)


def _parse_input(payload: dict[str, Any]) -> CalcInput:
    insurer = str(payload.get("insurer") or "").strip()
    product_name = str(payload.get("product_name") or "").strip()
    plan_type = str(payload.get("plan_type") or "").strip()
    pay_period = str(payload.get("pay_period") or "").strip()

    if not insurer:
        raise RateExampleCalcError("보험사를 선택해 주세요.")
    if insurer in EXCLUDED_CALC_INSURERS:
        raise RateExampleCalcError("해당 보험사는 계산식 검증 후 추후 지원 예정입니다.")
    if not product_name:
        raise RateExampleCalcError("상품명을 선택해 주세요.")
    if not pay_period:
        raise RateExampleCalcError("납기를 선택해 주세요.")

    premium = _to_decimal(payload.get("premium"), field_name="보험료")
    commission_rate = _to_decimal(payload.get("commission_rate"), field_name="수수료율")

    if premium <= 0:
        raise RateExampleCalcError("보험료는 0보다 커야 합니다.")
    if commission_rate <= 0:
        raise RateExampleCalcError("수수료율은 0보다 커야 합니다.")

    return CalcInput(
        insurer=insurer,
        product_name=product_name,
        plan_type=plan_type,
        pay_period=pay_period,
        premium=premium,
        commission_rate=commission_rate,
    )


def _get_conversion_row(data: CalcInput) -> RateExampleConversionRow:
    """
    상품 식별 기준:
    보험사 + 상품명 + 구분 + 납기

    plan_type은 공란 상품도 존재하므로 정확히 공란까지 매칭한다.
    """
    row = (
        RateExampleConversionRow.objects
        .filter(
            insurer_type=RateExample.TYPE_LIFE,
            category=RateExample.CAT_CONV,
            insurer=data.insurer,
            product_name=data.product_name,
            plan_type=data.plan_type,
            pay_period=data.pay_period,
        )
        .select_related("source_file")
        .order_by("-source_file__created_at", "-id")
        .first()
    )

    if row is None:
        raise RateExampleCalcError("계산에 필요한 환산율 정규화 데이터가 없습니다.")

    return row


def _get_pay_row(insurer: str, coverage_type: str) -> RateExamplePayRow:
    if not coverage_type:
        raise RateExampleCalcError("지급률 조회에 필요한 상품군 정보가 없습니다.")

    row = (
        RateExamplePayRow.objects
        .filter(
            insurer_type=RateExample.TYPE_LIFE,
            category=RateExample.CAT_PAY,
            insurer=insurer,
            tier=DEFAULT_PAY_TIER,
            coverage_type=coverage_type,
        )
        .select_related("source_file")
        .order_by("-source_file__created_at", "-id")
        .first()
    )

    if row is None:
        raise RateExampleCalcError("계산에 필요한 지급률 정규화 데이터가 없습니다.")

    return row


def _sum_optional(*values: int | None) -> int:
    return sum(v for v in values if v is not None)


def calculate_rate_example_commission(payload: dict[str, Any]) -> dict[str, Any]:
    """
    수수료 예시표 계산 진입점.

    계산식:
    - 익월 초회 = 보험료 × 1차년 환산율 × 초회 지급률 × 수수료율
    - 13회 = 보험료 × 2차년 환산율 × 13회 지급률 × 수수료율
    - 2차년 = 보험료 × 2차년 환산율 × 2차년구간 지급률 × 수수료율
    - 3차년 = 보험료 × 3차년 환산율 × 3차년구간 지급률 × 수수료율
    - 36회 = 보험료 × 3차년 환산율 × 36회 지급률 × 수수료율
    - 37회 = 보험료 × 4차년 환산율 × 37회 지급률 × 수수료율
    - 4차년 = 보험료 × 4차년 환산율 × 4차년구간 지급률 × 수수료율
    """
    data = _parse_input(payload)
    conv = _get_conversion_row(data)
    pay = _get_pay_row(data.insurer, conv.coverage_type)

    next_month_first = _amount_or_none(
        premium=data.premium,
        conversion_rate=conv.year1,
        pay_rate=pay.col_first,
        commission_rate=data.commission_rate,
    )
    next_month_subtotal = next_month_first or 0

    month_13 = _amount_or_none(
        premium=data.premium,
        conversion_rate=conv.year2,
        pay_rate=pay.col_m13,
        commission_rate=data.commission_rate,
    )
    year2 = _amount_or_none(
        premium=data.premium,
        conversion_rate=conv.year2,
        pay_rate=pay.col_yr2,
        commission_rate=data.commission_rate,
    )
    year3 = _amount_or_none(
        premium=data.premium,
        conversion_rate=conv.year3,
        pay_rate=pay.col_yr3,
        commission_rate=data.commission_rate,
    )
    month_36 = _amount_or_none(
        premium=data.premium,
        conversion_rate=conv.year3,
        pay_rate=pay.col_m36,
        commission_rate=data.commission_rate,
    )
    month_37 = _amount_or_none(
        premium=data.premium,
        conversion_rate=conv.year4,
        pay_rate=pay.col_m37,
        commission_rate=data.commission_rate,
    )
    year4 = _amount_or_none(
        premium=data.premium,
        conversion_rate=conv.year4,
        pay_rate=pay.col_yr4,
        commission_rate=data.commission_rate,
    )

    renewal_subtotal = _sum_optional(
        month_13,
        year2,
        year3,
        month_36,
        month_37,
        year4,
    )
    total_amount = next_month_subtotal + renewal_subtotal
    total_ratio = _ratio_round((Decimal(total_amount) / data.premium) * Decimal("100"))

    return {
        "insurer": data.insurer,
        "product_name": data.product_name,
        "plan_type": data.plan_type,
        "pay_period": data.pay_period,
        "coverage_type": conv.coverage_type,
        "next_month_first": next_month_first,
        "next_month_subtotal": next_month_subtotal,
        "month_13": month_13,
        "year2": year2,
        "year3": year3,
        "month_36": month_36,
        "month_37": month_37,
        "year4": year4,
        "renewal_subtotal": renewal_subtotal,
        "total_amount": total_amount,
        "total_ratio": total_ratio,
    }