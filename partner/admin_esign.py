# partner/admin_esign.py
"""
전자서명 관련 모델 Django Admin 등록

등록 모델:
  - EfficiencySignRequest  : 서명 요청 (확인서 단위)
  - EfficiencyConfirmSign  : 개별 참여자 서명 이력

audit/admin.py 패턴 준수:
  - custom_admin_site 동시 등록 (accounts/audit와 동일)
  - has_add_permission = False (뷰에서만 생성)
  - has_delete_permission: superuser만 허용
"""

import logging

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from partner.models import EfficiencySignRequest, EfficiencyConfirmSign


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# EfficiencyConfirmSign Inline
# ─────────────────────────────────────────────────────────────────────────────

class EfficiencyConfirmSignInline(admin.TabularInline):
    model            = EfficiencyConfirmSign
    extra            = 0
    can_delete       = False
    show_change_link = True

    fields = (
        'signer', 'role', 'signed_at',
        'ip_address', 'session_key', 'pass_verified_at_sign',
    )
    readonly_fields = (
        'signer', 'role', 'signed_at',
        'ip_address', 'session_key', 'pass_verified_at_sign',
    )

    def has_add_permission(self, request, obj=None):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# EfficiencySignRequest Admin
# ─────────────────────────────────────────────────────────────────────────────

class EfficiencySignRequestAdmin(admin.ModelAdmin):
    list_display   = (
        'id', 'ym', 'branch', 'status_badge',
        'row_count', 'signed_count',
        'pdf_link', 'created_by', 'created_at',
    )
    list_filter    = ('status', 'ym', 'branch')
    search_fields  = ('ym', 'branch', 'created_by__name', 'created_by__id')
    ordering       = ('-created_at',)
    date_hierarchy = 'created_at'

    readonly_fields = (
        'confirm_group', 'ym', 'branch', 'created_by',
        'status', 'doc_hash',
        'created_at', 'updated_at',
        'pdf_download_link',
    )
    fields = (
        ('ym', 'branch', 'status'),
        'confirm_group',
        'created_by',
        ('doc_hash', 'pdf_download_link'),
        ('created_at', 'updated_at'),
    )

    inlines = [EfficiencyConfirmSignInline]

    # ── 커스텀 컬럼 ──────────────────────────────────────────────

    @admin.display(description='상태', ordering='status')
    def status_badge(self, obj):
        palette = {
            'pending':   ('#dc3545', '서명 대기'),
            'partial':   ('#ffc107', '서명 진행중'),
            'completed': ('#198754', '서명 완료'),
            'cancelled': ('#6c757d', '취소'),
        }
        color, label = palette.get(obj.status, ('#6c757d', obj.status))
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 8px;'
            'border-radius:4px;font-size:11px;">{}</span>',
            color, label,
        )

    @admin.display(description='행 수')
    def row_count(self, obj):
        group = obj.confirm_group
        return group.efficiency_rows.count() if group else 0

    @admin.display(description='서명 현황')
    def signed_count(self, obj):
        signed = obj.signs.filter(signed_at__isnull=False).count()
        total  = obj.signs.count()
        return f'{signed} / {total}'

    @admin.display(description='확인서 PDF')
    def pdf_link(self, obj):
        if not obj.pdf_file:
            return '—'
        url = reverse('partner:esign_pdf', kwargs={'request_id': obj.pk})
        return format_html('<a href="{}" target="_blank">📄 다운로드</a>', url)

    @admin.display(description='PDF 다운로드')
    def pdf_download_link(self, obj):
        if not obj.pdf_file:
            return '서명 완료 후 생성됩니다.'
        url = reverse('partner:esign_pdf', kwargs={'request_id': obj.pk})
        return format_html(
            '<a class="button" href="{}" target="_blank">📄 확인서 다운로드</a>',
            url,
        )

    def has_add_permission(self, request):
        return False  # 뷰에서만 생성 허용

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ─────────────────────────────────────────────────────────────────────────────
# EfficiencyConfirmSign Admin
# ─────────────────────────────────────────────────────────────────────────────

class EfficiencyConfirmSignAdmin(admin.ModelAdmin):
    list_display   = (
        'id', 'request_link', 'signer', 'role_badge',
        'signed_at', 'ip_address', 'created_at',
    )
    list_filter    = ('role', 'request__status', 'request__ym')
    search_fields  = (
        'signer__name', 'signer__id',
        'request__ym', 'request__branch',
        'ip_address',
    )
    ordering       = ('-created_at',)
    date_hierarchy = 'created_at'

    readonly_fields = (
        'request', 'signer', 'role',
        'signed_at', 'ip_address', 'user_agent',
        'session_key', 'pass_verified_at_sign',
        'created_at',
    )
    fields = (
        'request',
        ('signer', 'role'),
        ('signed_at', 'ip_address'),
        'user_agent',
        ('session_key', 'pass_verified_at_sign'),
        'created_at',
    )

    @admin.display(description='서명 요청', ordering='request__id')
    def request_link(self, obj):
        url = reverse(
            'admin:partner_efficiencysignrequest_change',
            args=[obj.request_id],
        )
        return format_html(
            '<a href="{}">{} / {} [{}]</a>',
            url,
            obj.request.ym,
            obj.request.branch,
            obj.request.get_status_display(),
        )

    @admin.display(description='역할', ordering='role')
    def role_badge(self, obj):
        palette = {
            'deduct':       ('공제자',          '#dc3545'),
            'pay':          ('지급자',          '#0d6efd'),
            'head_confirm': ('최고관리자 확인', '#198754'),
        }
        label, color = palette.get(obj.role, (obj.role, '#6c757d'))
        mark = ' ✅' if obj.signed_at else ' ⏳'
        return format_html(
            '<span style="color:{};font-weight:600;">{}{}</span>',
            color, label, mark,
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ─────────────────────────────────────────────────────────────────────────────
# 기본 admin site + custom_admin_site 동시 등록
# audit/admin.py 패턴 준수
# ─────────────────────────────────────────────────────────────────────────────

admin.site.register(EfficiencySignRequest, EfficiencySignRequestAdmin)
admin.site.register(EfficiencyConfirmSign, EfficiencyConfirmSignAdmin)

try:
    from accounts.custom_admin import custom_admin_site

    if not custom_admin_site.is_registered(EfficiencySignRequest):
        custom_admin_site.register(EfficiencySignRequest, EfficiencySignRequestAdmin)
    if not custom_admin_site.is_registered(EfficiencyConfirmSign):
        custom_admin_site.register(EfficiencyConfirmSign, EfficiencyConfirmSignAdmin)
except Exception:
    logger.exception("[partner.admin_esign] custom_admin_site registration failed")