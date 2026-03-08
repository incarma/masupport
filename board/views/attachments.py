# django_ma/board/views/attachments.py
# =========================================================
# Attachment Download Views
# - 원천차단 핵심: att.file.url 직접 링크 금지
# - 다운로드 뷰에서 권한 검증 후 FileResponse
# =========================================================

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect

from accounts.decorators import grade_required

from audit.services import log_action
from audit.constants import ACTION

from ..constants import (
    BOARD_ALLOWED_GRADES, TASK_ALLOWED_GRADES,
    POST_LIST,
)
from ..models import Attachment, TaskAttachment
from ..policies import can_download_post_attachment, can_download_task_attachment
from ..services.attachments import open_fileresponse_from_fieldfile


__all__ = [
    "post_attachment_download",
    "task_attachment_download",
]


def _safe_action(name: str, default: str) -> str:
    """
    ACTION 상수가 아직 정의되지 않은 경우에도 board 동작이 깨지지 않도록 방어한다.
    """
    return getattr(ACTION, name, default)


def _attachment_meta(att, *, kind: str) -> dict:
    file_obj = getattr(att, "file", None)
    return {
        "kind": kind,
        "post_id": getattr(att, "post_id", None),
        "task_id": getattr(att, "task_id", None),
        "att_id": getattr(att, "id", None),
        "filename": (getattr(att, "original_name", "") or ""),
        "size": getattr(file_obj, "size", None),
        "stored_name": getattr(file_obj, "name", None),
    }


def _log_attachment_download(request: HttpRequest, att, *, kind: str, success: bool, reason: str = "") -> None:
    try:
        log_action(
            request,
            _safe_action("BOARD_ATTACHMENT_DOWNLOAD", "board_attachment_download"),
            obj=att,
            meta=_attachment_meta(att, kind=kind),
            success=success,
            reason=reason or "",
        )
    except Exception:
        # 로그 실패가 사용자 동작을 막으면 안 됨
        pass


def _open_download_or_404(att) -> FileResponse:
    file_obj = getattr(att, "file", None)
    file_name = getattr(file_obj, "name", "") if file_obj else ""
    if not file_obj or not file_name:
        raise Http404("첨부파일을 찾을 수 없습니다.")

    try:
        return open_fileresponse_from_fieldfile(file_obj, original_name=att.original_name or "")
    except FileNotFoundError as exc:
        raise Http404("첨부파일을 찾을 수 없습니다.") from exc


@login_required
@grade_required(*BOARD_ALLOWED_GRADES)
def post_attachment_download(request: HttpRequest, att_id: int) -> HttpResponse:
    """
    ✅ Post 첨부파일 다운로드
    - 권한: 게시글 조회 권한과 동일 (can_view_post)
    - 템플릿에서 att.file.url 대신 이 URL을 사용해야 원천차단 완성
    """
    att = get_object_or_404(Attachment, id=att_id)
    post = att.post
    if not can_download_post_attachment(request.user, att):
        _log_attachment_download(
            request,
            att,
            kind="post",
            success=False,
            reason="permission_denied",
        )
        messages.error(request, "첨부파일 다운로드 권한이 없습니다.")
        return redirect(POST_LIST)
    
    try:
        response = _open_download_or_404(att)
    except Http404:
        _log_attachment_download(
            request,
            att,
            kind="post",
            success=False,
            reason="file_not_found",
        )
        messages.error(request, "첨부파일을 찾을 수 없습니다.")
        return redirect(POST_LIST)

    _log_attachment_download(
        request,
        att,
        kind="post",
        success=True,
    )
    return response


@login_required
@grade_required(*TASK_ALLOWED_GRADES)
def task_attachment_download(request: HttpRequest, att_id: int) -> HttpResponse:
    """
    ✅ Task 첨부파일 다운로드 (task는 superuser only)
    - 동일 패턴으로 원천차단 적용
    """
    att = get_object_or_404(TaskAttachment, id=att_id)

    if not can_download_task_attachment(request.user, att):
        _log_attachment_download(
            request,
            att,
            kind="task",
            success=False,
            reason="permission_denied",
        )
        messages.error(request, "첨부파일 다운로드 권한이 없습니다.")
        return redirect("home")

    try:
        response = _open_download_or_404(att)
    except Http404:
        _log_attachment_download(
            request,
            att,
            kind="task",
            success=False,
            reason="file_not_found",
        )
        messages.error(request, "첨부파일을 찾을 수 없습니다.")
        return redirect("home")

    _log_attachment_download(
        request,
        att,
        kind="task",
        success=True,
    )
    return response