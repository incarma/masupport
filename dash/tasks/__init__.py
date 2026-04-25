# django_ma/dash/tasks/__init__.py
# ------------------------------------------------------------
# ✅ dash.tasks public Celery task surface
# ------------------------------------------------------------
# 목적:
# - web_ma/celery.py beat_schedule에서 사용하는 task name을 안정적으로 유지
# - 실제 구현은 dash.tasks.pipeline에 두고, 외부 등록명은 dash.tasks.* 로 고정
# - celery inspect registered 기준:
#   * dash.tasks.build_sales_aggs_hourly
#   * dash.tasks.build_sales_forecasts_daily
#   * dash.tasks.build_sales_forecasts_hourly
#   * dash.tasks.build_sales_forecasts_for_yms
# ------------------------------------------------------------

from __future__ import annotations

from celery import shared_task

from .pipeline import (
    build_sales_aggs_hourly as _pipeline_build_sales_aggs_hourly,
    build_sales_forecasts_daily as _pipeline_build_sales_forecasts_daily,
    build_sales_forecasts_for_yms as _pipeline_build_sales_forecasts_for_yms,
    build_sales_forecasts_hourly as _pipeline_build_sales_forecasts_hourly,
)


@shared_task(
    bind=True,
    ignore_result=True,
    name="dash.tasks.build_sales_aggs_hourly",
)
def build_sales_aggs_hourly(self):
    return _pipeline_build_sales_aggs_hourly.apply(args=()).get()


@shared_task(
    bind=True,
    ignore_result=True,
    name="dash.tasks.build_sales_forecasts_daily",
)
def build_sales_forecasts_daily(self):
    return _pipeline_build_sales_forecasts_daily.apply(args=()).get()


@shared_task(
    bind=True,
    ignore_result=True,
    name="dash.tasks.build_sales_forecasts_hourly",
)
def build_sales_forecasts_hourly(self):
    return _pipeline_build_sales_forecasts_hourly.apply(args=()).get()


@shared_task(
    bind=True,
    ignore_result=True,
    name="dash.tasks.build_sales_forecasts_for_yms",
)
def build_sales_forecasts_for_yms(self, yms=None):
    return _pipeline_build_sales_forecasts_for_yms.apply(args=(yms or [],)).get()


@shared_task(
    bind=True,
    ignore_result=True,
    name="dash.tasks.dash_refresh_agg_and_forecast",
)
def dash_refresh_agg_and_forecast(self):
    build_sales_aggs_hourly.delay()
    build_sales_forecasts_hourly.delay()
    return {"status": "queued"}


__all__ = [
    "build_sales_aggs_hourly",
    "build_sales_forecasts_daily",
    "build_sales_forecasts_hourly",
    "build_sales_forecasts_for_yms",
    "dash_refresh_agg_and_forecast",
]