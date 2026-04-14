# django_ma/board/admin.py

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from django.contrib import admin
from django.http import HttpResponse
from django.urls import path
from django.utils.html import format_html
from django.utils.timezone import localtime

from accounts.custom_admin import custom_admin_site
from .industry_models import (
    IndustryArticle,
    IndustryCollectJobLog,
    IndustryRecommendation,
    IndustryUserPreference,
)
from .models import Post


# =========================================================
# Excel Export (Posts)
# =========================================================
def export_posts_as_excel(queryset, filename: str = "posts_export.xlsx") -> HttpResponse:
    """
    Post queryset을 엑셀로 내보내는 공용 함수
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Posts"

    headers = [
        "접수번호",
        "제목",
        "사번(요청자)",
        "성명(요청자)",
        "소속(요청자)",
        "성명(대상자)",
        "사번(대상자)",
        "담당자",
        "상태",
        "상태변경일",
        "최초등록일",
    ]
    ws.append(headers)

    # Header 스타일 + 고정
    header_font = Font(bold=True)
    for col_idx in range(1, len(headers) + 1):
        ws.cell(row=1, column=col_idx).font = header_font
    ws.freeze_panes = "A2"

    for post in queryset:
        ws.append([
            post.receipt_number,
            post.title,
            post.user_id,
            post.user_name,
            post.user_branch,
            post.fa,
            post.code,
            post.handler or "-",
            post.status,
            localtime(post.status_updated_at).strftime("%Y-%m-%d %H:%M") if post.status_updated_at else "-",
            localtime(post.created_at).strftime("%Y-%m-%d %H:%M"),
        ])
    
    # Auto filter
    ws.auto_filter.ref = ws.dimensions
    
    # 열 너비 자동 조정(상한 적용)
    MAX_W = 50
    PADDING = 2
    for col_idx in range(1, ws.max_column + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 0
        for row_idx in range(1, ws.max_row + 1):
            v = ws.cell(row=row_idx, column=col_idx).value
            if v is None:
                continue
            s = str(v)
            if len(s) > max_len:
                max_len = len(s)
        ws.column_dimensions[col_letter].width = min(MAX_W, max(10, max_len + PADDING))

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename={filename}'
    wb.save(response)
    return response


# =========================================================
# Admin
# - custom_admin_site 접근 자체가 grade==superuser만 허용(기존 정책)
# =========================================================
@admin.register(Post, site=custom_admin_site)
class PostAdmin(admin.ModelAdmin):
    """
    업무요청(Post) 관리자 페이지
    """

    # -----------------------------
    # List / Filter / Search
    # -----------------------------
    list_display = (
        "get_receipt_number",
        "get_category",
        "get_title",
        "get_user_id",
        "get_user_name",
        "get_user_branch",
        "get_fa",
        "get_code",
        "get_handler",
        "colored_status",
        "get_status_updated_at",
        "get_created_at",
    )
    list_filter = ("status", "handler", "user_branch", "category", "created_at")
    search_fields = ("title", "content", "user_name", "user_id", "fa", "code", "handler")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "status_updated_at", "receipt_number")

    # -----------------------------
    # Fieldsets
    # -----------------------------
    fieldsets = (
        ("게시글 정보", {"fields": ("receipt_number", "category", "title", "content", "fa", "code")}),
        ("작성자 정보", {"fields": ("user_id", "user_name", "user_branch")}),
        ("담당자 / 상태 관리", {"fields": ("handler", "status", "status_updated_at")}),
        ("기타", {"fields": ("created_at",)}),
    )

    # -----------------------------
    # Actions
    # -----------------------------
    actions = ["export_selected_posts_to_excel"]

    def export_selected_posts_to_excel(self, request, queryset):
        return export_posts_as_excel(queryset, filename="selected_posts.xlsx")

    export_selected_posts_to_excel.short_description = "선택된 게시글을 Excel로 다운로드"

    # -----------------------------
    # Custom URLs (Export All)
    # -----------------------------
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "export-all/",
                self.admin_site.admin_view(self.export_all_posts_view),
                name="export_all_posts_excel",
            ),
        ]
        return custom_urls + urls

    def export_all_posts_view(self, request):
        return export_posts_as_excel(self.model.objects.all(), filename="all_posts.xlsx")

    # -----------------------------
    # UI Helpers
    # -----------------------------
    def colored_status(self, obj):
        color_map = {
            "확인중": "orange",
            "진행중": "green",
            "보완요청": "red",
            "완료": "black",
            "반려": "gray",
        }
        color = color_map.get(obj.status, "black")
        return format_html('<span style="color:{}; font-weight:600;">{}</span>', color, obj.status)

    colored_status.short_description = "상태"

    # -----------------------------
    # Display Labels (한글 컬럼명)
    # -----------------------------
    def get_receipt_number(self, obj): return obj.receipt_number
    get_receipt_number.short_description = "접수번호"

    def get_category(self, obj): return obj.category
    get_category.short_description = "구분"

    def get_title(self, obj): return obj.title
    get_title.short_description = "제목"

    def get_user_id(self, obj): return obj.user_id
    get_user_id.short_description = "사번(요청자)"

    def get_user_name(self, obj): return obj.user_name
    get_user_name.short_description = "성명(요청자)"

    def get_user_branch(self, obj): return obj.user_branch
    get_user_branch.short_description = "소속(요청자)"

    def get_fa(self, obj): return obj.fa
    get_fa.short_description = "성명(대상자)"

    def get_code(self, obj): return obj.code
    get_code.short_description = "사번(대상자)"

    def get_handler(self, obj): return obj.handler
    get_handler.short_description = "담당자"

    def get_status_updated_at(self, obj):
        return localtime(obj.status_updated_at).strftime("%Y-%m-%d %H:%M") if obj.status_updated_at else "-"
    get_status_updated_at.short_description = "상태변경일"

    def get_created_at(self, obj):
        return localtime(obj.created_at).strftime("%Y-%m-%d %H:%M")
    get_created_at.short_description = "최초등록일"



# =========================================================
# Industry Info Admin (Proxy Models)
# - 실제 DB는 support_* 테이블을 사용
# - board에서 운영/검수 화면을 통합 제공
# =========================================================
@admin.register(IndustryArticle, site=custom_admin_site)
class IndustryArticleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "source_name",
        "topic",
        "published_at",
        "is_active",
        "is_hidden",
    )
    list_filter = ("source_portal", "topic", "is_active", "is_hidden")
    search_fields = ("title", "summary", "source_name", "keyword_query")
    ordering = ("-published_at", "-id")


@admin.register(IndustryUserPreference, site=custom_admin_site)
class IndustryUserPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "article",
        "rating",
        "is_bookmarked",
        "is_hidden",
        "updated_at",
    )
    list_filter = ("is_bookmarked", "is_hidden", "is_read")
    search_fields = ("user__id", "article__title")


@admin.register(IndustryRecommendation, site=custom_admin_site)
class IndustryRecommendationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "article",
        "score",
        "reason_code",
        "model_version",
        "created_at",
    )
    list_filter = ("reason_code", "model_version", "clicked")
    search_fields = ("user__id", "article__title")


@admin.register(IndustryCollectJobLog, site=custom_admin_site)
class IndustryCollectJobLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "query",
        "status",
        "fetched_count",
        "inserted_count",
        "error_count",
        "created_at",
    )
    list_filter = ("source", "status")
    search_fields = ("query", "message")