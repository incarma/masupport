# django_ma/commission/views/api_deposit.py
from __future__ import annotations

"""
Backward-compatible shim.

- 1) 패키지 분리 구조(commission.views.api.deposit)가 존재하면 우선 사용
- 2) 없으면 단일 구현(commission.views.api_deposit_impl) fallback
- 3) 특정 attr이 없더라도 import 시점에서 죽지 않도록 안전가드 제공
"""

from importlib import import_module
from typing import Any, Callable

from django.http import JsonResponse

from .api_deposit_impl import *  # noqa


def _import_impl():
    # 1) 패키지 분리 구조가 있으면 그걸 사용
    try:
        return import_module("commission.views.api.deposit")
    except Exception:
        # 2) 없으면 단일 모듈 사용
        return import_module("commission.views.api_deposit_impl")


def _missing(name: str) -> Callable[..., Any]:
    def _fn(request, *args, **kwargs):
        return JsonResponse({"ok": False, "message": f"{name} is not available"}, status=501)
    return _fn


_impl = _import_impl()

search_user = getattr(_impl, "search_user", _missing("search_user"))
api_user_detail = getattr(_impl, "api_user_detail", _missing("api_user_detail"))
api_deposit_summary = getattr(_impl, "api_deposit_summary", _missing("api_deposit_summary"))
api_deposit_surety_list = getattr(_impl, "api_deposit_surety_list", _missing("api_deposit_surety_list"))
api_deposit_other_list = getattr(_impl, "api_deposit_other_list", _missing("api_deposit_other_list"))
api_support_pdf = getattr(_impl, "api_support_pdf", _missing("api_support_pdf"))

__all__ = [
    "search_user",
    "api_user_detail",
    "api_deposit_summary",
    "api_deposit_surety_list",
    "api_deposit_other_list",
    "api_support_pdf",
]
