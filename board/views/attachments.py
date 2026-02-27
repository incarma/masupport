# django_ma/board/views/attachments.py
# =========================================================
# Attachment Download Views
# - 원천차단 핵심: att.file.url 직접 링크 금지
# - 다운로드 뷰에서 권한 검증 후 FileResponse
# =========================================================

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect

from accounts.decorators import grade_required

from audit.services import log_action
from audit.constants import ACTION

from ..constants import (
    BOARD_ALLOWED_GRADES, TASK_ALLOWED_GRADES,
    POST_LIST,
)
from ..models import Attachment, TaskAttachment
from ..policies import can_view_post
from ..services.attachments import open_fileresponse_from_fieldfile


__all__ = [
    "post_attachment_download",
    "task_attachment_download",
]


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

    if not can_view_post(request.user, post):
        messages.error(request, "첨부파일 다운로드 권한이 없습니다.")
        return redirect(POST_LIST)
    
    # ✅ AuditLog: 다운로드(원천차단 핵심 이벤트)
    # - RequestLog는 자동 수집되므로, AuditLog에는 "누가/무엇을" 중심으로 남긴다.
    try:
        log_action(
            request,
            ACTION.BOARD_ATTACHMENT_DOWNLOAD,
            obj=att,
            meta={
                "kind": "post",
                "post_id": getattr(att, "post_id", None),
                "att_id": getattr(att, "id", None),
                "filename": (att.original_name or ""),
                "size": getattr(getattr(att, "file", None), "size", None),
            },
            success=True,
        )
    except Exception:
        # 로그 실패가 다운로드를 막으면 안 됨
        pass

    return open_fileresponse_from_fieldfile(att.file, original_name=att.original_name or "")


@login_required
@grade_required(*TASK_ALLOWED_GRADES)
def task_attachment_download(request: HttpRequest, att_id: int) -> HttpResponse:
    """
    ✅ Task 첨부파일 다운로드 (task는 superuser only)
    - 동일 패턴으로 원천차단 적용
    """
    att = get_object_or_404(TaskAttachment, id=att_id)

    # ✅ AuditLog: Task 첨부 다운로드
    try:
        log_action(
            request,
            ACTION.BOARD_ATTACHMENT_DOWNLOAD,
            obj=att,
            meta={
                "kind": "task",
                "task_id": getattr(att, "task_id", None),
                "att_id": getattr(att, "id", None),
                "filename": (att.original_name or ""),
                "size": getattr(getattr(att, "file", None), "size", None),
            },
            success=True,
        )
    except Exception:
        pass

    return open_fileresponse_from_fieldfile(att.file, original_name=att.original_name or "")