# django_ma/audit/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import RequestLog, AuditLog


@admin.register(RequestLog)
class RequestLogAdmin(admin.ModelAdmin):
    list_display = (
        "ts", "user_display", "method", "path", "status_code", "duration_ms", "ip",
    )
    list_filter = ("status_code", "method", "is_authenticated")
    search_fields = ("path", "querystring", "ip", "user_agent", "referer", "request_id", "session_key", "user__id", "user__name")
    date_hierarchy = "ts"
    readonly_fields = [f.name for f in RequestLog._meta.fields]
    ordering = ("-ts",)

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

    @admin.display(description="User")
    def user_display(self, obj: RequestLog):
        if obj.user_id:
            return f"{obj.user_id}"
        return "-"


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "ts", "action", "success_badge", "user_display", "object_ref", "ip", "reason",
    )
    list_filter = ("action", "success")
    search_fields = ("action", "reason", "object_type", "object_id", "ip", "request_id", "user__id", "user__name")
    date_hierarchy = "ts"
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    ordering = ("-ts",)

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

    @admin.display(description="User")
    def user_display(self, obj: AuditLog):
        if obj.user_id:
            return f"{obj.user_id}"
        return "-"

    @admin.display(description="Object")
    def object_ref(self, obj: AuditLog):
        if obj.object_type or obj.object_id:
            return f"{obj.object_type}:{obj.object_id}"
        return "-"

    @admin.display(description="OK")
    def success_badge(self, obj: AuditLog):
        if obj.success:
            return format_html('<span style="color:green;font-weight:700;">OK</span>')
        return format_html('<span style="color:#c00;font-weight:700;">FAIL</span>')
    

# =============================================================================
# ✅ custom_admin_site에도 등록 (중요!)
# =============================================================================
try:
    from accounts.custom_admin import custom_admin_site

    # 이미 등록되어 있으면 예외 나므로 방어
    if not custom_admin_site.is_registered(RequestLog):
        custom_admin_site.register(RequestLog, RequestLogAdmin)
    if not custom_admin_site.is_registered(AuditLog):
        custom_admin_site.register(AuditLog, AuditLogAdmin)
except Exception:
    # admin 로딩 실패가 전체를 막지 않도록
    pass