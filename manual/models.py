# django_ma/manual/models.py

from __future__ import annotations

import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .constants import (
    BLOCK_TITLE_MAX_LEN,
    MANUAL_TITLE_MAX_LEN,
    MAX_ATTACHMENT_SIZE,
    SECTION_TITLE_MAX_LEN,
)


# =============================================================================
# Manual
# =============================================================================

class Manual(models.Model):
    """
    ✅ 매뉴얼(문서)

    접근 규칙(views/utils.permissions에서 사용):
    - admin_only=True    : superuser/head만 접근
    - is_published=False : superuser만 접근 (직원전용/비공개 개념)
    """

    title = models.CharField(max_length=MANUAL_TITLE_MAX_LEN)
    content = models.TextField(blank=True)

    # 접근 제어 플래그
    admin_only = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)

    # 목록 정렬 우선순위 (작을수록 위)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="manuals",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "-updated_at"]
        indexes = [
            models.Index(fields=["sort_order"]),
            models.Index(fields=["-updated_at"]),
        ]

    def __str__(self) -> str:
        return self.title


# =============================================================================
# Section
# =============================================================================

class ManualSection(models.Model):
    """
    ✅ 매뉴얼 안의 '섹션 카드'
    - manual     : 소속 매뉴얼
    - title      : 섹션 제목(옵션)
    - sort_order : 섹션 정렬
    """

    manual = models.ForeignKey(Manual, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(max_length=SECTION_TITLE_MAX_LEN, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["manual", "sort_order"]),
        ]

    def __str__(self) -> str:
        return f"[manual#{self.manual_id}] section#{self.id}"


# =============================================================================
# Block
# =============================================================================

class ManualBlock(models.Model):
    """
    ✅ 섹션 안의 '블록 카드'

    - section : 소속 섹션 (nullable 유지: 기존 호환)
    - manual  : section.manual로 추론 가능하지만 기존 호환을 위해 유지(추후 정리 권장)
    - content : Quill HTML
    - image   : 좌측 이미지 (선택)
    - attachments : 첨부파일 N개
    """

    manual = models.ForeignKey(Manual, on_delete=models.CASCADE, related_name="blocks")

    section = models.ForeignKey(
        ManualSection,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="blocks",
    )

    title = models.CharField(max_length=BLOCK_TITLE_MAX_LEN, blank=True, default="")
    content = models.TextField(blank=True)

    image = models.ImageField(upload_to="manual/blocks/", blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["manual", "sort_order"]),
            models.Index(fields=["section", "sort_order"]),
        ]

    def __str__(self) -> str:
        return f"block#{self.id} (section={self.section_id})"

    def delete(self, using=None, keep_parents=False):
        """
        ✅ 블록 삭제 시 이미지 파일도 함께 삭제
        - attachments는 cascade + attachment.delete()에서 파일 삭제됨
        """
        if self.image:
            self.image.delete(save=False)
        return super().delete(using=using, keep_parents=keep_parents)
    
    def save(self, *args, **kwargs):
        from manual.utils.sanitize import sanitize_quill_html
        self.content = sanitize_quill_html(self.content)
        super().save(*args, **kwargs)


# =============================================================================
# Block Attachments
# =============================================================================

def validate_attachment_size(f):
    """✅ 첨부파일 용량 제한(기본 20MB)"""
    if f and hasattr(f, "size") and f.size > MAX_ATTACHMENT_SIZE:
        raise ValidationError(f"첨부파일은 최대 {MAX_ATTACHMENT_SIZE // (1024 * 1024)}MB까지 업로드 가능합니다.")


class ManualBlockAttachment(models.Model):
    """
    ✅ 블록 첨부파일 (N개 가능)
    - Quill 본문에는 링크로 삽입하여 사용
    """

    block = models.ForeignKey(
        ManualBlock,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    file = models.FileField(
        upload_to="manual/attachments/",
        validators=[validate_attachment_size],
    )

    # 사용자가 업로드한 원본 파일명 보존용
    original_name = models.CharField(max_length=255, blank=True, default="")
    size = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["block", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"attachment#{self.id} block={self.block_id}"

    def save(self, *args, **kwargs):
        """
        ✅ 저장 시 size/original_name 자동 채움
        - view에서 안 채워도 DB 일관성 유지
        """
        if self.file:
            self.size = getattr(self.file, "size", 0) or 0
            if not self.original_name:
                # InMemoryUploadedFile.name 또는 storage name이 섞일 수 있어 basename 처리
                self.original_name = os.path.basename(getattr(self.file, "name", "") or "")
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        """✅ 첨부 삭제 시 파일도 함께 삭제"""
        if self.file:
            self.file.delete(save=False)
        return super().delete(using=using, keep_parents=keep_parents)
