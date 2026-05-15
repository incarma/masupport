# django_ma/manual/views/attachment.py

from __future__ import annotations

import logging
import os

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_cache_control
from django.views.decorators.http import require_POST

from audit.constants import ACTION
from audit.services import log_action

from ..models import ManualBlock, ManualBlockAttachment
from ..utils import fail, is_digits, json_body, ok, to_str, ensure_superuser_or_403, attachment_to_dict, open_manual_fileresponse
from ..utils.permissions import manual_accessible_or_denied
from ..utils.uploads import validate_manual_attachment


logger = logging.getLogger(__name__)


@require_POST
@login_required
def manual_block_attachment_upload_ajax(request):
    """superuser 전용: 블록 첨부 업로드 (multipart)"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    block_id = request.POST.get("block_id")
    upfile = request.FILES.get("file")

    if not is_digits(block_id):
        return fail("block_id가 올바르지 않습니다.", 400)
    if not upfile:
        return fail("업로드할 파일이 없습니다.", 400)
    
    err = validate_manual_attachment(upfile)
    if err:
        return fail(err, 400)

    b = get_object_or_404(
        ManualBlock.objects.select_related("section__manual", "manual"),
        pk=int(block_id),
    )

    a = ManualBlockAttachment.objects.create(
        block=b,
        file=upfile,
        original_name=to_str(getattr(upfile, "name", "")),
        size=int(getattr(upfile, "size", 0) or 0),
    )

    log_action(
        request,
        ACTION.MANUAL_ATTACHMENT_UPLOAD,
        obj=a,
        meta={"block_id": b.id, "manual_id": b.manual_id, "name": a.original_name, "size": a.size},
    )

    # ✅ SSOT 직렬화(utils.serializers) 사용
    return ok({"attachment": attachment_to_dict(a)})


@require_POST
@login_required
def manual_block_attachment_delete_ajax(request):
    """superuser 전용: 첨부 삭제 (JSON)"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    attachment_id = payload.get("attachment_id")

    if not is_digits(attachment_id):
        return fail("attachment_id가 올바르지 않습니다.", 400)

    a = get_object_or_404(
        ManualBlockAttachment.objects.select_related("block__section__manual", "block__manual"),
        pk=int(attachment_id),
    )
    manual = a.block.section.manual if a.block.section_id else a.block.manual

    log_action(
        request,
        ACTION.MANUAL_ATTACHMENT_DELETE,
        obj=a,
        meta={"block_id": a.block_id, "manual_id": manual.id, "name": a.original_name, "size": a.size},
    )
    a.delete()
    return ok()


@login_required
def manual_attachment_download(request, attachment_id: int):
    """권한 검증 후 첨부파일을 FileResponse로 제공한다."""
    a = get_object_or_404(
        ManualBlockAttachment.objects.select_related("block__section__manual", "block__manual"),
        pk=attachment_id,
    )

    manual = a.block.section.manual if a.block.section_id else a.block.manual
    denied = manual_accessible_or_denied(request, manual)
    if denied:
        return denied

    if not a.file:
        raise Http404("파일이 없습니다.")

    filename = a.original_name or os.path.basename(a.file.name)

    try:
        # ✅ 기능 변화 0:
        # - 권한 검증 후 FileResponse 제공
        # - RFC5987 한글 파일명 헤더 유지
        # - 파일 직접 URL 노출 없음
        response = open_manual_fileresponse(
            a.file,
            filename=filename,
            as_attachment=True,
        )

        log_action(
            request,
            ACTION.MANUAL_ATTACHMENT_DOWNLOAD,
            obj=a,
            meta={"block_id": a.block_id, "manual_id": manual.id, "name": filename, "size": a.size},
        )
        return response
    except Http404:
        logger.exception("Manual attachment file missing. attachment_id=%s", attachment_id)
        raise Http404("파일을 찾을 수 없습니다.")


@login_required
def manual_block_image(request, block_id: int):
    """권한 검증 후 블록 이미지를 inline FileResponse로 제공한다."""
    b = get_object_or_404(
        ManualBlock.objects.select_related("section__manual", "manual"),
        pk=block_id,
    )

    manual = b.section.manual if b.section_id else b.manual
    denied = manual_accessible_or_denied(request, manual)
    if denied:
        return denied

    if not b.image:
        raise Http404("이미지가 없습니다.")

    try:
        # ✅ 기능 변화 0:
        # - 기존처럼 inline 이미지 응답
        # - private cache-control 유지
        return open_manual_fileresponse(
            b.image,
            as_attachment=False,
            cache_private_seconds=3600,
        )
    except Http404:
        logger.exception("Manual block image missing. block_id=%s", block_id)
        raise Http404("이미지를 찾을 수 없습니다.")