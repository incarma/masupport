# django_ma/board/services/attachments.py
# =========================================================
# Attachment Services (FINAL)
# - 첨부 저장(create_func로 모델 분기)
# - 다운로드: FileSystemStorage(.path) 기반 안전 처리
# - 파일 핸들 close 보장(File wrapper)
# - 다운로드 파일명 브라우저 호환(Content-Disposition RFC 5987)
# - 파일명 정규화(Win 금지문자/예약어/끝 공백·점/길이 제한/확장자 보존)
# =========================================================

from __future__ import annotations

import logging
import os
import mimetypes
import re
from typing import Any, Callable, Iterable

from django.conf import settings
from django.core.files import File
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.utils.http import content_disposition_header

logger = logging.getLogger("board.access")

DEFAULT_MAX_UPLOAD_SIZE = 10 * 1024 * 1024


# -----------------------------
# Filename normalization (Win-safe)
# -----------------------------
_WIN_FORBIDDEN_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
_WIN_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _normalize_download_filename(name: str, *, fallback: str = "download", max_len: int = 120) -> str:
    """
    ✅ 다운로드 파일명 정규화(Windows 호환 중심)
    - 금지문자 제거: <>:"/\\|?* + 제어문자(0x00-0x1F)
    - 끝 공백/점 제거(Windows에서 문제)
    - 예약어(CON, PRN, AUX, NUL, COM1.., LPT1..) 방어
    - 너무 긴 경우: 확장자 보존하며 max_len으로 자르기
    """
    raw = (name or "").strip()
    if not raw:
        raw = fallback

    # 금지문자 -> "_" 치환
    raw = _WIN_FORBIDDEN_CHARS_RE.sub("_", raw)

    # 연속 공백 정리
    raw = re.sub(r"\s+", " ", raw).strip()

    # 끝의 공백/점 제거(Windows)
    raw = raw.rstrip(" .")
    if not raw:
        raw = fallback

    stem, ext = os.path.splitext(raw)
    stem_clean = (stem or "").strip().rstrip(" .")
    if not stem_clean:
        stem_clean = fallback

    # 예약어 방어(확장자 제외 stem 기준)
    if stem_clean.upper() in _WIN_RESERVED_NAMES:
        stem_clean = f"_{stem_clean}"

    ext_clean = (ext or "").strip()

    # 길이 제한: 확장자 보존
    base = stem_clean
    if max_len and len(base + ext_clean) > max_len:
        keep = max_len - len(ext_clean)
        if keep < 1:
            # ext가 너무 길면 ext도 잘라서 최소 1글자 확보
            ext_clean = ext_clean[: max(0, max_len - 1)]
            keep = max_len - len(ext_clean)
        base = base[:keep]

    out = (base + ext_clean).strip().rstrip(" .")
    return out or fallback


def _build_download_filename(*, original_name: str, file_path: str) -> str:
    """
    1) original_name 우선
    2) 없으면 file_path basename 사용
    3) 확장자 없으면 file_path 확장자 참고(가능하면 붙임)
    4) 정규화 적용 후 반환
    """
    raw = (original_name or "").strip()
    raw = os.path.basename(raw)  # 경로 주입 방어
    if not raw:
        raw = os.path.basename(file_path)

    # 확장자 보정: raw에 없으면 실제 저장 경로의 확장자 사용
    _, raw_ext = os.path.splitext(raw)
    if not raw_ext:
        _, path_ext = os.path.splitext(os.path.basename(file_path))
        if path_ext:
            raw = f"{raw}{path_ext}"

    return _normalize_download_filename(raw, fallback="download", max_len=120)


# -----------------------------
# Upload validation
# -----------------------------
DEFAULT_ALLOWED_EXTENSIONS = {
    ".pdf",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".txt", ".csv",
    ".xls", ".xlsx",
    ".doc", ".docx",
    ".ppt", ".pptx",
    ".hwp", ".hwpx",
}

DEFAULT_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/x-hwp",
    "application/haansofthwp",
    "application/vnd.hancom.hwp",
    "application/vnd.hancom.hwpx",
}

def _as_lower_set(values, *, default: set[str]) -> set[str]:
    raw = values if values is not None else default
    return {str(v or "").strip().lower() for v in raw if str(v or "").strip()}

def _upload_limit_bytes() -> int:
    value = getattr(settings, "BOARD_ATTACHMENT_MAX_UPLOAD_SIZE", DEFAULT_MAX_UPLOAD_SIZE)
    try:
        n = int(value)
    except Exception:
        n = DEFAULT_MAX_UPLOAD_SIZE
    return max(1, n)


def validate_board_attachment(uploaded_file) -> None:
    """
    Board 첨부파일 서버단 검증
    """
    name = os.path.basename(str(getattr(uploaded_file, "name", "") or "")).strip()
    size = int(getattr(uploaded_file, "size", 0) or 0)
    content_type = str(getattr(uploaded_file, "content_type", "") or "").split(";")[0].strip().lower()

    if not name:
        raise ValidationError("파일명이 없습니다.")

    if size <= 0:
        raise ValidationError(f"{name}: 빈 파일입니다.")

    max_size = _upload_limit_bytes()
    if size > max_size:
        mb = max_size / (1024 * 1024)
        raise ValidationError(f"{name}: 파일은 개당 최대 {mb:.0f}MB까지 업로드할 수 있습니다.")

    _, ext = os.path.splitext(name)
    ext = ext.lower()

    allowed_exts = _as_lower_set(
        getattr(settings, "BOARD_ATTACHMENT_ALLOWED_EXTENSIONS", None),
        default=DEFAULT_ALLOWED_EXTENSIONS,
    )

    if ext not in allowed_exts:
        raise ValidationError(f"{name}: 허용되지 않는 파일 확장자입니다.")

    allowed_types = _as_lower_set(
        getattr(settings, "BOARD_ATTACHMENT_ALLOWED_CONTENT_TYPES", None),
        default=DEFAULT_ALLOWED_CONTENT_TYPES,
    )

    guessed_type = (mimetypes.guess_type(name)[0] or "").lower()
    effective_type = content_type or guessed_type

    if effective_type and effective_type not in allowed_types:
        raise ValidationError(f"{name}: 허용되지 않는 파일 형식입니다.")


# -----------------------------
# Public API
# -----------------------------
def save_attachments(*, files: Iterable, create_func: Callable[..., Any]) -> None:
    """
    ✅ files: request.FILES.getlist("attachments")
    ✅ create_func: Attachment/TaskAttachment objects.create 래퍼
    """
    for f in files:
        validate_board_attachment(f)
        create_func(
            file=f,
            original_name=getattr(f, "name", "") or "",
            size=getattr(f, "size", 0) or 0,
            content_type=getattr(f, "content_type", "") or "",
        )


def open_fileresponse_from_fieldfile(fieldfile, *, original_name: str = "") -> FileResponse:
    """
    ✅ FileSystemStorage 기준 다운로드 제공
    - storage가 .path를 지원하지 않으면 Http404 처리(기존 정책 유지)
    - File wrapper로 파일핸들 close 보장
    - Content-Disposition: filename + filename*(UTF-8) 브라우저 호환
    - 파일명 정규화(Windows 호환)
    """
    if not fieldfile or not getattr(fieldfile, "name", ""):
        raise Http404("파일을 찾을 수 없습니다.")

    try:
        file_path = fieldfile.path
    except Exception as exc:
        logger.warning("Attachment path unavailable (storage may not support .path): %s", exc)
        raise Http404("파일을 찾을 수 없습니다.") from exc

    if not file_path or not os.path.exists(file_path):
        raise Http404("파일을 찾을 수 없습니다.")

    filename = _build_download_filename(original_name=original_name, file_path=file_path)

    # ✅ Django File wrapper를 통해 response 종료 시 close 보장
    f = open(file_path, "rb")
    resp = FileResponse(File(f), as_attachment=True)

    # ✅ 한글/특수문자 파일명 브라우저 호환(RFC 5987 filename*=UTF-8''...)
    # - Django가 ASCII fallback + filename* 조합을 생성
    resp["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=filename)
    return resp
