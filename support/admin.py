# django_ma/support/admin.py

from django.contrib import admin

from .models import (
    SupportArticle,
    SupportCollectJobLog,
    SupportRecommendation,
    SupportUserPreference,
)


@admin.register(SupportArticle)
class SupportArticleAdmin(admin.ModelAdmin):
    """
    업계정보 기사 운영용 admin
    """

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


@admin.register(SupportUserPreference)
class SupportUserPreferenceAdmin(admin.ModelAdmin):
    """
    사용자 선호도 확인용 admin
    """

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


@admin.register(SupportRecommendation)
class SupportRecommendationAdmin(admin.ModelAdmin):
    """
    추천 스냅샷 운영 확인용 admin
    """

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


@admin.register(SupportCollectJobLog)
class SupportCollectJobLogAdmin(admin.ModelAdmin):
    """
    기사 수집 작업 로그 admin
    """

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