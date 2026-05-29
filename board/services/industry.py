# board/services/industry.py
# 업계정보 뷰 레이어 전용 서비스 함수 SSOT.
# 뷰에서 IndustryArticle / IndustryUserPreference ORM 직접 호출 금지.

from __future__ import annotations

from django.db.models import QuerySet
from django.utils import timezone

from board.industry_models import IndustryArticle, IndustryUserPreference


def get_article_qs(*, topic: str = "") -> QuerySet:
    """활성 기사 기본 쿼리셋 (topic 필터 선택)."""
    qs = (
        IndustryArticle.objects
        .filter(is_active=True, is_hidden=False)
        .order_by("-published_at", "-id")
    )
    if topic:
        qs = qs.filter(topic=topic)
    return qs


def get_bookmarked_article_ids(user) -> QuerySet:
    """사용자 북마크 article_id ValuesQuerySet."""
    return (
        IndustryUserPreference.objects
        .filter(user=user, is_bookmarked=True)
        .values_list("article_id", flat=True)
    )


def get_bookmarked_article_qs(user, *, topic: str = "") -> QuerySet:
    """사용자 북마크 기사 쿼리셋."""
    bookmarked_ids = get_bookmarked_article_ids(user)
    qs = (
        IndustryArticle.objects
        .filter(id__in=bookmarked_ids, is_active=True, is_hidden=False)
        .order_by("-published_at", "-id")
    )
    if topic:
        qs = qs.filter(topic=topic)
    return qs


def get_pref_map(user, article_ids: list) -> dict:
    """article_id → IndustryUserPreference 딕셔너리."""
    if not article_ids:
        return {}
    return {
        pref.article_id: pref
        for pref in IndustryUserPreference.objects.filter(
            user=user,
            article_id__in=article_ids,
        )
    }


def get_bookmark_count(user) -> int:
    """사용자 북마크 수."""
    return IndustryUserPreference.objects.filter(
        user=user,
        is_bookmarked=True,
    ).count()


def get_or_create_pref(user, article) -> tuple:
    """(IndustryUserPreference, created) 반환."""
    return IndustryUserPreference.objects.get_or_create(
        user=user,
        article=article,
    )


def update_and_save_pref(
    pref,
    *,
    rating=None,
    is_bookmarked=None,
    is_hidden=None,
) -> None:
    """선호도 필드 갱신 후 저장 (뷰에서 timezone 의존성 제거)."""
    if rating is not None:
        pref.rating = rating
    if is_bookmarked is not None:
        pref.is_bookmarked = bool(is_bookmarked)
    if is_hidden is not None:
        pref.is_hidden = bool(is_hidden)
    pref.updated_at = timezone.now()
    pref.save()


def mark_clicked(pref) -> None:
    """클릭 기록: clicked_at, is_read, read_at 갱신."""
    now = timezone.now()
    pref.clicked_at = now
    pref.is_read = True
    pref.read_at = pref.read_at or now
    pref.save(update_fields=["clicked_at", "is_read", "read_at", "updated_at"])
