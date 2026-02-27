# django_ma/audit/services.py
from __future__ import annotations

from typing import Any, Optional

from django.db import transaction

from .models import AuditLog
from .utils import get_client_ip, mask_value


def _safe_meta(meta: Optional[dict[str, Any]]) -> dict[str, Any]:
    """
    meta는 민감정보가 들어가기 쉬움.
    - 문자열은 mask_value 적용
    - dict/list는 너무 깊게 저장하지 않도록 제한
    """
    if not meta:
        return {}

    safe: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (int, float, bool)):
            safe[k] = v
        elif isinstance(v, str):
            safe[k] = mask_value(v)
        else:
            # 복잡한 객체는 str로 축약
            safe[k] = mask_value(str(v))
    return safe


@transaction.atomic
def log_action(
    request,
    action: str,
    *,
    obj: Any = None,
    object_type: str = "",
    object_id: str = "",
    meta: Optional[dict[str, Any]] = None,
    success: bool = True,
    reason: str = "",
) -> AuditLog:
    """
    중요 이벤트 기록.
    - obj를 넘기면 기본적으로 model명/PK를 object_type/object_id로 사용
    """
    user = getattr(request, "user", None)
    if obj is not None:
        object_type = object_type or obj.__class__.__name__
        # Django model이면 pk가 있을 가능성이 높음
        object_id = object_id or str(getattr(obj, "pk", "") or "")

    request_id = getattr(request, "audit_request_id", "") or request.META.get("HTTP_X_REQUEST_ID", "") or ""
    ip = get_client_ip(request)

    return AuditLog.objects.create(
        action=action,
        user=user if getattr(user, "is_authenticated", False) else None,
        ip=ip,
        success=bool(success),
        reason=(reason or "")[:300],
        object_type=(object_type or "")[:100],
        object_id=(object_id or "")[:64],
        meta=_safe_meta(meta),
        request_id=(request_id or "")[:64],
    )