# board/tasks.py
"""
WorkTask Celery 태스크.

⚠️ 태스크명 3자 완전 일치 필수 (worktask.md §11.1):
    beat_schedule "task" 값
    = @shared_task(name=...) 등록명
    = celery inspect registered 결과
    → 셋이 완전 일치하지 않으면 태스크가 실행되지 않는다.

확인 명령:
    celery -A web_ma inspect registered | grep worktask
"""

from __future__ import annotations

import logging
from collections import defaultdict

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# 반복 WorkTask 자동생성
# beat_schedule 키: "generate-monthly-worktasks"
# 스케줄: 매달 1일 00:10 (celery.py beat_schedule 참조)
# =============================================================================

@shared_task(
    name="board.tasks.generate_monthly_worktasks",  # ← beat "task" 값과 반드시 일치
    bind=True,
    max_retries=3,
    default_retry_delay=300,   # 5분 후 재시도
)
def generate_monthly_worktasks(self, year: int | None = None, month: int | None = None):
    """
    반복 원본 → 해당 월 자식 WorkTask 자동생성.

    year/month 미전달 시 현재 월 기준 실행.
    중복 방지 로직은 services.worktasks.generate_monthly_tasks 에 위임.

    즉시 실행 테스트:
        from board.tasks import generate_monthly_worktasks
        generate_monthly_worktasks.apply_async()
    """
    from board.services.worktasks import generate_monthly_tasks

    today = timezone.localdate()
    y = year  or today.year
    m = month or today.month

    logger.info("generate_monthly_worktasks START: %s-%02d", y, m)
    try:
        created = generate_monthly_tasks(y, m)
        logger.info("generate_monthly_worktasks DONE: created=%s", created)
        return {"year": y, "month": m, "created": created}
    except Exception as exc:
        logger.exception("generate_monthly_worktasks FAILED: %s-%02d", y, m)
        raise self.retry(exc=exc)


# =============================================================================
# 마감 D-N일 알림 이메일 발송
# beat_schedule 키: "notify-due-worktasks"
# 스케줄: 매일 08:00 (celery.py beat_schedule 참조)
# =============================================================================

@shared_task(
    name="board.tasks.notify_due_worktasks",        # ← beat "task" 값과 반드시 일치
    bind=True,
    max_retries=2,
    default_retry_delay=600,   # 10분 후 재시도
)
def notify_due_worktasks(self):
    """
    마감 D-N일 이내 미완료 WorkTask owner 별 이메일 알림 발송.

    발송 규칙 (worktask.md §11.3):
        - is_notified=False  AND  due_date <= 오늘 + notify_days_before
        - 발송 완료 후 즉시 is_notified=True 갱신 (update_fields)
        - owner 별 이메일에 본인 업무만 포함 — 타인 업무 노출 구조적 불가

    즉시 실행 테스트:
        from board.tasks import notify_due_worktasks
        notify_due_worktasks.apply_async()
    """
    from board.models import WorkTask
    from board.services.worktasks import get_pending_notify_tasks

    today = timezone.localdate()

    # owner 별 그룹핑 — 구조적으로 본인 업무만 포함
    owner_tasks: dict[str, list] = defaultdict(list)
    for task in get_pending_notify_tasks():
        days_left = (task.due_date - today).days
        if days_left <= task.notify_days_before:
            owner_tasks[task.owner_id].append(task)

    sent_count    = 0
    notified_pks  = []

    for owner_id, tasks in owner_tasks.items():
        owner = tasks[0].owner   # select_related 로 이미 로드
        email = getattr(owner, "email", None)
        if not email:
            logger.warning("notify_due_worktasks: owner=%s 이메일 없음 — skip", owner_id)
            continue

        # 메일 본문 구성
        lines = [
            f"안녕하세요 {owner.name}님,",
            "",
            "마감이 임박한 업무 항목이 있습니다.",
            "",
        ]
        for t in tasks:
            d = (t.due_date - today).days
            dday = f"D-{d}" if d > 0 else ("D-day" if d == 0 else f"초과 {abs(d)}일")
            lines.append(
                f"  • [{t.category.label}] {t.title}"
                f" (마감: {t.due_date.strftime('%Y-%m-%d')}, {dday})"
            )
        lines += ["", "업무 관리 시스템에서 확인해 주세요."]

        try:
            send_mail(
                subject       = f"[업무관리] 마감 임박 업무 {len(tasks)}건 알림",
                message       = "\n".join(lines),
                from_email    = settings.DEFAULT_FROM_EMAIL,
                recipient_list = [email],
                fail_silently = False,
            )
            sent_count += 1
            notified_pks.extend([t.pk for t in tasks])
            logger.info(
                "notify_due_worktasks: 발송 owner=%s tasks=%s",
                owner_id, [t.pk for t in tasks],
            )
        except Exception:
            logger.exception("notify_due_worktasks: 발송 실패 owner=%s", owner_id)
            # 발송 실패 시 is_notified 갱신 안 함 → 다음 실행 시 재시도

    # 발송 완료 항목만 is_notified=True 갱신 (중복 발송 방지)
    if notified_pks:
        WorkTask.objects.filter(pk__in=notified_pks).update(is_notified=True)
        logger.info("notify_due_worktasks: is_notified 갱신 pks=%s", notified_pks)

    logger.info(
        "notify_due_worktasks DONE: sent_owners=%s notified=%s",
        sent_count, len(notified_pks),
    )
    return {"sent_owners": sent_count, "notified_tasks": len(notified_pks)}