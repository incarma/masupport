# django_ma/commission/views/_files.py
from __future__ import annotations

"""
Upload file helpers (views layer SSOT)

목표:
- api_upload.py / approval.py 등에서 반복되는 임시 업로드 파일 저장/삭제 로직을 공통화
- 기능 변화 없이 코드 중복 제거 + 예외 안전성 강화

주의:
- FileSystemStorage 기본 설정(Django MEDIA storage)에 그대로 저장했다가 finally에서 삭제하는 패턴 유지
- "저장 -> 처리 -> 삭제" lifecycle만 공통화
"""

from dataclasses import dataclass
import logging
from typing import Optional

from django.core.files.storage import FileSystemStorage


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TempUpload:
    """
    임시 업로드 파일 메타.

    - fs: 저장에 사용한 FileSystemStorage
    - saved_name: storage 상의 저장명
    - file_path: 로컬 경로(fs.path)
    - original_name: 업로드된 원본 파일명
    """
    fs: FileSystemStorage
    saved_name: str
    file_path: str
    original_name: str


def save_temp_upload(excel_file, *, fs: Optional[FileSystemStorage] = None) -> TempUpload:
    """
    업로드 파일을 FileSystemStorage로 저장하고 TempUpload 정보를 반환.

    excel_file: request.FILES.get("excel_file") 로 받은 UploadedFile
    """
    storage = fs or FileSystemStorage()
    original_name = getattr(excel_file, "name", "") or ""
    saved_name = storage.save(original_name, excel_file)
    file_path = storage.path(saved_name)
    return TempUpload(
        fs=storage,
        saved_name=saved_name,
        file_path=file_path,
        original_name=original_name,
    )


def safe_delete(temp: TempUpload) -> None:
    """
    임시 업로드 파일 삭제 (실패해도 예외 전파하지 않음).
    - 기존 코드의 "finally: try delete except pass" 패턴을 SSOT화
    """
    try:
        temp.fs.delete(temp.saved_name)
    except Exception:
        logger.exception("[commission.files] temp upload delete failed saved_name=%s", temp.saved_name)