"""
Celery config for web_ma project.

- settings의 CELERY_*를 자동 로드
- INSTALLED_APPS 내 tasks.py 자동 탐색
- Celery beat로 운영형 파이프라인 스케줄(집계/예측/수집 자동 생성)

⚠️ beat_schedule 등록 원칙 (Scenario α 방지)
- "task" 값은 반드시 워커에 등록된 태스크명과 정확히 일치해야 한다.
- 불일치 시 태스크가 실행되지 않고 에러도 발생하지 않아 탐지가 매우 어렵다.
- 등록명 확인 명령: celery -A web_ma inspect registered
- tasks.py 또는 tasks/__init__.py의 @shared_task(name=) 값이 SSOT다.
"""

from __future__ import annotations

import logging
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ma.settings")

app = Celery("web_ma")
app.config_from_object("django.conf:settings", namespace="CELERY")

# ✅ INSTALLED_APPS에서 tasks.py 자동 탐색
app.autodiscover_tasks()
# ⚠️ board/tasks/ 는 패키지 구조이므로 autodiscover_tasks() 단독 탐색 불가
# → 패키지 루트를 명시적으로 추가 탐색하여 board 태스크 등록 보장
app.autodiscover_tasks(["board.tasks"])

logger = logging.getLogger(__name__)


def _safe_args(value, *, default=()):
    if value is None:
        return default
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    logger.warning("[celery] invalid beat args ignored: %r", value)
    return default


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")


# =============================================================================
# Celery Beat Schedule (SSOT)
# =============================================================================
app.conf.beat_schedule = {
    # ── board: 업계정보 기사 수집 ───────────────────────────────────────────
    # 6시간 주기: 00:05 / 06:05 / 12:05 / 18:05
    "board-industry-news-collect": {
        "task": "board.tasks.industry_info.collect_board_industry_news",
        "schedule": crontab(hour="0,6,12,18", minute=5),
        "args": (),
    },

    # ── board: 업계정보 기사 정리 ───────────────────────────────────────────
    # 매일 03:00: 14일 이전 기사 삭제 (북마크된 기사 보존)
    # ✅ 14일 보존: 추천 알고리즘 탐색 범위(14일)와 일치
    "board-industry-cleanup-daily": {
        "task": "board.tasks.industry_info.cleanup_old_industry_articles",
        "schedule": crontab(hour=3, minute=0),
        "args": _safe_args((14,)),
    },

    # ── dash: 매출 집계 ─────────────────────────────────────────────────────
    # 매시간 10분: 집계 갱신(이번달/전월) → SalesDailyAgg 최신화
    "dash-agg-hourly": {
         "task": "dash.tasks.build_sales_aggs_hourly",
        "schedule": crontab(minute=10),
        "args": (),
    },

    # ── dash: 예측 갱신 ─────────────────────────────────────────────────────
    # 매일 02:10: 모델/예측 갱신 → Forecast 생성/업데이트
    "dash-forecast-daily": {
        "task": "dash.tasks.build_sales_forecasts_daily",
        "schedule": crontab(hour=2, minute=10),
        "args": (),
    },

    # 매시간 20분: 집계 갱신 직후 예측도 최신화 (집계 :10 → 예측 :20 순서 보장)
    "dash-forecast-hourly": {
        "task": "dash.tasks.build_sales_forecasts_hourly",
        "schedule": crontab(minute=20),
        "args": (),
    },
    
    # ------------------------------------------------------------------
    # WorkTask 반복 자동생성 — 매달 1일 00:10
    # board/tasks.py: generate_monthly_worktasks
    # ------------------------------------------------------------------
    "generate-monthly-worktasks": {
        "task":     "board.tasks.generate_monthly_worktasks",
        "schedule": crontab(day_of_month="1", hour="0", minute="10"),
    },

    # ------------------------------------------------------------------
    # WorkTask 마감 알림 이메일 — 매일 08:00
    # board/tasks.py: notify_due_worktasks
    # ------------------------------------------------------------------
    "notify-due-worktasks": {
        "task":     "board.tasks.notify_due_worktasks",
        "schedule": crontab(hour="8", minute="0"),
    },
}