# django_ma/manual/services/attachments.py

from __future__ import annotations

from django.shortcuts import get_object_or_404

from manual.models import ManualBlock, ManualBlockAttachment


def get_block_for_attachment_upload(block_id: int) -> ManualBlock:
    return get_object_or_404(
        ManualBlock.objects.select_related("section__manual", "manual"),
        pk=block_id,
    )


def create_attachment(
    block: ManualBlock,
    *,
    file,
    original_name: str,
    size: int,
) -> ManualBlockAttachment:
    return ManualBlockAttachment.objects.create(
        block=block,
        file=file,
        original_name=original_name,
        size=size,
    )


def get_attachment_or_404(attachment_id: int) -> ManualBlockAttachment:
    """삭제/다운로드 공용 — block → section → manual 관계를 select_related로 로드한다."""
    return get_object_or_404(
        ManualBlockAttachment.objects.select_related("block__section__manual", "block__manual"),
        pk=attachment_id,
    )
