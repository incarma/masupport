# django_ma/board/tasks/holidays.py
"""
대한민국 공휴일 Celery 태스크.

주의:
- task name은 web_ma/celery.py beat_schedule의 "task" 값과 정확히 일치해야 한다.
- 실제 수집/DB upsert 로직은 board.services.holidays가 SSOT다.
"""

from __future__ import annotations

import logging

from celery import shared_task

from board.services.holidays import (
    sync_kr_holidays_for_year,
    sync_kr_holidays_window,
)

logger = logging.getLogger(__name__)


@shared_task(name="board.tasks.holidays.sync_kr_holidays_for_year")
def sync_kr_holidays_for_year_task(year: int, *, force: bool = False) -> dict:
    """
    특정 연도 공휴일 동기화.
    """
    logger.info("[kr_holidays] celery year sync start year=%s force=%s", year, force)
    result = sync_kr_holidays_for_year(year, force=force)
    logger.info("[kr_holidays] celery year sync done result=%s", result)
    return result


@shared_task(name="board.tasks.holidays.sync_kr_holidays_window")
def sync_kr_holidays_window_task(*, force: bool = False) -> dict:
    """
    settings 기준 window 공휴일 동기화.
    기본 범위: 현재연도-1 ~ 현재연도+2
    """
    logger.info("[kr_holidays] celery window sync start force=%s", force)
    result = sync_kr_holidays_window(force=force)
    logger.info("[kr_holidays] celery window sync done result=%s", result)
    return result