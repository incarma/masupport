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
import re
import unicodedata
import logging

from commission.models import RateExample, RateExampleConversionRow, RateExamplePayRow


logger = logging.getLogger(__name__)


EXCLUDED_CALC_INSURERS = set()
IBK_PREFIX = "[IBK]"
DEFAULT_PAY_TIER = "5천만↑"

EMPTY_PLAN_TYPE_VALUES = {"", "-", "없음", "사용안함", "해당없음", "N/A", "n/a"}


class RateExampleCalcError(ValueError):
    """사용자에게 노출 가능한 계산 검증 오류."""


@dataclass(frozen=True)
class CalcInput:
    insurer_type: str
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


def _fire_mod_to_multiplier(value: Decimal | None) -> Decimal | None:
    """
    손해보험 수정률 multiplier 변환.

    일부 손보 parser는 raw 1.6을 그대로 저장하고,
    일부 parser는 화면 표시 기준 160(%)을 저장한다.
    계산에서는 둘 다 1.6배로 사용해야 하므로,
    명백한 percent 값(20 초과)은 /100 처리한다.
    """
    if value is None:
        return None
    raw = Decimal(value)
    if raw > Decimal("20"):
        return raw / Decimal("100")
    return raw


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


def _amount_or_none_with_conversion_multiplier(
    *,
    premium: Decimal,
    conversion_multiplier: Decimal | None,
    pay_rate: Decimal | None,
    commission_rate: Decimal,
) -> int | None:
    """
    DB생명 전용 계산 보조.

    DB생명은 일부 회차에서 단일 환산율이 아니라
    1차년+2차년 환산율 합계를 사용하므로,
    이미 /100 처리된 conversion multiplier를 직접 받는다.
    """
    pay = _pct_to_multiplier(pay_rate)
    comm = _pct_to_multiplier(commission_rate)

    if conversion_multiplier is None or pay is None or comm is None:
        return None

    return _money_round(premium * conversion_multiplier * pay * comm)


def _normalize_text(value: Any) -> str:
    """
    계산 매칭용 공통 문자열 정규화.
    - 유니코드 호환문자 정규화
    - 앞뒤 공백 제거
    - 내부 연속 공백 1칸으로 축약
    """
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _match_key(value: Any) -> str:
    """
    후보 row 비교용 key.
    공백 차이 때문에 같은 상품/납기가 불일치하지 않도록 공백을 제거한다.

    보험사 raw 표현 차이도 흡수:
    - &, /, ·, ,  → 동일 구분자 취급
    - 괄호 종류 통일
    - "만기", "납" 사이 공백 제거
    """
    text = _normalize_text(value)

    # 괄호 normalize
    text = (
        text.replace("[", "(")
        .replace("]", ")")
        .replace("{", "(")
        .replace("}", ")")
    )

    # 구분자 normalize
    text = re.sub(r"\s*[&/,·]\s*", "/", text)

    # 불필요 공백 제거
    text = text.replace(" ", "")

    return text.lower()


def _normalize_plan_type(value: Any) -> str:
    text = _normalize_text(value)
    return "" if text in EMPTY_PLAN_TYPE_VALUES else text


def _parse_input(payload: dict[str, Any]) -> CalcInput:
    insurer_type = _normalize_text(payload.get("insurer_type") or RateExample.TYPE_LIFE)
    if insurer_type == "nonlife":
        insurer_type = RateExample.TYPE_FIRE
    if insurer_type not in {RateExample.TYPE_LIFE, RateExample.TYPE_FIRE}:
        insurer_type = RateExample.TYPE_LIFE

    insurer = _normalize_text(payload.get("insurer"))
    product_name = _normalize_text(payload.get("product_name"))
    plan_type = _normalize_plan_type(payload.get("plan_type"))
    pay_period = _normalize_text(payload.get("pay_period"))

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
        insurer_type=insurer_type,
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
    # 1차: 정규화된 입력값 기준 exact match
    row = (
        RateExampleConversionRow.objects
        .filter(
            insurer_type=data.insurer_type,
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

    if row is not None:
        return row

    # 2차: 구분 없음 표시값/빈값 차이를 흡수
    if data.plan_type == "":
        row = (
            RateExampleConversionRow.objects
            .filter(
                insurer_type=data.insurer_type,
                category=RateExample.CAT_CONV,
                insurer=data.insurer,
                product_name=data.product_name,
                plan_type__in=["", "-", "없음", "사용안함"],
                pay_period=data.pay_period,
            )
            .select_related("source_file")
            .order_by("-source_file__created_at", "-id")
            .first()
        )
        if row is not None:
            return row

    # 3차: 상품명/구분/납기의 공백·표시 차이를 Python 비교로 흡수
    candidates = (
        RateExampleConversionRow.objects
        .filter(
            insurer_type=data.insurer_type,
            category=RateExample.CAT_CONV,
            insurer=data.insurer,
        )
        .select_related("source_file")
        .order_by("-source_file__created_at", "-id")[:5000]
    )

    target_product = _match_key(data.product_name)
    target_plan = _match_key(data.plan_type)
    target_period = _match_key(data.pay_period)

    for cand in candidates:
        cand_plan = _match_key(_normalize_plan_type(cand.plan_type))
        if (
            _match_key(cand.product_name) == target_product
            and cand_plan == target_plan
            and _match_key(cand.pay_period) == target_period
        ):
            return cand
    
    logger.warning(
        "[rate_example_calculator] conversion row not found "
        "insurer=%s product=%s plan_type=%s pay_period=%s "
        "target_product_key=%s target_plan_key=%s target_period_key=%s",
        data.insurer,
        data.product_name,
        data.plan_type,
        data.pay_period,
        target_product,
        target_plan,
        target_period,
    )

    label = "수정률" if data.insurer_type == RateExample.TYPE_FIRE else "환산율"
    raise RateExampleCalcError(f"계산에 필요한 {label} 정규화 데이터가 없습니다.")


def _get_pay_row(insurer: str, coverage_type: str, *, insurer_type: str = RateExample.TYPE_LIFE) -> RateExamplePayRow:
    if not coverage_type:
        raise RateExampleCalcError("지급률 조회에 필요한 상품군 정보가 없습니다.")

    row = (
        RateExamplePayRow.objects
        .filter(
            insurer_type=insurer_type,
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


def _build_fire_result(*, data: CalcInput, conv: RateExampleConversionRow, pay: RateExamplePayRow) -> dict[str, Any]:
    """
    손해보험 전용 계산.
    수정률은 RateExampleConversionRow.year1 단일값을 사용한다.
    주의:
    - 손해보험 수정률은 생보 환산율처럼 240을 저장하지 않는다.
    - DB 손보 raw가 2.4이면 DB에도 Decimal("2.4") 그대로 저장한다.
    - 따라서 계산 시 /100 하지 않고 2.4를 배율로 직접 사용한다.
    지급률 매핑:
    - 초회: col_first
    - 13회: col_yr2
    - 14회: col_yr3
    - 15회: col_m36
    """
    mod_multiplier = _fire_mod_to_multiplier(conv.year1)

    def amount(pay_rate):
        return _amount_or_none_with_conversion_multiplier(
            premium=data.premium,
            conversion_multiplier=mod_multiplier,   
            pay_rate=pay_rate,
            commission_rate=data.commission_rate,
        )

    next_month_first = amount(pay.col_first)
    next_month_subtotal = next_month_first or 0
    month_13 = amount(pay.col_yr2)
    month_14 = amount(pay.col_yr3)
    month_15 = amount(pay.col_m36)
    renewal_subtotal = _sum_optional(month_13, month_14, month_15)
    total_amount = next_month_subtotal + renewal_subtotal

    return {
        "insurer": data.insurer,
        "product_name": data.product_name,
        "plan_type": data.plan_type,
        "pay_period": data.pay_period,
        "coverage_type": conv.coverage_type,
        "pay_coverage_type": conv.coverage_type,
        "next_month_first": next_month_first,
        "next_month_subtotal": next_month_subtotal,
        "month_13": month_13,
        "month_14": month_14,
        "month_15": month_15,
        "renewal_subtotal": renewal_subtotal,
        "total_amount": total_amount,
        "total_ratio": _ratio_round((Decimal(total_amount) / data.premium) * Decimal("100")),
    }


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

    if data.insurer == "DB" and use_conversion:
        # DB생명 전용 예외 산식
        # - 13회: 1차년 환산율 + 2차년 환산율
        # - 36회/37회: 1차년 환산율
        # - 나머지 계속분: 각 연차 환산율 사용
        y1 = _pct_to_multiplier(year1_rate)
        y2 = _pct_to_multiplier(year2_rate)
        y3 = _pct_to_multiplier(year3_rate)
        y4 = _pct_to_multiplier(year4_rate)
        y1_plus_y2 = (y1 + y2) if y1 is not None and y2 is not None else None

        month_13 = _amount_or_none_with_conversion_multiplier(
            premium=data.premium,
            conversion_multiplier=y1_plus_y2,
            pay_rate=pay.col_m13,
            commission_rate=data.commission_rate,
        )
        year2 = _amount_or_none_with_conversion_multiplier(
            premium=data.premium,
            conversion_multiplier=y2,
            pay_rate=pay.col_yr2,
            commission_rate=data.commission_rate,
        )
        year3 = _amount_or_none_with_conversion_multiplier(
            premium=data.premium,
            conversion_multiplier=y3,
            pay_rate=pay.col_yr3,
            commission_rate=data.commission_rate,
        )
        month_36 = _amount_or_none_with_conversion_multiplier(
            premium=data.premium,
            conversion_multiplier=y1,
            pay_rate=pay.col_m36,
            commission_rate=data.commission_rate,
        )
        month_37 = _amount_or_none_with_conversion_multiplier(
            premium=data.premium,
            conversion_multiplier=y1,
            pay_rate=pay.col_m37,
            commission_rate=data.commission_rate,
        )
        year4 = _amount_or_none_with_conversion_multiplier(
            premium=data.premium,
            conversion_multiplier=y4,
            pay_rate=pay.col_yr4,
            commission_rate=data.commission_rate,
        )
    else:
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

     DB생명 예외:
    - 13회 = 보험료 × (1차년 환산율 + 2차년 환산율) × 13회/2차년 지급률 × 수수료율
    - 36회 = 보험료 × 1차년 환산율 × 36회 지급률 × 수수료율
    - 37회 = 보험료 × 1차년 환산율 × 37회 지급률 × 수수료율
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

    if data.insurer_type == RateExample.TYPE_FIRE:
        pay = _get_pay_row(data.insurer, conv.coverage_type, insurer_type=RateExample.TYPE_FIRE)
        return _build_fire_result(data=data, conv=conv, pay=pay)

    pay_coverage_type = _resolve_pay_coverage_type(conv)
    pay = _get_pay_row(data.insurer, pay_coverage_type, insurer_type=RateExample.TYPE_LIFE)

    return _build_result(
        data=data,
        coverage_type=conv.coverage_type,
        pay=pay,
        use_conversion=True,
        conv=conv,
    )