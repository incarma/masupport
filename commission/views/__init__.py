# django_ma/commission/views/__init__.py
from __future__ import annotations

from importlib import import_module
from typing import Any, Callable

from django.http import HttpResponse

# =============================================================================
# Lazy import helpers
# =============================================================================


def _import_first(*module_paths: str):
    """
    Try importing module paths in order and return the first importable module.
    Raises the last exception if all fail.
    """
    last_err: Exception | None = None
    for mp in module_paths:
        try:
            return import_module(mp)
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    raise ModuleNotFoundError("No module paths provided.")


def _stub_501(name: str, err: Exception) -> Callable[..., HttpResponse]:
    """
    URLConf import 단계에서 서비스 전체가 죽는 것을 막기 위한 501 stub.
    (운영 목표: 정상 구현 완료 후 stub이 호출되지 않게 하는 것)
    """

    def _view(request, *args, **kwargs):
        return HttpResponse(
            f"{name} is not available: {err.__class__.__name__}",
            status=501,
        )

    return _view


# =============================================================================
# Lazy surface map
# =============================================================================

# 1) pages
_PAGES = {
    "redirect_to_deposit": ("commission.views.pages", "redirect_to_deposit"),
    "deposit_home": ("commission.views.pages", "deposit_home"),
    "approval_home": ("commission.views.pages", "approval_home"),
    "support_home": ("commission.views.pages", "support_home"),
    # legacy alias
    "commission_home": ("commission.views.pages", "redirect_to_deposit"),
    "collect_home": ("commission.views.pages", "collect_home"),
}

_COLLECT_API_NAMES = frozenset({
     "api_collect_list",
     "api_collect_ym_list",
     "api_collect_feedback_list",
     "api_collect_feedback_create",
     "api_collect_feedback_update",
     "api_collect_feedback_delete",
     "api_collect_dropdown_feedback_save",
 })

# 2) upload (deposit)
_UPLOAD = {
    "upload_excel": ("commission.views.api_upload", "upload_excel"),
}

# 3) deposit apis (impl 우선, shim fallback)
_DEPOSIT_APIS = {
    "search_user",
    "api_user_detail",
    "api_deposit_summary",
    "api_deposit_surety_list",
    "api_deposit_other_list",
    "api_support_pdf",
}

# 4) approval/efficiency upload (모듈 미존재/오류 시 501 stub)
_APPROVAL_UPLOADS = {"approval_upload_excel", "efficiency_upload_excel"}

# 5) downloads
_DOWNLOADS = {
    "download_upload_fail_excel": ("commission.views.downloads", "download_upload_fail_excel"),
    "download_approval_pending_excel": ("commission.views.downloads", "download_approval_pending_excel"),
    "download_efficiency_excess_excel": ("commission.views.downloads", "download_efficiency_excess_excel"),
}


def __getattr__(name: str) -> Any:
    # -------------------------------------------------------------------------
    # Pages
    # -------------------------------------------------------------------------
    if name in _PAGES:
        mod_path, attr = _PAGES[name]
        mod = _import_first(mod_path)
        return getattr(mod, attr)
    
    # -------------------------------------------------------------------------
    # Collect API 뷰 lazy import
    # -------------------------------------------------------------------------
    if name in _COLLECT_API_NAMES:
        from commission.views import api_collect as _api_collect
        return getattr(_api_collect, name)

    # -------------------------------------------------------------------------
    # Upload (Deposit SSOT)
    # -------------------------------------------------------------------------
    if name in _UPLOAD:
        mod_path, attr = _UPLOAD[name]
        mod = _import_first(mod_path)
        return getattr(mod, attr)

    # -------------------------------------------------------------------------
    # Deposit APIs (impl 우선, shim fallback)
    # -------------------------------------------------------------------------
    if name in _DEPOSIT_APIS:
        mod_impl = _import_first("commission.views.api_deposit_impl")
        if hasattr(mod_impl, name):
            return getattr(mod_impl, name)
        mod_shim = _import_first("commission.views.api_deposit")
        return getattr(mod_shim, name)

    # -------------------------------------------------------------------------
    # Approval/Efficiency upload (안전 stub)
    # -------------------------------------------------------------------------
    if name in _APPROVAL_UPLOADS:
        try:
            mod = _import_first("commission.views.approval")
            return getattr(mod, name)
        except Exception as e:
            return _stub_501(name, e)

    # -------------------------------------------------------------------------
    # Downloads
    # -------------------------------------------------------------------------
    if name in _DOWNLOADS:
        mod_path, attr = _DOWNLOADS[name]
        mod = _import_first(mod_path)
        return getattr(mod, attr)

    raise AttributeError(f"module 'commission.views' has no attribute '{name}'")


__all__ = [
    # pages
    "redirect_to_deposit",
    "commission_home",
    "deposit_home",
    "approval_home",
    "support_home",
    # upload
    "upload_excel",
    "approval_upload_excel",
    "efficiency_upload_excel",
    # deposit apis
    "search_user",
    "api_user_detail",
    "api_deposit_summary",
    "api_deposit_surety_list",
    "api_deposit_other_list",
    "api_support_pdf",
    # downloads
    "download_upload_fail_excel",
    "download_approval_pending_excel",
    "download_efficiency_excess_excel",
    "collect_home",
    "api_collect_list",
    "api_collect_ym_list",
    "api_collect_feedback_list",
    "api_collect_feedback_create",
    "api_collect_feedback_update",
    "api_collect_feedback_delete",
    "api_collect_dropdown_feedback_save",
]