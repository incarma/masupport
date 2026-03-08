# django_ma/board/views/posts.py
# =========================================================
# Post Views (업무요청) - superuser/head/leader
# - 목록/상세/작성/수정
# - 인라인 업데이트(담당자/상태) - superuser only
# =========================================================

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from accounts.models import CustomUser

from audit.constants import ACTION
from audit.services import log_action

from ..constants import (
    BOARD_ALLOWED_GRADES,
    INLINE_ACTIONS,
    PER_PAGE_CHOICES,
    POST_ATTACHMENT_DOWNLOAD,
    POST_CATEGORY_VALUES,
    POST_DETAIL,
    POST_EDIT,
    POST_LIST,
    STATUS_CHOICES,
)
from ..forms import CommentForm, PostForm
from ..models import Attachment, Comment, Post
from ..policies import can_edit_post, can_view_post
from ..services.attachments import save_attachments
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


__all__ = [
    # pages
    "post_list",
    "post_create",
    "post_detail",
    "post_edit",
    # ajax
    "ajax_update_post_field",
    "ajax_update_post_field_detail",
]


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


def _post_meta(post, *, extra: dict | None = None) -> dict:
    meta = {
        "post_id": getattr(post, "pk", None),
        "category": getattr(post, "category", "") or "",
        "status": getattr(post, "status", "") or "",
        "handler": getattr(post, "handler", "") or "",
        "user_id": getattr(post, "user_id", "") or "",
        "user_branch": getattr(post, "user_branch", "") or "",
    }
    if extra:
        meta.update(extra)
    return meta


def _log_post_action(request: HttpRequest, action_name: str, *, post=None, success: bool, reason: str = "", meta: dict | None = None) -> None:
    try:
        log_action(
            request,
            action_name,
            obj=post,
            object_type="board_post",
            object_id=str(getattr(post, "pk", "") or ""),
            meta=meta or _post_meta(post, extra={}) if post is not None else (meta or {}),
            success=success,
            reason=reason or "",
        )
    except Exception:
        logger.exception("post audit logging failed")


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
@grade_required(*BOARD_ALLOWED_GRADES)
def post_list(request: HttpRequest) -> HttpResponse:
    """
    ✅ 업무요청 목록
    - visibility 정책: superuser/all, head(본인+지점), leader(본인)
    - ✅ list 화면의 [부문] 컬럼을 위해 post.user_channel(요청자 부문) annotate 추가
      (Post.user_id가 FK가 아닐 수도 있으므로 Subquery로 안전 조회)
    """
    grade = (getattr(request.user, "grade", "") or "").strip()
    is_superuser = (grade == "superuser")

    p = read_list_params(request)

    # ---------------------------------------------------------
    # ✅ annotate: comment_count + user_channel(CustomUser.channel)
    # - Post.user_id(사번/아이디) -> CustomUser.id 매칭
    # - user_id 저장 규칙이 PK(id) 또는 emp_id(사번)로 바뀌어도 안전하게 매칭
    # ---------------------------------------------------------
    # emp_id 필드 존재 여부에 따라 OR 매칭 적용(필드 없으면 기존 로직 유지)
    try:
        CustomUser._meta.get_field("emp_id")
        _has_emp_id = True
    except Exception:
        _has_emp_id = False

    if _has_emp_id:
        user_channel_sq = Subquery(
            CustomUser.objects
            .filter(Q(id=OuterRef("user_id")) | Q(emp_id=OuterRef("user_id")))
            .values("channel")[:1]
        )
    else:
        user_channel_sq = Subquery(
            CustomUser.objects.filter(id=OuterRef("user_id")).values("channel")[:1]
        )

    qs = (
        Post.objects.annotate(
            comment_count=Count("comments", distinct=True),
            user_channel=Coalesce(user_channel_sq, Value("")),
        )
        .order_by("-created_at")
    )

    # ---------------------------------------------------------
    # ✅ 검색 (기존 로직 유지)
    # - user_name_field는 Post에 저장된 snapshot(user_name) 기준
    # ---------------------------------------------------------
    qs = apply_keyword_filter(
        qs,
        p.keyword,
        p.search_type,
        title_field="title",
        content_field="content",
        user_name_field="user_name",
    )

    # ---------------------------------------------------------
    # ✅ 공용 필터 (기존 로직 유지)
    # ---------------------------------------------------------
    qs = apply_common_list_filters(
        qs,
        date_from=p.date_from,
        date_to=p.date_to,
        selected_category=p.selected_category,
        selected_handler=p.selected_handler,
        selected_status=p.selected_status,
    )

    # ---------------------------------------------------------
    # ✅ Visibility policy (기존 로직 유지)
    # ---------------------------------------------------------
    if not is_superuser:
        # ✅ 통일 키: emp_id(사번) 우선 → user_id → id
        user_key = getattr(request.user, "emp_id", None) or getattr(request.user, "user_id", None) or request.user.id
        my_id = str(user_key or "")

        # 혼재 데이터(예: 기존 글은 PK, 신규 글은 emp_id)까지 최대한 커버
        legacy_pk = str(getattr(request.user, "id", "") or "")

        if grade == "head":
            my_branch = (getattr(request.user, "branch", "") or "").strip()
            # 내 글(통일키) + (가능하면 레거시 PK로 작성된 내 글) + 지점 글
            mine_q = Q(user_id=my_id)
            if legacy_pk and legacy_pk != my_id:
                mine_q = mine_q | Q(user_id=legacy_pk)
            qs = qs.filter(mine_q | Q(user_branch__iexact=my_branch))

        else:
            mine_q = Q(user_id=my_id)
            if legacy_pk and legacy_pk != my_id:
                mine_q = mine_q | Q(user_id=legacy_pk)
            qs = qs.filter(mine_q)  

    posts, per_page = paginate(request, qs, default_per_page=10)
    query_string = build_query_string_without_page(request)

    return render(request, "board/post_list.html", {
        "posts": posts,
        "per_page": per_page,
        "per_page_choices": PER_PAGE_CHOICES,
        "query_string": query_string,

        "is_superuser": is_superuser,
        "handlers": get_handlers(),
        "status_choices": STATUS_CHOICES,

        "keyword": p.keyword,
        "search_type": p.search_type,
        "selected_handler": p.selected_handler,
        "selected_status": p.selected_status,

        "category_choices": POST_CATEGORY_VALUES,
        "selected_category": p.selected_category,

        "date_from": p.date_from_raw,
        "date_to": p.date_to_raw,
    })


@login_required
@grade_required(*BOARD_ALLOWED_GRADES)
@require_POST
def ajax_update_post_field(request: HttpRequest) -> JsonResponse:
    """
    ✅ 목록 인라인 변경: superuser만 허용(기존 정책 유지)
    """
    if getattr(request.user, "grade", "") != "superuser":
        return JsonResponse({"ok": False, "message": "권한이 없습니다."}, status=403)

    post_id = request.POST.get("post_id")
    action = request.POST.get("action_type")
    value = (request.POST.get("value") or request.POST.get(action) or "").strip()

    if not post_id or action not in INLINE_ACTIONS:
        return JsonResponse({"ok": False, "message": "요청이 올바르지 않습니다."}, status=400)

    post = get_object_or_404(Post, id=post_id)
    response = inline_update_common(obj=post, action=action, value=value, allowed_status_values=STATUS_CHOICES)
    _log_post_action(
        request,
        _inline_action_to_audit_name(action),
        post=post,
        success=response.status_code < 400,
        reason="" if response.status_code < 400 else (_json_message(response) or "inline_update_failed"),
        meta=_post_meta(
            post,
            extra={
                "source": "list",
                "action_type": action,
                "requested_value": value,
            },
        ),
    )
    return response


@login_required
@grade_required(*BOARD_ALLOWED_GRADES)
@require_POST
def ajax_update_post_field_detail(request: HttpRequest, pk: int) -> JsonResponse:
    """
    ✅ 상세 인라인 변경: superuser only
    """
    if getattr(request.user, "grade", "") != "superuser":
        return JsonResponse({"ok": False, "message": "권한이 없습니다."}, status=403)

    action = request.POST.get("action_type")
    value = (request.POST.get("value") or "").strip()

    if action not in INLINE_ACTIONS:
        return JsonResponse({"ok": False, "message": "요청이 올바르지 않습니다."}, status=400)

    post = get_object_or_404(Post, pk=pk)
    response = inline_update_common(obj=post, action=action, value=value, allowed_status_values=STATUS_CHOICES)
    _log_post_action(
        request,
        _inline_action_to_audit_name(action),
        post=post,
        success=response.status_code < 400,
        reason="" if response.status_code < 400 else (_json_message(response) or "inline_update_failed"),
        meta=_post_meta(
            post,
            extra={
                "source": "detail",
                "action_type": action,
                "requested_value": value,
            },
        ),
    )
    return response


@login_required
@grade_required(*BOARD_ALLOWED_GRADES)
def post_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """
    ✅ 업무요청 상세
    - URL 직접 접근 방어(can_view_post)
    - 수정/삭제: 작성자+superuser(can_edit_post)
    """
    post = get_object_or_404(Post, pk=pk)

    if not can_view_post(request.user, post):
        messages.error(request, "해당 게시글을 조회할 권한이 없습니다.")
        return redirect(POST_LIST)

    is_superuser = (getattr(request.user, "grade", "") == "superuser")
    can_edit = can_edit_post(request.user, post)

    if request.method == "POST":
        handled = handle_comments_actions(
            request=request,
            obj=post,
            comment_model=Comment,
            fk_field="post",
            redirect_detail_name=POST_DETAIL,
        )
        if handled:
            return handled

        act = (request.POST.get("action_type") or "").strip()
        if act == "delete_post":
            if not can_edit:
                _log_post_action(
                    request,
                    _safe_action("BOARD_POST_DELETE", "board_post_delete"),
                    post=post,
                    success=False,
                    reason="permission_denied",
                )
                messages.error(request, "삭제 권한이 없습니다.")
                return redirect(POST_DETAIL, pk=pk)
            post_meta = _post_meta(post)
            post.delete()
            _log_post_action(
                request,
                _safe_action("BOARD_POST_DELETE", "board_post_delete"),
                post=None,
                success=True,
                meta=post_meta,
            )
            messages.success(request, "게시글이 삭제되었습니다.")
            return redirect(POST_LIST)

        return redirect(POST_DETAIL, pk=pk)

    post_info = {
        "소속(요청자)": post.user_branch,
        "성명(요청자)": post.user_name,
        "사번(요청자)": post.user_id,
    }

    return render(request, "board/post_detail.html", {
        "post": post,
        "post_info": post_info,
        "is_superuser": is_superuser,
        "can_edit": can_edit,

        "handlers": get_handlers(),
        "status_choices": STATUS_CHOICES,

        "comments": post.comments.order_by("-created_at"),
        "attachments": post.attachments.all(),
        "form": CommentForm(),

        "detail_url": reverse(POST_DETAIL, kwargs={"pk": post.pk}),
        "list_url": reverse(POST_LIST),
        "edit_url": reverse(POST_EDIT, kwargs={"pk": post.pk}),

        # ✅ 템플릿에서 url name으로 안전 다운로드 링크 생성 가능
        "attachment_download_name": POST_ATTACHMENT_DOWNLOAD,
    })


@login_required
@grade_required(*BOARD_ALLOWED_GRADES)
def post_create(request: HttpRequest) -> HttpResponse:
    """
    ✅ 업무요청 작성
    - 첨부 저장 공용 서비스 사용
    """
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist("attachments")
            with transaction.atomic():
                post = form.save(commit=False)
                post.user_id = _user_storage_key(request.user)
                post.user_name = getattr(request.user, "name", "") or ""
                post.user_branch = getattr(request.user, "branch", "") or ""
                post.save()

                def _create(**kwargs):
                    return Attachment.objects.create(post=post, **kwargs)

                save_attachments(files=files, create_func=_create)

            _log_post_action(
                request,
                _safe_action("BOARD_POST_CREATE", "board_post_create"),
                post=post,
                success=True,
                meta=_post_meta(
                    post,
                    extra={
                        "attachment_count": _attachment_upload_count(files),
                    },
                ),
            )

            messages.success(request, "게시글이 등록되었습니다.")
            return redirect(POST_DETAIL, pk=post.pk)
        
        _log_post_action(
            request,
            _safe_action("BOARD_POST_CREATE", "board_post_create"),
            post=None,
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
        form = PostForm()

    return render(request, "board/post_create.html", {"form": form})


@login_required
@grade_required(*BOARD_ALLOWED_GRADES)
def post_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """
    ✅ 업무요청 수정
    - 수정 권한: 작성자 or superuser
    - 기존 첨부 삭제 + 신규 첨부 추가
    """
    post = get_object_or_404(Post, pk=pk)

    if not can_edit_post(request.user, post):
        messages.error(request, "수정 권한이 없습니다.")
        return redirect(POST_DETAIL, pk=pk)

    if request.method == "POST":
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            delete_ids = _safe_int_ids(request.POST.getlist("delete_files"))
            files = request.FILES.getlist("attachments")
            with transaction.atomic():
                form.save()

                if delete_ids:
                    Attachment.objects.filter(id__in=delete_ids, post=post).delete()

                def _create(**kwargs):
                    return Attachment.objects.create(post=post, **kwargs)

                save_attachments(files=files, create_func=_create)

            _log_post_action(
                request,
                _safe_action("BOARD_POST_UPDATE", "board_post_update"),
                post=post,
                success=True,
                meta=_post_meta(
                    post,
                    extra={
                        "deleted_attachment_ids": delete_ids,
                        "new_attachment_count": _attachment_upload_count(files),
                    },
                ),
            )

            messages.success(request, "게시글이 수정되었습니다.")
            return redirect(POST_DETAIL, pk=post.pk)
        
        _log_post_action(
            request,
            _safe_action("BOARD_POST_UPDATE", "board_post_update"),
            post=post,
            success=False,
            reason="form_invalid",
            meta=_post_meta(
                post,
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
        form = PostForm(instance=post)

    return render(request, "board/post_edit.html", {
        "form": form,
        "post": post,
        "attachments": post.attachments.all(),
        # ✅ edit 화면의 "기존 첨부 링크"를 다운로드 뷰로 통일하기 위한 URL name
        "attachment_download_name": POST_ATTACHMENT_DOWNLOAD,
    })
