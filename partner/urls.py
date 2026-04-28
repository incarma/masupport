# django_ma/partner/urls.py

from django.urls import path
from . import views

app_name = "partner"

urlpatterns = [
    # Pages
    path("", views.redirect_to_join, name="join_form"),
    path("join/", views.join_form, name="join_form"),
    path("calculate/", views.manage_calculate, name="manage_calculate"),
    path("grades/", views.manage_grades, name="manage_grades"),
    path("charts/", views.manage_charts, name="manage_charts"),
    path("rate/", views.manage_rate, name="manage_rate"),
    path("tables/", views.manage_tables, name="manage_tables"),
    path("upload-grades-excel/", views.upload_grades_excel, name="upload_grades_excel"),

    # Structure Change
    path("api/structure/fetch/", views.structure_fetch, name="structure_fetch"),
    path("api/structure/save/", views.structure_save, name="structure_save"),
    path("api/structure/delete/", views.structure_delete, name="structure_delete"),
    path(
        "api/structure/update-process-date/",
        views.structure_update_process_date,
        name="structure_update_process_date",
    ),

    # Rate Change
    path("api/rate/fetch/", views.rate_fetch, name="rate_fetch"),
    path("api/rate/save/", views.rate_save, name="rate_save"),
    path("api/rate/delete/", views.rate_delete, name="rate_delete"),
    path(
        "api/rate/update-process-date/",
        views.rate_update_process_date,
        name="rate_update_process_date",
    ),

    # ✅ Efficiency (Accordion groups + rows)
    path("api/efficiency/fetch/", views.efficiency_fetch, name="efficiency_fetch"),
    path("api/efficiency/save/", views.efficiency_save, name="efficiency_save"),
    path("api/efficiency/delete/", views.efficiency_delete_row, name="efficiency_delete_row"),
    path("api/efficiency/delete-group/", views.efficiency_delete_group, name="efficiency_delete_group"),
    path(
        "api/efficiency/update-process-date/",
        views.efficiency_update_process_date,
        name="efficiency_update_process_date",
    ),

    # ✅ Efficiency confirm
    path(
        "efficiency/confirm-template/download/",
        views.efficiency_confirm_template_download,
        name="efficiency_confirm_template_download",
    ),
    path("efficiency/confirm-groups/", views.efficiency_confirm_groups, name="efficiency_confirm_groups"),
    path("efficiency/confirm-upload/", views.efficiency_confirm_upload, name="efficiency_confirm_upload"),
    path(
        "efficiency/attachments/<int:att_id>/download/",
        views.efficiency_confirm_attachment_download,
        name="efficiency_confirm_attachment_download",
    ),

    # Permission Management
    path("api/users-data/", views.ajax_users_data, name="ajax_users_data"),
    path("api/update-level/", views.ajax_update_level, name="ajax_update_level"),

    # Part/Branch utilities
    path("ajax/fetch-channels/", views.ajax_fetch_channels, name="ajax_fetch_channels"),
    path("ajax/fetch-parts/", views.ajax_fetch_parts, name="ajax_fetch_parts"),
    path("ajax/fetch-branches/", views.ajax_fetch_branches, name="ajax_fetch_branches"),

    # Table Setting
    path("ajax/table-fetch/", views.ajax_table_fetch, name="ajax_table_fetch"),
    path("ajax/table-save/", views.ajax_table_save, name="ajax_table_save"),

    # RateTable
    path("ajax/rate-userlist/", views.ajax_rate_userlist, name="ajax_rate_userlist"),
    path("ajax/rate-userlist-excel/", views.ajax_rate_userlist_excel, name="ajax_rate_userlist_excel"),
    path("ajax/rate-userlist-upload/", views.ajax_rate_userlist_upload, name="ajax_rate_userlist_upload"),
    path("ajax/rate-user-detail/", views.ajax_rate_user_detail, name="ajax_rate_user_detail"),
    path(
        "ajax/rate-userlist-template-excel/",
        views.ajax_rate_userlist_template_excel,
        name="ajax_rate_userlist_template_excel",
    ),

    # Legacy aliases (편제 공용)
    path("api/fetch/", views.structure_fetch, name="ajax_fetch"),
    path("api/save/", views.structure_save, name="ajax_save"),
    path("api/delete/", views.structure_delete, name="ajax_delete"),
    path("api/update-process-date/",views.structure_update_process_date,name="ajax_update_process_date",),

    path("api/add-sub-admin/", views.ajax_add_sub_admin, name="ajax_add_sub_admin"),
    path("ajax/delete-subadmin/", views.ajax_delete_subadmin, name="ajax_delete_subadmin"),

    # ── 전자서명 (esign) ───────────────────────────────────────
    # 페이지
    path('esign/', views.esign_confirm_page, name='esign_confirm'),
 
    # 데이터 API
    path('api/esign/fetch/',        views.esign_fetch,        name='esign_fetch'),
    path('api/esign/save/',         views.esign_save,         name='esign_save'),
    path('api/esign/delete-group/', views.esign_delete_group, name='esign_delete_group'),
 
    # 서명 API
    path('api/esign/<int:request_id>/sign/', views.esign_sign, name='esign_sign'),
 
    # PDF 다운로드 (FileResponse — url 직접 노출 금지)
    path('api/esign/<int:request_id>/pdf/', views.esign_pdf_download, name='esign_pdf'),

    path('api/esign/process-date/', views.esign_update_process_date, name='esign_update_process_date'),
]
