# django_ma/commission/upload_utils/_db.py

from __future__ import annotations

from typing import Iterable

# =========================================================
# DB helpers
# =========================================================
def _bulk_existing_user_ids(ids: Iterable[str]):
    """CustomUser 존재하는 PK들을 bulk로 조회."""
    from accounts.models import CustomUser

    ids = [str(x).strip() for x in ids if x is not None and str(x).strip()]
    if not ids:
        return set()
    qs = CustomUser.objects.filter(pk__in=ids).values_list("pk", flat=True)
    return set(str(x) for x in qs)


def _update_upload_log(part: str, upload_type: str, excel_file_name: str, count: int):
    """
    ⚠️ Deprecated wrapper.
    업로드 로그 SSOT는 commission.upload_handlers.deposit._update_upload_log 를 사용.
    """
    from commission.upload_handlers.deposit import _update_upload_log as _ssot_update

    return _ssot_update(
        part=part,
        upload_type=upload_type,
        excel_file_name=excel_file_name,
        count=count,
    )