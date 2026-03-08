# django_ma/dash/services/agg.py
from __future__ import annotations

import calendar
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from dash.models import SalesRecord, SalesDailyAgg
import logging

logger = logging.getLogger(__name__)

def _last_day(ym: str) -> int:
    y, m = map(int, ym.split("-"))
    return calendar.monthrange(y, m)[1]

def _scope_filter(scope_type: str, scope_key: str):
    """
    Scope filter 안정화
    - user NULL 대응
    - snapshot 기반 fallback
    """

    scope_key = (scope_key or "").strip()

    if scope_type == "all":
        return Q()

    if not scope_key:
        return Q()

    if scope_type == "part":
        return (
            Q(user__isnull=False, user__part=scope_key)
            | Q(part_snapshot=scope_key)
        )

    if scope_type == "branch":
        return (
            Q(user__isnull=False, user__branch=scope_key)
            | Q(branch_snapshot=scope_key)
        )

    return Q()

def _qs_category(qs, category: str):
    # dash_sales와 “동일 기준”으로 맞추는 게 중요
    if category == "long":
        return qs.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납")
    if category == "car":
        return qs.filter(life_nl="자동차")
    if category == "long_nonlife":
        return qs.filter(life_nl="손보").exclude(pay_method__icontains="일시납")
    if category == "long_life":
        return qs.filter(life_nl="생보").exclude(pay_method__icontains="일시납")
    return qs.none()

@transaction.atomic
def build_daily_agg_for_month(ym: str, scope_type: str, scope_key: str) -> None:
    base = (
        SalesRecord.objects
        .filter(ym=ym)
        .exclude(receipt_date__isnull=True)
        .filter(_scope_filter(scope_type, scope_key))
    )

    last_day = _last_day(ym)

    for category in ["long", "car", "long_nonlife", "long_life"]:
        qs = _qs_category(base, category)

        rows = (
            qs.values("receipt_date")
              .annotate(v=Sum(Coalesce("receipt_amount", 0)))
              .order_by("receipt_date")
        )

        logger.debug(
            "[dash.agg] ym=%s scope=%s/%s category=%s rows=%s",
            ym, scope_type, scope_key, category, rows.count()
        )
        
        day_amount = {r["receipt_date"].day: int(r["v"] or 0) for r in rows if r["receipt_date"]}

        running = 0
        for d in range(1, last_day + 1):
            amt = int(day_amount.get(d, 0))
            running += amt

            SalesDailyAgg.objects.update_or_create(
                ym=ym, day=d, scope_type=scope_type, scope_key=scope_key, category=category,
                defaults={"amount": amt, "cumsum": running},
            )
