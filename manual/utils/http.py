# django_ma/manual/utils/http.py

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from django.http import JsonResponse


def json_body(request) -> Dict[str, Any]:
    """
    ✅ request.body(JSON)를 안전하게 dict로 파싱
    - 파싱 실패/빈 바디: {}
    """
    try:
        raw = (request.body or b"").decode("utf-8")
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return {}


def ok(data: Optional[dict] = None) -> JsonResponse:
    """
    ✅ 통일된 성공 응답 포맷
    """
    payload = {"ok": True}
    if isinstance(data, dict):
        payload.update(data)
    return JsonResponse(payload)


def fail(message: str, status: int = 400, **extra) -> JsonResponse:
    """
    ✅ 통일된 실패 응답 포맷
    """
    payload = {"ok": False, "message": message}
    if extra:
        payload.update(extra)
    return JsonResponse(payload, status=status)
