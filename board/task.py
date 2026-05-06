# board/task.py — DEPRECATED
"""
⚠️  이 파일은 board/tasks/worktask_tasks.py 로 이동되었습니다.
    하위 호환성을 위해 re-export 래퍼만 유지합니다.
    새 코드는 board/tasks/worktask_tasks.py 를 직접 참조하세요.
"""

from board.tasks.worktask_tasks import (  # noqa: F401
    generate_monthly_worktasks,
    notify_due_worktasks,
)
