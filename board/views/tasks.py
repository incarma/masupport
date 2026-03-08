# django_ma/board/views/tasks.py
# =========================================================
# Task Views (직원업무) - superuser only
# - 목록/상세/작성/수정
# - 인라인 업데이트(담당자/상태)
# =========================================================

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required

from audit.constants import ACTION
from audit.services import log_action

from ..constants import (
    TASK_ALLOWED_GRADES,
    INLINE_ACTIONS,
    PER_PAGE_CHOICES,
    TASK_CATEGORY_VALUES,
    TASK_DETAIL, TASK_LIST, TASK_EDIT,
    TASK_ATTACHMENT_DOWNLOAD,
)
from ..forms import TaskCommentForm, TaskForm
from ..models import TASK_STATUS_CHOICES, Task, TaskAttachment, TaskComment
from ..services.comments import handle_comments_actions
from ..services.inline_update import inline_update_common
from ..services.listing import (
    apply_common_list_filters,
    apply_keyword_filter,
    build_query_string_without_page,
    get_handlers,
    paginate,
    read_list_params,
)
from ..services.attachments import save_attachments


__all__ = [
    # pages
    "task_list",
    "task_create",
    "task_detail",
    "task_edit",
    # ajax
    "ajax_update_task_field",
    "ajax_update_task_field_detail",
]


TASK_STATUS_VALUES = [s[0] for s in TASK_STATUS_CHOICES]



logger = logging.getLogger(__name__)


def _safe_action(name: str, default: str) -> str:
    return getattr(ACTION, name, default)


def _user_storage_key(user) -> str:
    key = getattr(user, "emp_id", None) or getattr(user, "user_id", None) or getattr(user, "id", "")
    return str(key or "")


def _safe_int_ids(values) -> list[int]:
    result: list[int] = []
    for value in values or []:
        s = str(value or "").strip()
        if not s.isdigit():
            continue
        result.append(int(s))
    return result


def _task_meta(task, *, extra: dict | None = None) -> dict:
    meta = {
        "task_id": getattr(task, "pk", None),
        "category": getattr(task, "category", "") or "",
        "status": getattr(task, "status", "") or "",
        "handler": getattr(task, "handler", "") or "",
        "user_id": getattr(task, "user_id", "") or "",
        "user_branch": getattr(task, "user_branch", "") or "",
    }
    if extra:
        meta.update(extra)
    return meta


def _log_task_action(request: HttpRequest, action_name: str, *, task=None, success: bool, reason: str = "", meta: dict | None = None) -> None:
    try:
        log_action(
            request,
            action_name,
            obj=task,
            object_type="board_task",
            object_id=str(getattr(task, "pk", "") or ""),
            meta=meta or _task_meta(task, extra={}) if task is not None else (meta or {}),
            success=success,
            reason=reason or "",
        )
    except Exception:
        logger.exception("task audit logging failed")


def _json_message(response: JsonResponse) -> str:
    try:
        return (response.json().get("message") or "").strip()
    except Exception:
        return ""


def _inline_action_to_audit_name(action: str) -> str:
    mapping = {
        "status": _safe_action("BOARD_STATUS_UPDATE", "board_status_update"),
        "handler": _safe_action("BOARD_HANDLER_UPDATE", "board_handler_update"),
    }
    return mapping.get(action, _safe_action("BOARD_INLINE_UPDATE", "board_inline_update"))


def _attachment_upload_count(files) -> int:
    return len([f for f in (files or []) if getattr(f, "name", "")])


@login_required
@grade_required(*TASK_ALLOWED_GRADES)
def task_list(request: HttpRequest) -> HttpResponse:
    """
    ✅ 직원업무 목록
    - 검색/필터/페이지네이션 공용 서비스 사용
    """
    p = read_list_params(request)

    qs = Task.objects.annotate(comment_count=Count("comments", distinct=True)).order_by("-created_at")

    qs = apply_keyword_filter(
        qs, p.keyword, p.search_type,
        title_field="title",
        content_field="content",
        user_name_field="user_name",
    )
    qs = apply_common_list_filters(
        qs,
        date_from=p.date_from,
        date_to=p.date_to,
        selected_category=p.selected_category,
        selected_handler=p.selected_handler,
        selected_status=p.selected_status,
    )

    tasks, per_page = paginate(request, qs, default_per_page=10)
    query_string = build_query_string_without_page(request)

    return render(request, "board/task_list.html", {
        "tasks": tasks,
        "per_page": per_page,
        "per_page_choices": PER_PAGE_CHOICES,
        "query_string": query_string,
        "is_superuser": True,

        "handlers": get_handlers(),
        "keyword": p.keyword,
        "search_type": p.search_type,
        "selected_handler": p.selected_handler,
        "selected_status": p.selected_status,
        "status_choices": TASK_STATUS_VALUES,

        "category_choices": TASK_CATEGORY_VALUES,
        "selected_category": p.selected_category,
        "date_from": p.date_from_raw,
        "date_to": p.date_to_raw,
    })


@login_required
@grade_required(*TASK_ALLOWED_GRADES)
@require_POST
def ajax_update_task_field(request: HttpRequest) -> JsonResponse:
    """
    ✅ 목록 페이지 인라인 업데이트
    """
    task_id = request.POST.get("task_id")
    action = request.POST.get("action_type")
    value = (request.POST.get("value") or request.POST.get(action) or "").strip()

    if not task_id or action not in INLINE_ACTIONS:
        return JsonResponse({"ok": False, "message": "요청이 올바르지 않습니다."}, status=400)

    task = get_object_or_404(Task, id=task_id)
    response = inline_update_common(obj=task, action=action, value=value, allowed_status_values=TASK_STATUS_VALUES)
    _log_task_action(
        request,
        _inline_action_to_audit_name(action),
        task=task,
        success=response.status_code < 400,
        reason="" if response.status_code < 400 else (_json_message(response) or "inline_update_failed"),
        meta=_task_meta(
            task,
            extra={
                "source": "list",
                "action_type": action,
                "requested_value": value,
            },
        ),
    )
    return response


@login_required
@grade_required(*TASK_ALLOWED_GRADES)
@require_POST
def ajax_update_task_field_detail(request: HttpRequest, pk: int) -> JsonResponse:
    """
    ✅ 상세 페이지 인라인 업데이트
    """
    action = request.POST.get("action_type")
    value = (request.POST.get("value") or "").strip()

    if action not in INLINE_ACTIONS:
        return JsonResponse({"ok": False, "message": "요청이 올바르지 않습니다."}, status=400)

    task = get_object_or_404(Task, pk=pk)
    response = inline_update_common(obj=task, action=action, value=value, allowed_status_values=TASK_STATUS_VALUES)
    _log_task_action(
        request,
        _inline_action_to_audit_name(action),
        task=task,
        success=response.status_code < 400,
        reason="" if response.status_code < 400 else (_json_message(response) or "inline_update_failed"),
        meta=_task_meta(
            task,
            extra={
                "source": "detail",
                "action_type": action,
                "requested_value": value,
            },
        ),
    )
    return response


@login_required
@grade_required(*TASK_ALLOWED_GRADES)
def task_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """
    ✅ 직원업무 상세
    - 댓글 처리 공용 서비스 사용
    """
    task = get_object_or_404(Task, pk=pk)

    if request.method == "POST":
        handled = handle_comments_actions(
            request=request,
            obj=task,
            comment_model=TaskComment,
            fk_field="task",
            redirect_detail_name=TASK_DETAIL,
        )
        if handled:
            return handled

        act = (request.POST.get("action_type") or "").strip()
        if act == "delete_task":
            task_meta = _task_meta(task)
            task.delete()
            _log_task_action(
                request,
                _safe_action("BOARD_TASK_DELETE", "board_task_delete"),
                task=None,
                success=True,
                meta=task_meta,
            )
            messages.success(request, "게시글이 삭제되었습니다.")
            return redirect(TASK_LIST)

        return redirect(TASK_DETAIL, pk=pk)

    task_info = {
        "소속(요청자)": task.user_branch,
        "성명(요청자)": task.user_name,
        "사번(요청자)": task.user_id,
    }

    return render(request, "board/task_detail.html", {
        "task": task,
        "task_info": task_info,
        "is_superuser": True,
        "can_edit": True,

        "handlers": get_handlers(),
        "comments": task.comments.order_by("-created_at"),
        "attachments": task.attachments.all(),
        "form": TaskCommentForm(),

        "detail_url": reverse(TASK_DETAIL, kwargs={"pk": task.pk}),
        "list_url": reverse(TASK_LIST),
        "edit_url": reverse(TASK_EDIT, kwargs={"pk": task.pk}),
        "status_choices": TASK_STATUS_VALUES,
        "attachment_download_name": TASK_ATTACHMENT_DOWNLOAD,
    })


@login_required
@grade_required(*TASK_ALLOWED_GRADES)
def task_create(request: HttpRequest) -> HttpResponse:
    """
    ✅ 직원업무 작성
    - 첨부 저장 공용 서비스 사용
    """
    if request.method == "POST":
        form = TaskForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist("attachments")
            with transaction.atomic():
                task = form.save(commit=False)
                task.user_id = _user_storage_key(request.user)
                task.user_name = getattr(request.user, "name", "") or ""
                task.user_branch = getattr(request.user, "branch", "") or ""
                task.save()

                def _create(**kwargs):
                    return TaskAttachment.objects.create(task=task, **kwargs)

                save_attachments(files=files, create_func=_create)

            _log_task_action(
                request,
                _safe_action("BOARD_TASK_CREATE", "board_task_create"),
                task=task,
                success=True,
                meta=_task_meta(
                    task,
                    extra={
                        "attachment_count": _attachment_upload_count(files),
                    },
                ),
            )

            messages.success(request, "게시글이 등록되었습니다.")
            return redirect(TASK_DETAIL, pk=task.pk)
        
        _log_task_action(
            request,
            _safe_action("BOARD_TASK_CREATE", "board_task_create"),
            task=None,
            success=False,
            reason="form_invalid",
            meta={
                "user_id": _user_storage_key(request.user),
                "category": (request.POST.get("category") or "").strip(),
                "title_len": len((request.POST.get("title") or "").strip()),
                "content_len": len((request.POST.get("content") or "").strip()),
                "attachment_count": _attachment_upload_count(request.FILES.getlist("attachments")),
            },
        )
        messages.error(request, "입력값을 다시 확인해주세요.")
    else:
        form = TaskForm()

    return render(request, "board/task_create.html", {"form": form})


@login_required
@grade_required(*TASK_ALLOWED_GRADES)
def task_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """
    ✅ 직원업무 수정
    - 삭제 파일 처리 + 신규 첨부 추가
    """
    task = get_object_or_404(Task, pk=pk)

    if request.method == "POST":
        form = TaskForm(request.POST, request.FILES, instance=task)
        if form.is_valid():
            delete_ids = _safe_int_ids(request.POST.getlist("delete_files"))
            files = request.FILES.getlist("attachments")
            with transaction.atomic():
                # 편집 시에도 user_id 저장 규칙을 post와 동일하게 유지(혼재 방지)
                task = form.save(commit=False)
                user_key = (
                    getattr(request.user, "emp_id", None)
                    or getattr(request.user, "user_id", None)
                    or request.user.id
                )
                task.user_id = task.user_id or str(user_key)
                task.user_name = task.user_name or (getattr(request.user, "name", "") or "")
                task.user_branch = task.user_branch or (getattr(request.user, "branch", "") or "")
                task.save()

                if delete_ids:
                    TaskAttachment.objects.filter(id__in=delete_ids, task=task).delete()

                def _create(**kwargs):
                    return TaskAttachment.objects.create(task=task, **kwargs)

                save_attachments(files=files, create_func=_create)

            _log_task_action(
                request,
                _safe_action("BOARD_TASK_UPDATE", "board_task_update"),
                task=task,
                success=True,
                meta=_task_meta(
                    task,
                    extra={
                        "deleted_attachment_ids": delete_ids,
                        "new_attachment_count": _attachment_upload_count(files),
                    },
                ),
            )

            messages.success(request, "게시글이 수정되었습니다.")
            return redirect(TASK_DETAIL, pk=task.pk)
        
        _log_task_action(
            request,
            _safe_action("BOARD_TASK_UPDATE", "board_task_update"),
            task=task,
            success=False,
            reason="form_invalid",
            meta=_task_meta(
                task,
                extra={
                    "requested_category": (request.POST.get("category") or "").strip(),
                    "requested_title_len": len((request.POST.get("title") or "").strip()),
                    "requested_content_len": len((request.POST.get("content") or "").strip()),
                    "deleted_attachment_ids": _safe_int_ids(request.POST.getlist("delete_files")),
                    "new_attachment_count": _attachment_upload_count(request.FILES.getlist("attachments")),
                },
            ),
        )
        messages.error(request, "입력값을 확인해주세요.")
    else:
        form = TaskForm(instance=task)

    return render(request, "board/task_edit.html", {
        "form": form,
        "task": task,
        "attachments": task.attachments.all(),
        # ✅ edit 화면의 "기존 첨부 링크"를 다운로드 뷰로 통일하기 위한 URL name
        "attachment_download_name": TASK_ATTACHMENT_DOWNLOAD,
    })
