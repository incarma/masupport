"""
Celery config for web_ma project.

- settings의 CELERY_*를 자동 로드
- INSTALLED_APPS 내 tasks.py 자동 탐색
- Celery beat로 운영형 파이프라인 스케줄(집계/예측 자동 생성)
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ma.settings")

app = Celery("web_ma")
app.config_from_object("django.conf:settings", namespace="CELERY")

# ✅ 모든 INSTALLED_APPS에서 tasks.py 자동 탐색
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")


# =============================================================================
# Celery Beat Schedule (SSOT)
# - 매시간/매일 파이프라인: SalesDailyAgg + Forecast
# =============================================================================
app.conf.beat_schedule = {
    # 매시간 10분: 집계 갱신(이번달/전월) → SalesDailyAgg(또는 유사 집계 테이블) 최신화
    "dash-agg-hourly": {
        "task": "dash.tasks.pipeline.build_sales_aggs_hourly",
        "schedule": crontab(minute=10),
        "args": (),
    },
    # 매일 02:10: 모델/예측 갱신 → Forecast 생성/업데이트
    "dash-forecast-daily": {
        "task": "dash.tasks.pipeline.build_sales_forecasts_daily",
        "schedule": crontab(hour=2, minute=10),
        "args": (),
    },
    # (선택) 매시간 예측까지 갱신하고 싶으면 활성화
    # "dash-forecast-hourly": {
    #     "task": "dash.tasks.pipeline.build_sales_forecasts_hourly",
    #     "schedule": crontab(minute=20),
    #     "args": (),
    # },
}
