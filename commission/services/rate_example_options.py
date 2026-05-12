# django_ma/commission/services/rate_example_options.py
from __future__ import annotations

"""
RateExample 옵션 조회 서비스.

역할:
- rate_example_home.html의 계산 입력 테이블에서 사용하는
  보험사 → 상품명 → 구분 → 납기 연동 옵션을 제공한다.
- 정규화 master인 RateExampleConversionRow를 SSOT로 사용한다.
- view에서는 쿼리 로직을 직접 작성하지 않고 본 서비스를 호출한다.

주의:
- 계산 로직은 포함하지 않는다.
- 환산율/수정률 정규화 데이터(conv)만 조회한다.
- 기본 옵션은 환산율(conv) 기준이지만,
- IBK 상품군은 지급률(pay) 테이블을 기준으로 제공한다.
"""

from dataclasses import dataclass

from commission.models import RateExample, RateExampleConversionRow, RateExamplePayRow


IBK_PREFIX = "[IBK]"


@dataclass(frozen=True)
class RateExampleOptionQuery:
    """옵션 조회 조건."""

    kind: str
    insurer: str = ""
    product_name: str = ""
    plan_type: str = ""


VALID_KINDS = {
    "insurers",
    "products",
    "plan_types",
    "pay_periods",
}


def _clean(value: object) -> str:
    """GET 파라미터/DB 값을 안전한 문자열로 정규화한다."""
    return str(value or "").strip()


def _base_qs():
    """
    환산율/수정률 정규화 row 기본 queryset.

    [SSOT]
    - insurer_type='life'
    - category='conv'
    - 정규화 row 기준 옵션 조회
    """
    return RateExampleConversionRow.objects.filter(
        insurer_type=RateExample.TYPE_LIFE,
        category=RateExample.CAT_CONV,
    )


def _distinct_values(field: str, qs) -> list[str]:
    """빈 값 제거 + distinct + 한글 정렬."""
    values = (
        qs.exclude(**{f"{field}__isnull": True})
        .exclude(**{field: ""})
        .values_list(field, flat=True)
        .distinct()
    )
    return sorted({_clean(v) for v in values if _clean(v)}, key=lambda x: x)


def _ibk_product_options() -> list[str]:
    """
    IBK 상품군 옵션.

    IBK는 환산율 정규화 테이블이 아니라 지급률 정규화 테이블의
    coverage_type("[IBK]상품군")을 상품명 드랍다운으로 사용한다.
    """
    values = (
        RateExamplePayRow.objects
        .filter(
            insurer_type=RateExample.TYPE_LIFE,
            category=RateExample.CAT_PAY,
            insurer="IBK",
            tier="5천만↑",
        )
        .exclude(coverage_type="")
        .values_list("coverage_type", flat=True)
        .distinct()
    )
    items = []
    for value in values:
        text = _clean(value)
        if not text:
            continue
        if text.startswith(IBK_PREFIX):
            text = text[len(IBK_PREFIX):]
        if text:
            items.append(text)
    return sorted(set(items), key=lambda x: x)


def get_rate_example_options(query: RateExampleOptionQuery) -> list[str]:
    """
    옵션 목록 조회.

    kind:
    - insurers    : 보험사 목록
    - products    : 특정 보험사의 상품명 목록
    - plan_types  : 특정 보험사+상품명의 구분 목록
    - pay_periods : 특정 보험사+상품명+구분의 납기 목록
    """
    kind = _clean(query.kind)
    if kind not in VALID_KINDS:
        return []

    if kind == "insurers":
        # 기존 생보 보험사 목록을 우선 제공하되,
        # 정규화 master에 실제 존재하는 보험사만 쓰려면 아래 qs 방식으로 변경 가능.
        return list(RateExample.LIFE_INSURERS)

    qs = _base_qs()

    insurer = _clean(query.insurer)
    product_name = _clean(query.product_name)
    plan_type = _clean(query.plan_type)

    if insurer:
        qs = qs.filter(insurer=insurer)

    if kind == "products":
        if not insurer:
            return []
        if insurer == "IBK":
            return _ibk_product_options()
        return _distinct_values("product_name", qs)

    if kind == "plan_types":
        if insurer == "IBK":
            return []
        if not insurer or not product_name:
            return []
        qs = qs.filter(product_name=product_name)
        return _distinct_values("plan_type", qs)

    if kind == "pay_periods":
        if insurer == "IBK":
            return []
        if not insurer or not product_name:
            return []
        qs = qs.filter(product_name=product_name)
        if plan_type:
            qs = qs.filter(plan_type=plan_type)
        return _distinct_values("pay_period", qs)

    return []