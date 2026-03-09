# django_ma/dash/tasks.py
from __future__ import annotations

"""
Dash Celery task entrypoint (SSOT wrapper)
------------------------------------------------------------
- Celery autodiscover는 기본적으로 `dash.tasks` 경로를 본다.
- 실제 집계/예측 실행 로직은 `dash.task_runtime`에 두고,
  여기서는 worker가 안정적으로 task를 등록할 수 있도록 re-export만 수행한다.
- 목적:
  1) legacy 단일 tasks.py 구현 제거
  2) runtime 로직 단일화
  3) Celery worker 등록 경로를 `dash.tasks.*`로 고정
"""

from dash.task_runtime import (  # noqa:F401
    build_sales_aggs_hourly,
    build_sales_forecasts_daily,
    build_sales_forecasts_for_yms,
    build_sales_forecasts_hourly,
    dash_refresh_agg_and_forecast,
)

__all__ = [
    "build_sales_aggs_hourly",
    "build_sales_forecasts_daily",
    "build_sales_forecasts_for_yms",
    "build_sales_forecasts_hourly",
    "dash_refresh_agg_and_forecast",
]