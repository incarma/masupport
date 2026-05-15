# django_ma/manual/utils/files.py

from __future__ import annotations

import os
from urllib.parse import quote

from django.http import FileResponse, Http404
from django.utils.cache import patch_cache_control


def open_manual_fileresponse(
    fieldfile,
    *,
    filename: str = "",
    as_attachment: bool = True,
    cache_private_seconds: int | None = None,
) -> FileResponse:
    """
    ✅ manual 파일 응답 공통 헬퍼

    목적:
    - manual_attachment_download / manual_block_image 의 FileResponse 생성 로직을 통합한다.
    - 첨부파일 직접 URL 노출 금지 원칙을 유지한다.
    - 한글 파일명 다운로드를 위해 RFC5987 filename* 헤더를 유지한다.

    기능 변화 0:
    - 첨부 다운로드: as_attachment=True 유지
    - 블록 이미지: as_attachment=False 유지
    - 이미지 private cache-control 정책 유지 가능
    - 파일이 없으면 기존처럼 Http404 반환
    """
    if not fieldfile:
        raise Http404("파일이 없습니다.")

    resolved_name = filename or os.path.basename(getattr(fieldfile, "name", "") or "")

    try:
        response = FileResponse(
            fieldfile.open("rb"),
            as_attachment=as_attachment,
            filename=resolved_name if as_attachment else None,
        )
    except FileNotFoundError as exc:
        raise Http404("파일을 찾을 수 없습니다.") from exc

    if as_attachment and resolved_name:
        quoted = quote(resolved_name)
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quoted}"

    if cache_private_seconds is not None:
        patch_cache_control(response, private=True, max_age=cache_private_seconds)

    return response