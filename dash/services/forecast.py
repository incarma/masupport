# django_ma/dash/services/forecast.py
from __future__ import annotations

import logging

from dash.models import SalesDailyAgg, SalesForecast, SalesForecastDaily

logger = logging.getLogger(__name__)


def check_agg_exists(ym: str, scope: str, scope_key: str, categories) -> bool:
    return SalesDailyAgg.objects.filter(
        ym=ym,
        scope_type=scope,
        scope_key=scope_key,
        category__in=categories,
    ).exists()


def check_forecast_exists(
    ym: str,
    asof_day: int,
    scope: str,
    scope_key: str,
    categories,
    model_ver: str,
) -> bool:
    return SalesForecast.objects.filter(
        ym=ym,
        scope_type=scope,
        scope_key=scope_key,
        category__in=categories,
        model_ver=model_ver,
        asof_day__lte=asof_day,
        pred_total_p50__isnull=False,
    ).exists()


def get_category_payload(
    ym: str,
    scope: str,
    scope_key: str,
    category: str,
    asof_day: int,
    labels: list[int],
    model_ver: str,
) -> dict:
    """단일 카테고리의 실측 누적선 + 예측 데이터 반환."""
    rows = SalesDailyAgg.objects.filter(
        ym=ym, scope_type=scope, scope_key=scope_key, category=category
    ).values("day", "cumsum")
    actual_map = {r["day"]: int(r["cumsum"] or 0) for r in rows}
    actual_cumsum = [actual_map.get(d, 0) for d in labels]

    fc = (
        SalesForecast.objects.filter(
            ym=ym,
            scope_type=scope,
            scope_key=scope_key,
            category=category,
            model_ver=model_ver,
            asof_day__lte=asof_day,
        )
        .order_by("-asof_day", "-created_at")
        .first()
    )

    if not fc:
        return {
            "category": category,
            "asof_day": asof_day,
            "actual_cumsum": actual_cumsum,
            "pred": None,
        }

    days = SalesForecastDaily.objects.filter(forecast=fc).values(
        "day", "pred_cumsum_p10", "pred_cumsum_p50", "pred_cumsum_p90"
    )
    pred_map = {r["day"]: r for r in days}

    def _series(key):
        return [
            (None if (pred_map.get(d) or {}).get(key) is None else int(pred_map[d][key]))
            for d in labels
        ]

    return {
        "category": category,
        "asof_day": int(fc.asof_day),
        "generated_at": fc.created_at.isoformat(),
        "actual_cumsum": actual_cumsum,
        "pred": {
            "p10": _series("pred_cumsum_p10"),
            "p50": _series("pred_cumsum_p50"),
            "p90": _series("pred_cumsum_p90"),
            "totals": {
                "p10": fc.pred_total_p10,
                "p50": fc.pred_total_p50,
                "p90": fc.pred_total_p90,
            },
            "actual_to_date": fc.actual_to_date,
        },
    }
