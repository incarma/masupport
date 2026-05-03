# board/services/worktasks.py
"""
WorkTask 서비스 레이어 — 소유자 격리 SSOT.

핵심 원칙 (worktask.md §6):
    - 뷰는 반드시 이 파일의 함수만 호출한다. 뷰에서 ORM 직접 호출 금지.
    - get_user_queryset / get_user_task 가 소유자 격리의 단일 책임.
    - 이 파일을 수정할 때는 격리 정책 전체를 재검토해야 한다.

⚠️ 절대 수정 주의 파일 (worktask.md §17)
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone

from board.models import WorkTask, WorkTaskAttachment

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.contrib.auth import get_user_model
    User = get_user_model()

logger = logging.getLogger(__name__)


# =============================================================================
# 소유자 격리 SSOT — 모든 쿼리의 진입점
# =============================================================================

def get_user_queryset(user) -> "QuerySet[WorkTask]":
    """
    소유자 격리 SSOT — 모든 목록 쿼리의 시작점.

    ⚠️ 이 함수를 우회하는 어떠한 직접 ORM 호출도 금지.
    select_related 포함으로 N+1 기본 차단.
    """
    return (
        WorkTask.objects
        .filter(owner=user)
        .select_related("category", "owner")
        .prefetch_related("related_users", "attachments")
        .annotate(comment_count=Count("comments", distinct=True))
    )


def get_user_task(user, pk: int) -> WorkTask:
    """
    소유자 격리 SSOT — 상세/수정/삭제의 단일 진입점.

    타인의 pk 접근 시 404 반환 (owner=user 검증 내장).
    ⚠️ get_object_or_404(WorkTask, pk=pk) 단독 호출 금지.
    """
    return get_object_or_404(WorkTask, pk=pk, owner=user)


# =============================================================================
# 필터 적용
# =============================================================================

def apply_filters(qs: "QuerySet[WorkTask]", params: dict) -> "QuerySet[WorkTask]":
    """
    목록 필터 적용.

    params 키:
        ym       : "2026-03" 형식 귀속월
        status   : WorkTask.STATUS_* 값
        category : WorkCategory.code 값

    ym 필터 로직:
        target_ym 이 설정된 자동생성 자식 → target_ym = ym
        target_ym 이 없는 일반 항목        → due_date 가 해당 월 범위 내
        target_ym 이 없고 due_date 도 없음  → 원본 템플릿 항목은 포함
    """
    from django.db.models import Q

    ym       = (params.get("ym")       or "").strip()
    status   = (params.get("status")   or "").strip()
    category = (params.get("category") or "").strip()
    branch   = (params.get("branch")   or "").strip()
    keyword  = (params.get("keyword")  or "").strip()

    # -- 귀속월 필터 --
    if ym:
        try:
            year, month = int(ym[:4]), int(ym[5:7])
            month_start = date(year, month, 1)
            month_end   = date(year, month, calendar.monthrange(year, month)[1])
        except (ValueError, IndexError):
            year = month = None
            month_start = month_end = None

        if year and month:
            qs = qs.filter(
                # ① 자동생성 자식: target_ym 일치
                Q(target_ym=ym)
                # ② 일반 항목: due_date 가 해당 월 범위
                | Q(target_ym="", due_date__gte=month_start, due_date__lte=month_end)
                # ③ due_date 없는 원본 템플릿 포함 (template_task=None)
                | Q(target_ym="", due_date__isnull=True, template_task__isnull=True)
            )

    # -- 상태 필터 --
    if status:
        qs = qs.filter(status=status)

    # -- 카테고리 필터 --
    if category:
        qs = qs.filter(category_id=category)

    # -- 지점 필터 --
    if branch:
        qs = qs.filter(family_branches__contains=[branch])

    # -- 키워드 필터 --
    if keyword:
        qs = qs.filter(
            Q(title__icontains=keyword) | Q(description__icontains=keyword)
        )    
    
    return qs


# =============================================================================
# 생성 / 수정
# =============================================================================

def create_task(user, data: dict) -> WorkTask:
    """
    WorkTask 생성.

    owner=user 강제 주입 — 뷰에서 owner 를 직접 지정하는 것 금지.
    related_users 는 M2M 이므로 save 후 별도 처리.
    """
    related_users = data.pop("related_users", [])

    with transaction.atomic():
        if "family_branches" in data:
            data["family_branches"] = _clean_family_branches(data.get("family_branches"))
        task = WorkTask(**data, owner=user)
        task.full_clean()
        task.save()
        if related_users:
            task.related_users.set(related_users)

    logger.info(
        "WorkTask created: pk=%s owner=%s title=%r",
        task.pk, user.pk, task.title,
    )
    return task


def _clean_family_branches(values):
    """
    WorkTask 영업가족 지점명 목록 정규화.
    - 템플릿에서는 name="family_branches" 다중 hidden input으로 전송
    - DB에는 JSON list[str]로 저장
    - 순서 유지 + 중복 제거
   """
    if not values:
        return []

    if isinstance(values, str):
        values = [values]

    cleaned = []
    seen = set()
    for value in values:
        branch = str(value or "").strip()
        if not branch or branch in seen:
            continue
        cleaned.append(branch)
        seen.add(branch)
    return cleaned


def update_task(task: WorkTask, data: dict) -> WorkTask:
    """
    WorkTask 수정.

    owner 변경은 허용하지 않는다 (격리 보장).
    related_users=None 이면 M2M 변경하지 않음.
    """
    related_users = data.pop("related_users", None)
    # owner 변경 시도 방어
    data.pop("owner",    None)
    data.pop("owner_id", None)
    data["family_branches"] = _clean_family_branches(data.get("family_branches"))

    with transaction.atomic():
        for field, value in data.items():
            setattr(task, field, value)
        task.full_clean()
        task.save()
        if related_users is not None:
            task.related_users.set(related_users)

    logger.info("WorkTask updated: pk=%s owner=%s", task.pk, task.owner_id)
    return task


# =============================================================================
# 상태 변경
# =============================================================================

def mark_done(task: WorkTask) -> WorkTask:
    """완료 처리. status → done, updated_at 자동 갱신."""
    task.status = WorkTask.STATUS_DONE
    task.save(update_fields=["status", "updated_at"])
    logger.info("WorkTask done: pk=%s owner=%s", task.pk, task.owner_id)
    return task


def mark_skipped(task: WorkTask) -> WorkTask:
    """건너뜀 처리. status → skipped, updated_at 자동 갱신."""
    task.status = WorkTask.STATUS_SKIPPED
    task.save(update_fields=["status", "updated_at"])
    logger.info("WorkTask skipped: pk=%s owner=%s", task.pk, task.owner_id)
    return task


def mark_pending(task: WorkTask) -> WorkTask:
    """대기 상태로 초기화 (완료/건너뜀 해제). status → pending."""
    task.status = WorkTask.STATUS_PENDING
    task.save(update_fields=["status", "updated_at"])
    logger.info("WorkTask reset to pending: pk=%s owner=%s", task.pk, task.owner_id)
    return task


# =============================================================================
# 첨부파일
# =============================================================================

def save_attachment(task: WorkTask, file, user) -> WorkTaskAttachment:
    """
    WorkTaskAttachment 저장.

    original_name: 업로드 파일의 원본명 보존 (RFC5987 다운로드에 사용).
    """
    att = WorkTaskAttachment(
        task=task,
        file=file,
        original_name=file.name,
        uploaded_by=user,
    )
    att.save()
    logger.info(
        "WorkTaskAttachment saved: att_pk=%s task_pk=%s owner=%s name=%r",
        att.pk, task.pk, user.pk, file.name,
    )
    return att


def delete_attachment(att: WorkTaskAttachment, user) -> None:
    """
    첨부파일 삭제 + 물리 파일 제거.

    ⚠️ att.task.owner == user 검증은 호출 전(뷰 레이어)에서 보장해야 한다.
    """
    file_path = att.file.name
    att.delete()
    try:
        from django.core.files.storage import default_storage
        if file_path and default_storage.exists(file_path):
            default_storage.delete(file_path)
    except Exception:
        logger.exception(
            "첨부파일 물리 삭제 실패: path=%r owner=%s", file_path, user.pk,
        )


# =============================================================================
# 반복 자동생성 (Celery 배치용 — Phase 4)
# =============================================================================

def generate_monthly_tasks(year: int, month: int) -> int:
    """
    반복 원본(template_task=None, recurrence_type≠none) →
    해당 월 자식 WorkTask 자동생성.

    중복 방지: (template_task, target_ym) 조합이 이미 존재하면 skip.
    생성된 레코드 수 반환.
    """
    target_ym = f"{year}-{month:02d}"

    # 반복 원본만 조회
    templates = WorkTask.objects.filter(
        template_task__isnull=True,
    ).exclude(recurrence_type=WorkTask.RECURRENCE_NONE)

    created_count = 0
    for tmpl in templates:
        # 중복 방지
        if WorkTask.objects.filter(template_task=tmpl, target_ym=target_ym).exists():
            continue

        due = _calc_due_date(tmpl, year, month)

        try:
            with transaction.atomic():
                child = WorkTask.objects.create(
                    owner=tmpl.owner,
                    category=tmpl.category,
                    title=tmpl.title,
                    description=tmpl.description,
                    due_date=due,
                    recurrence_type=WorkTask.RECURRENCE_NONE,   # 자식은 반복 없음
                    template_task=tmpl,
                    target_ym=target_ym,
                    status=WorkTask.STATUS_PENDING,
                    priority=tmpl.priority,
                )
                if tmpl.related_users.exists():
                    child.related_users.set(tmpl.related_users.all())
            created_count += 1
        except Exception:
            logger.exception(
                "반복 WorkTask 생성 실패: template_pk=%s target_ym=%s",
                tmpl.pk, target_ym,
            )

    logger.info(
        "generate_monthly_tasks: %s-%02d created=%s", year, month, created_count,
    )
    return created_count


def _calc_due_date(tmpl: WorkTask, year: int, month: int) -> date | None:
    """반복 유형별 마감일 계산."""
    _, last_day = calendar.monthrange(year, month)

    if tmpl.recurrence_type == WorkTask.RECURRENCE_MONTHLY_OPEN:
        return date(year, month, 10)
    elif tmpl.recurrence_type == WorkTask.RECURRENCE_MONTHLY_MID:
        return date(year, month, 20)
    elif tmpl.recurrence_type == WorkTask.RECURRENCE_MONTHLY_END:
        return date(year, month, last_day)
    elif tmpl.recurrence_type == WorkTask.RECURRENCE_DAILY:
        return date(year, month, 1)
    elif tmpl.recurrence_type == WorkTask.RECURRENCE_CUSTOM:
        day = min(tmpl.recurrence_day or 1, last_day)
        return date(year, month, day)
    return None


# =============================================================================
# 알림 대상 조회 (Celery 배치용 — Phase 4)
# =============================================================================

def get_pending_notify_tasks() -> "QuerySet[WorkTask]":
    """
    알림 발송 대상 조회.

    조건:
        - is_notified=False (미발송)
        - due_date 가 설정되어 있음
        - status 가 done/skipped 가 아닌 미완료
        (due_date ≤ today + notify_days_before 필터는 Celery 태스크에서 추가 처리)
    """
    return (
        WorkTask.objects
        .filter(is_notified=False, due_date__isnull=False)
        .exclude(status__in=[WorkTask.STATUS_DONE, WorkTask.STATUS_SKIPPED])
        .select_related("owner", "category")
        .order_by("owner_id", "due_date")
    )