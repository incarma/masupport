# django_ma/board/tasks/__init__.py
#
# 이 패키지(board/tasks/)가 관리하는 Celery 태스크 목록:
#   - industry_info.py : 업계정보 기사 수집/정리 (board.tasks.industry_info.*)
#   - holidays.py      : 공휴일 DB 동기화 (board.tasks.holidays.*)
#   - worktask_tasks.py: WorkTask 반복생성/알림 (board.tasks.generate_monthly_worktasks,
#                                                board.tasks.notify_due_worktasks)
#
# ⚠️ 구 파일 안내: board/task.py (단수)는 이 패키지로 통합됨 — deprecation 래퍼 역할만 수행

from .industry_info import collect_board_industry_news, cleanup_old_industry_articles

# 대한민국 공휴일 동기화 태스크 등록 보장
from .holidays import (  # noqa: F401
    sync_kr_holidays_for_year_task,
    sync_kr_holidays_window_task,
)

# WorkTask 반복생성 / 알림 태스크 등록 보장
from .worktask_tasks import (  # noqa: F401
    generate_monthly_worktasks,
    notify_due_worktasks,
)

__all__ = [
    "collect_board_industry_news",
    "cleanup_old_industry_articles",
    "sync_kr_holidays_for_year_task",
    "sync_kr_holidays_window_task",
    "generate_monthly_worktasks",
    "notify_due_worktasks",
]