# django_ma/commission/upload_utils/_db.py
from __future__ import annotations

"""
commission 업로드 DB 보조 유틸.

신규 업로드 로그 갱신은 upload_handlers.deposit._update_upload_log가 SSOT다.
이 모듈의 _update_upload_log는 과거 import 경로 보호용 deprecated wrapper다.
"""

from typing import Iterable

# =========================================================
# DB helpers
# =========================================================
def _bulk_existing_user_ids(ids: Iterable[str]):
    """
    CustomUser에 실제 존재하는 사번 PK만 bulk 조회한다.

    업로드 핸들러에서 row별 exists()를 호출하지 않기 위한 성능 보조 함수다.
    """
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

    유지 이유:
    - 과거 코드가 commission.upload_utils._update_upload_log 를 import할 수 있다.
    - 실제 구현은 deposit handler SSOT로 위임한다.
    - 신규 코드는 이 wrapper를 직접 import하지 않는다.
    - 이 함수 삭제 시 레거시 import 경로가 깨질 수 있으므로 P4 구조 이동 전까지 유지한다.
    """
    from commission.upload_handlers.deposit import _update_upload_log as _ssot_update

    return _ssot_update(
        part=part,
        upload_type=upload_type,
        excel_file_name=excel_file_name,
        count=count,
    )