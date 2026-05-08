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

    # =========================================================
    # Collect (환수관리)
    # 기존 URL name 변경 금지. 신규 추가만.
    # 업로드는 기존 commission:upload_excel 재사용 (신규 URL 불필요)
    # =========================================================
    path("collect/",                    views.collect_home,                name="collect_home"),
    path("collect/api/list/",           views.api_collect_list,            name="api_collect_list"),
    path("collect/api/ym-list/",        views.api_collect_ym_list,         name="api_collect_ym_list"),
    path("collect/api/feedback/",       views.api_collect_feedback_list,   name="api_collect_feedback_list"),
    path("collect/api/feedback/create/",views.api_collect_feedback_create, name="api_collect_feedback_create"),
    path("collect/api/feedback/update/",views.api_collect_feedback_update, name="api_collect_feedback_update"),
    path("collect/api/feedback/delete/",views.api_collect_feedback_delete, name="api_collect_feedback_delete"),
    path("collect/api/dropdown-feedback/save/", views.api_collect_dropdown_feedback_save, name="api_collect_dropdown_feedback_save"),

    # =========================================================================
    # Collect Notice (환수내역 안내자료)
    # - 페이지: 기존 URL name 유지
    # - 엑셀 생성: openpyxl 서버 생성 API 신규 추가
    # =========================================================================
    path("collect/notice/", views.collect_notice, name="collect_notice"),
    path(
        "collect/notice/export/",
        views.collect_notice_export_excel,
        name="collect_notice_export_excel",
    ),

    # =========================================================================
    # 예시표 (RateExample)
    # =========================================================================
    path("rate-examples/",
         views.rate_example_home,     name="rate_example_home"),
    path("rate-examples/upload/",
         views.rate_example_upload,   name="rate_example_upload"),
    path("rate-examples/<int:pk>/download/",
         views.rate_example_download, name="rate_example_download"),
    path("rate-examples/<int:pk>/delete/",
         views.rate_example_delete,   name="rate_example_delete"),
     path("rate-examples/conversions/",
         views.rate_example_conversion_list, name="rate_example_conversion_list"),
]