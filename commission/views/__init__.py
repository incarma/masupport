# django_ma/commission/views/__init__.py
from __future__ import annotations

from importlib import import_module
from typing import Any, Iterable

from django.http import HttpResponse


# =============================================================================
# Internal helpers
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


def _stub_501(name: str, err: Exception):
    """
    URLConf import 단계에서 전체 서비스가 죽는 것을 막기 위한 501 stub.
    - 실제 운영에서는 해당 엔드포인트를 완성한 뒤 이 stub이 호출되지 않도록 하는 것이 목표.
    """
    def _view(request, *args, **kwargs):
        return HttpResponse(
            f"{name} is not available: {err.__class__.__name__}",
            status=501,
        )
    return _view


# =============================================================================
# Lazy surface (Django import from `from . import views` safe)
# =============================================================================
def __getattr__(name: str) -> Any:
    # ---------------------------------------------------------------------
    # Pages (commission/urls.py에서 참조)
    # ---------------------------------------------------------------------
    if name in {"redirect_to_deposit", "deposit_home", "approval_home", "support_home"}:
        mod = _import_first("commission.views.pages")
        return getattr(mod, name)

    # legacy alias
    if name == "commission_home":
        mod = _import_first("commission.views.pages")
        return getattr(mod, "redirect_to_deposit")

    # ---------------------------------------------------------------------
    # Upload (채권 SSOT 업로드)
    # ---------------------------------------------------------------------
    if name == "upload_excel":
        mod = _import_first("commission.views.api_upload")
        return getattr(mod, name)

    # ---------------------------------------------------------------------
    # Deposit APIs (조회 + PDF)
    # - impl 우선, 없으면 shim fallback
    # ---------------------------------------------------------------------
    if name in {
        "search_user",
        "api_user_detail",
        "api_deposit_summary",
        "api_deposit_surety_list",
        "api_deposit_other_list",
        "api_support_pdf",
    }:
        mod_impl = _import_first("commission.views.api_deposit_impl")
        if hasattr(mod_impl, name):
            return getattr(mod_impl, name)

        mod_shim = _import_first("commission.views.api_deposit")
        return getattr(mod_shim, name)

    # ---------------------------------------------------------------------
    # Approval/Efficiency upload
    # - 모듈/함수 미존재 시 URLConf 전체 500 방지
    # ---------------------------------------------------------------------
    if name in {"approval_upload_excel", "efficiency_upload_excel"}:
        try:
            mod = _import_first("commission.views.approval")
            return getattr(mod, name)
        except Exception as e:
            return _stub_501(name, e)

    # ---------------------------------------------------------------------
    # Downloads
    # ---------------------------------------------------------------------
    if name in {
        "download_upload_fail_excel",
        "download_approval_pending_excel",
        "download_efficiency_excess_excel",
    }:
        mod = _import_first("commission.views.downloads")
        return getattr(mod, name)

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
]