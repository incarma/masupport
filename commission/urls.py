from __future__ import annotations

from django.urls import path

from . import views

app_name = "commission"

urlpatterns = [
    # =========================================================================
    # Pages
    # =========================================================================
    path("", views.redirect_to_deposit, name="commission_home"),
    path("deposit/", views.deposit_home, name="deposit_home"),
    path("approval/", views.approval_home, name="approval_home"),
    # (지원신청서 페이지는 현재 미사용이므로 views.support_home가 안전 fallback 처리)

    # =========================================================================
    # Upload APIs
    # =========================================================================
    path("upload-excel/", views.upload_excel, name="upload_excel"),
    path("approval/upload-excel/", views.approval_upload_excel, name="approval_upload_excel"),

    # =========================================================================
    # Downloads (token 기반 fail 다운로드 포함)
    # =========================================================================
    path("download/upload-fail/", views.download_upload_fail_excel, name="download_upload_fail_excel"),
    path("approval/excel/pending/", views.download_approval_pending_excel, name="download_approval_pending_excel"),
    path(
        "approval/excel/efficiency-excess/",
        views.download_efficiency_excess_excel,
        name="download_efficiency_excess_excel",
    ),

    # =========================================================================
    # Data APIs (Deposit)
    # =========================================================================
    path("api/user-detail/", views.api_user_detail, name="api_user_detail"),
    path("api/deposit-summary/", views.api_deposit_summary, name="api_deposit_summary"),
    path("api/deposit-surety/", views.api_deposit_surety_list, name="api_deposit_surety_list"),
    path("api/deposit-other/", views.api_deposit_other_list, name="api_deposit_other_list"),
    path("api/support-pdf/", views.api_support_pdf, name="api_support_pdf"),
]