# django_ma/manual/utils/serializers.py

from __future__ import annotations

import os

from django.urls import reverse

from manual.models import ManualBlock, ManualBlockAttachment


def attachment_to_dict(a: ManualBlockAttachment) -> dict:
    download_url = reverse("manual:manual_attachment_download", args=[a.id])
    return {
        "id": a.id,
        "name": a.original_name or os.path.basename(a.file.name) if a.file else "",
        "url": download_url if a.file else "",
        "download_url": download_url if a.file else "",
        "size": a.size or 0,
    }


def block_to_dict(b: ManualBlock) -> dict:
    """
    ✅ 블록을 프런트가 즉시 DOM 업데이트 가능한 dict로 변환
    - 이미지 + 첨부파일 포함
    """
    image_url = reverse("manual:manual_block_image", args=[b.id]) if b.image else ""
    return {
        "id": b.id,
        "section_id": b.section_id,
        "title": b.title,
        "content": b.content,
        "image_url": image_url,
        "attachments": [
            attachment_to_dict(a)
            for a in b.attachments.all().order_by("created_at", "id")
        ],
    }
