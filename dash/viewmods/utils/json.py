# django_ma/dash/viewmods/utils/json.py
from django.http import JsonResponse


def json_err(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "message": message}, status=status)