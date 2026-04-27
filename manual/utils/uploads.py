# django_ma/manual/utils/uploads.py

from __future__ import annotations

import os

from django.core.files.uploadedfile import UploadedFile

from manual.constants import (
    MANUAL_ALLOWED_ATTACHMENT_EXTENSIONS,
    MANUAL_ALLOWED_ATTACHMENT_MIME_TYPES,
    MANUAL_ALLOWED_IMAGE_EXTENSIONS,
    MANUAL_ALLOWED_IMAGE_MIME_TYPES,
    MAX_ATTACHMENT_SIZE,
)


def _ext(filename: str) -> str:
    """업로드 파일명에서 소문자 확장자를 추출한다."""
    return os.path.splitext(filename or "")[1].lower()


def _content_type(upfile: UploadedFile) -> str:
    """브라우저/클라이언트가 전달한 MIME 값을 안전하게 정규화한다."""
    return str(getattr(upfile, "content_type", "") or "").lower().strip()


def validate_manual_attachment(upfile: UploadedFile) -> str:
    """
    manual 첨부파일 서버단 검증.

    반환값:
    - ""      : 통과
    - message : 사용자에게 보여줄 오류 메시지
    """
    if not upfile:
        return "업로드할 파일이 없습니다."

    if getattr(upfile, "size", 0) and upfile.size > MAX_ATTACHMENT_SIZE:
        mb = MAX_ATTACHMENT_SIZE // (1024 * 1024)
        return f"파일 용량은 최대 {mb}MB까지 가능합니다."

    ext = _ext(getattr(upfile, "name", ""))
    if ext not in MANUAL_ALLOWED_ATTACHMENT_EXTENSIONS:
        return "허용되지 않는 파일 확장자입니다."

    content_type = _content_type(upfile)
    if content_type and content_type not in MANUAL_ALLOWED_ATTACHMENT_MIME_TYPES:
        return "허용되지 않는 파일 형식입니다."

    return ""


def validate_manual_image(upfile: UploadedFile) -> str:
    """
    manual 블록 이미지 서버단 검증.

    기존 ImageField 저장 구조는 유지하되,
    확장자와 MIME을 별도로 검증하여 비이미지 파일 업로드를 차단한다.
    """
    if not upfile:
        return ""

    if getattr(upfile, "size", 0) and upfile.size > MAX_ATTACHMENT_SIZE:
        mb = MAX_ATTACHMENT_SIZE // (1024 * 1024)
        return f"이미지 용량은 최대 {mb}MB까지 가능합니다."

    ext = _ext(getattr(upfile, "name", ""))
    if ext not in MANUAL_ALLOWED_IMAGE_EXTENSIONS:
        return "허용되지 않는 이미지 확장자입니다."

    content_type = _content_type(upfile)
    if content_type and content_type not in MANUAL_ALLOWED_IMAGE_MIME_TYPES:
        return "허용되지 않는 이미지 형식입니다."

    return ""