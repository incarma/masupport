# commission/services/rate_example_calculator.py
from __future__ import annotations

"""
수수료 예시표 계산 서비스.

역할:
- 환산율 정규화 데이터(RateExampleConversionRow)와
  지급률 정규화 데이터(RateExamplePayRow)를 조합하여 회차별 수수료를 계산한다.
- 계산은 Decimal 기반으로 수행한다.
- DB는 별도 계산식 검증 전까지 제외하고,
- IBK는 지급률 상품군 기준 전용 계산식을 사용한다.

주의:
- DB 저장값은 123.4%를 Decimal("123.4") 형태로 보관한다.
- 계산 시 반드시 /100 하여 배수로 변환한다.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from commission.models import RateExample, RateExampleConversionRow, RateExamplePayRow


EXCLUDED_CALC_INSURERS = {"DB"}
IBK_PREFIX = "[IBK]"
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
    
    # IBK는 환산율 정규화 row가 아니라 지급률 상품군 기준으로 계산한다.
    # 따라서 구분/납기는 사용하지 않는다.
    if insurer != "IBK" and not pay_period:
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


def _resolve_pay_coverage_type(conv: RateExampleConversionRow) -> str:
    """
    지급률 매칭 키 결정.

    우선순위:
    1) 환산율 정규화 row의 strategy_flag가 있으면 전략상품 지급률 사용
    2) 없으면 기존 보종(coverage_type) 지급률 사용
    """
    strategy_flag = str(conv.strategy_flag or "").strip()
    if strategy_flag:
        return strategy_flag
    return str(conv.coverage_type or "").strip()


def _get_ibk_pay_row(product_name: str) -> RateExamplePayRow:
    """
    IBK 전용 지급률 row 조회.

    프론트에서는 사용자에게 prefix 없는 상품군명만 보여주고,
    DB에는 rate_example_pay_normalizer.py 기준으로 [IBK]{상품명} 형태 저장.
    """
    product = str(product_name or "").strip()
    if not product:
        raise RateExampleCalcError("IBK 상품군을 선택해 주세요.")

    coverage_type = product if product.startswith(IBK_PREFIX) else f"{IBK_PREFIX}{product}"
    return _get_pay_row("IBK", coverage_type)


def _sum_optional(*values: int | None) -> int:
    return sum(v for v in values if v is not None)


def _calc_amount_without_conversion(
    *,
    premium: Decimal,
    pay_rate: Decimal | None,
    commission_rate: Decimal,
) -> int | None:
    """
    IBK 전용 계산.

    IBK는 상품군별 지급률만 사용하므로 환산율 multiplier를 적용하지 않는다.
    """
    pay = _pct_to_multiplier(pay_rate)
    comm = _pct_to_multiplier(commission_rate)

    if pay is None or comm is None:
        return None

    return _money_round(premium * pay * comm)


def _build_result(
    *,
    data: CalcInput,
    coverage_type: str,
    pay: RateExamplePayRow,
    use_conversion: bool,
    conv: RateExampleConversionRow | None = None,
) -> dict[str, Any]:
    """
    계산 결과 조립 공통 함수.

    - 일반 보험사: 환산율 × 지급률 × 수수료율
    - IBK: 지급률 × 수수료율
    """
    if use_conversion:
        assert conv is not None

        def amount(conversion_rate, pay_rate):
            return _amount_or_none(
                premium=data.premium,
                conversion_rate=conversion_rate,
                pay_rate=pay_rate,
                commission_rate=data.commission_rate,
            )
    else:
        def amount(_conversion_rate, pay_rate):
            return _calc_amount_without_conversion(
                premium=data.premium,
                pay_rate=pay_rate,
                commission_rate=data.commission_rate,
            )

    year1_rate = conv.year1 if conv else None
    year2_rate = conv.year2 if conv else None
    year3_rate = conv.year3 if conv else None
    year4_rate = conv.year4 if conv else None

    next_month_first = amount(year1_rate, pay.col_first)
    next_month_subtotal = next_month_first or 0

    month_13 = amount(year2_rate, pay.col_m13)
    year2 = amount(year2_rate, pay.col_yr2)
    year3 = amount(year3_rate, pay.col_yr3)
    month_36 = amount(year3_rate, pay.col_m36)
    month_37 = amount(year4_rate, pay.col_m37)
    year4 = amount(year4_rate, pay.col_yr4)

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
        "plan_type": "" if data.insurer == "IBK" else data.plan_type,
        "pay_period": "" if data.insurer == "IBK" else data.pay_period,
        "coverage_type": coverage_type,
        "pay_coverage_type": coverage_type,
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

    if data.insurer == "IBK":
        pay = _get_ibk_pay_row(data.product_name)
        display_coverage = str(pay.coverage_type or "").removeprefix(IBK_PREFIX)
        return _build_result(
            data=data,
            coverage_type=display_coverage,
            pay=pay,
            use_conversion=False,
        )

    conv = _get_conversion_row(data)
    pay_coverage_type = _resolve_pay_coverage_type(conv)
    pay = _get_pay_row(data.insurer, pay_coverage_type)

    return _build_result(
        data=data,
        coverage_type=conv.coverage_type,
        pay=pay,
        use_conversion=True,
        conv=conv,
    )