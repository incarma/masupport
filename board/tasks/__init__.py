# django_ma/board/tasks/__init__.py

from .industry_info import collect_board_industry_news, cleanup_old_industry_articles

# 대한민국 공휴일 동기화 태스크 등록 보장
from .holidays import (  # noqa: F401
    sync_kr_holidays_for_year_task,
    sync_kr_holidays_window_task,
)

__all__ = [
    "collect_board_industry_news",
    "cleanup_old_industry_articles",
    "sync_kr_holidays_for_year_task",
    "sync_kr_holidays_window_task",
]