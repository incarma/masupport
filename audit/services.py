# django_ma/audit/services.py
from __future__ import annotations

from typing import Any, Optional

from django.db import transaction

from .models import AuditLog
from .utils import get_client_ip, mask_value


MAX_META_DEPTH = 2
MAX_META_ITEMS = 30


def _safe_meta_value(value: Any, *, depth: int = 0) -> Any:
    if value is None:
        return None

    if isinstance(value, (int, float, bool)):
        return value

    if isinstance(value, str):
        return mask_value(value)

    if depth >= MAX_META_DEPTH:
        return mask_value(str(value))

    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= MAX_META_ITEMS:
                safe["_truncated"] = True
                break
            safe[str(k)[:100]] = _safe_meta_value(v, depth=depth + 1)
        return safe

    if isinstance(value, (list, tuple, set)):
        items = list(value)[:MAX_META_ITEMS]
        safe_items = [_safe_meta_value(v, depth=depth + 1) for v in items]
        if len(list(value)) > MAX_META_ITEMS:
            safe_items.append("_truncated")
        return safe_items

    return mask_value(str(value))


def _safe_meta(meta: Optional[dict[str, Any]]) -> dict[str, Any]:
    """
    meta는 민감정보가 들어가기 쉬움.
    - 문자열은 mask_value 적용
    - dict/list는 구조를 일부 유지하되 깊이/개수를 제한
    """
    if not meta:
        return {}

    safe: dict[str, Any] = {}
    for k, v in meta.items():
        key = str(k)[:100]
        safe_value = _safe_meta_value(v, depth=0)
        if safe_value is None:
            continue
        safe[key] = safe_value
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
    user = getattr(request, "user", None) if request is not None else None
    if obj is not None:
        object_type = object_type or obj.__class__.__name__
        # Django model이면 pk가 있을 가능성이 높음
        object_id = object_id or str(getattr(obj, "pk", "") or "")

    meta_obj = getattr(request, "META", {}) if request is not None else {}
    request_id = getattr(request, "audit_request_id", "") or meta_obj.get("HTTP_X_REQUEST_ID", "") or ""
    ip = get_client_ip(request) if request is not None else ""

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