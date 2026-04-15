# django_ma/board/tasks/industry_info.py

from __future__ import annotations

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from audit.constants import ACTION
from audit.services import log_action

from board.industry_models import IndustryArticle, IndustryCollectJobLog
from board.services.industry_news import default_queries, fetch_naver_news, parse_naver_item


@shared_task(
    bind=True,
    name="board.tasks.industry_info.collect_board_industry_news",  # ✅ Scenario α 방지 SSOT
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def collect_board_industry_news(self, query: str = "", pages: int = 2, actor_id: str = ""):
    """
    네이버 뉴스 배치 수집 task

    설계 원칙:
    - 사용자 요청 시 외부 API를 직접 호출하지 않음
    - 배치 수집 + DB 조회 구조 유지
    """
    User = get_user_model()
    actor = User.objects.filter(pk=actor_id).first() if actor_id else None
    queries = [query] if query else default_queries()

    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    for one_query in queries:
        job = IndustryCollectJobLog.objects.create(
            source="naver",
            query=one_query,
            actor=actor,
            requested_at=timezone.now(),
            status=IndustryCollectJobLog.STATUS_READY,
        )

        try:
            fetched_count = 0
            inserted_count = 0
            skipped_count = 0

            for page in range(pages):
                start = page * 20 + 1
                payload = fetch_naver_news(one_query, display=20, start=start, sort="date")
                items = payload.get("items", [])
                fetched_count += len(items)

                for item in items:
                    defaults = parse_naver_item(item, one_query)
                    _, created = IndustryArticle.objects.update_or_create(
                        normalized_hash=defaults["normalized_hash"],
                        defaults=defaults,
                    )
                    if created:
                        inserted_count += 1
                    else:
                        skipped_count += 1

            job.status = IndustryCollectJobLog.STATUS_SUCCESS
            job.fetched_count = fetched_count
            job.inserted_count = inserted_count
            job.skipped_count = skipped_count
            job.finished_at = timezone.now()
            job.save(
                update_fields=[
                    "status",
                    "fetched_count",
                    "inserted_count",
                    "skipped_count",
                    "finished_at",
                    # ✅ updated_at 제외: auto_now=True 필드는 update_fields 명시 불필요
                ]
            )

            total_inserted += inserted_count
            total_skipped += skipped_count

            if actor:
                log_action(
                    None,
                    ACTION.SUPPORT_COLLECT_RUN,
                    object_type="IndustryCollectJobLog",
                    object_id=str(job.id),
                    meta={
                        "source": "naver",
                        "query": one_query,
                        "fetched_count": fetched_count,
                        "inserted_count": inserted_count,
                        "skipped_count": skipped_count,
                        "source_app": "board",
                    },
                )

        except Exception as exc:
            total_errors += 1
            job.status = IndustryCollectJobLog.STATUS_FAIL
            job.error_count = 1
            job.finished_at = timezone.now()
            job.message = str(exc)
            job.save(
                update_fields=[
                    "status",
                    "error_count",
                    "finished_at",
                    "message",
                    # ✅ updated_at 제외
                ]
            )

            if actor:
                log_action(
                    None,
                    ACTION.SUPPORT_COLLECT_FAIL,
                    object_type="IndustryCollectJobLog",
                    object_id=str(job.id),
                    success=False,
                    reason=str(exc),
                    meta={
                        "source": "naver",
                        "query": one_query,
                        "source_app": "board",
                    },
                )
            raise

    return {
        "queries": len(queries),
        "inserted_count": total_inserted,
        "skipped_count": total_skipped,
        "error_count": total_errors,
    }