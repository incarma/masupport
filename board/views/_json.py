# board/views/_json.py
# board 앱 JSON 응답 헬퍼 SSOT.
# 응답 포맷: {"ok": true/false, ...}
from django.http import JsonResponse


def _json_ok(message: str | None = None, **extra) -> JsonResponse:
    payload = {"ok": True}
    if message is not None:
        payload["message"] = message
    payload.update(extra)
    return JsonResponse(payload)


def _json_err(message: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "message": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)
