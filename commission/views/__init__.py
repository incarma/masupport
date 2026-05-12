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
    # 환수내역 안내자료 제작 페이지 (superuser 전용, 클라이언트 전용 xlsx 생성)
    "collect_notice":      ("commission.views.pages", "collect_notice"),
    # 예시표 페이지
    "rate_example_home":   ("commission.views.pages", "rate_example_home"),
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

# Rate Example API (예시표 업로드/다운로드/삭제)
_RATE_EXAMPLE_API = {
    "rate_example_upload":   ("commission.views.api_rate_example", "rate_example_upload"),
    "rate_example_download": ("commission.views.api_rate_example", "rate_example_download"),
    "rate_example_delete":   ("commission.views.api_rate_example", "rate_example_delete"),
    # 환산율/수정률 정규화 데이터 조회 API
    "rate_example_conversion_list": (
        "commission.views.api_rate_example_conversion",
        "rate_example_conversion_list",
    ),
    "rate_example_conversion_strategy_update": (
        "commission.views.api_rate_example_conversion",
        "rate_example_conversion_strategy_update",
    ),
    # 지급률 정규화 데이터 조회 API
    "rate_example_pay_list": (
        "commission.views.api_rate_example_pay",
        "rate_example_pay_list",
    ),
    # 환산율 정규화 초기화 (보험사 단위)
    "rate_example_conversion_reset": (
        "commission.views.api_rate_example_conversion",
        "rate_example_conversion_reset",
    ),
    # 지급률 정규화 전체 초기화
    "rate_example_pay_reset": (
        "commission.views.api_rate_example_pay",
        "rate_example_pay_reset",
    ),
    # 수수료 예시표 메인 계산 테이블 옵션 조회 API
    "rate_example_options": (
        "commission.views.api_rate_example_options",
        "rate_example_options",
    ),
}

# Collect Notice export
_COLLECT_NOTICE_EXPORTS = {
    "collect_notice_export_excel": (
        "commission.views.collect_notice_export",
        "collect_notice_export_excel",
    ),
}

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
    # Rate Example API (예시표)
    # -------------------------------------------------------------------------
    if name in _RATE_EXAMPLE_API:
        mod_path, attr = _RATE_EXAMPLE_API[name]
        mod = _import_first(mod_path)
        return getattr(mod, attr)

    # -------------------------------------------------------------------------
    # Collect Notice Excel Export
    # -------------------------------------------------------------------------
    if name in _COLLECT_NOTICE_EXPORTS:
        mod_path, attr = _COLLECT_NOTICE_EXPORTS[name]
        mod = _import_first(mod_path)
        return getattr(mod, attr)

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
    "collect_notice",
    "collect_notice_export_excel",
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
    # rate example
    "rate_example_home",
    "rate_example_upload",
    "rate_example_download",
    "rate_example_delete",
    "rate_example_conversion_list",
    "rate_example_options",
    "rate_example_conversion_strategy_update",
    "rate_example_pay_list",
    "rate_example_conversion_reset",
    "rate_example_pay_reset",
]