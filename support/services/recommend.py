# django_ma/support/services/recommend.py

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import List

from django.db.models import Avg, Count, Q
from django.utils import timezone

from support.constants import SUPPORT_RECOMMEND_MODEL_VERSION
from support.models import SupportArticle, SupportUserPreference


def _base_queryset(topic: str = ""):
    """
    추천/인기 기사 공용 queryset

    처리 내용:
    - 활성 기사만 조회
    - 운영 숨김 기사 제외
    - 평균 평점 / 북마크 수를 annotate
    """

    qs = (
        SupportArticle.objects.filter(is_active=True, is_hidden=False)
        .annotate(
            avg_rating=Avg("preferences__rating"),
            bookmark_count=Count("preferences", filter=Q(preferences__is_bookmarked=True)),
        )
        .order_by("-published_at", "-id")
    )

    if topic:
        qs = qs.filter(topic=topic)

    return qs


def get_major_articles(limit: int = 6, topic: str = "") -> List[SupportArticle]:
    """
    추천 데이터가 부족하거나 추천 계산이 실패한 경우의 fallback

    주요 기사 선정 기준:
    - 최근성
    - 평균 평점
    - 북마크 수
    """

    now = timezone.now()
    articles = list(_base_queryset(topic=topic)[:80])
    scored = []

    for article in articles:
        published = article.published_at or now
        recency_hours = max(0.0, 72.0 - ((now - published).total_seconds() / 3600.0))
        rating = float(article.avg_rating or 0.0)
        bookmarks = int(article.bookmark_count or 0)

        score = recency_hours * 0.20 + rating * 2.5 + bookmarks * 0.50

        # ---------------------------------------------------------------------
        # 템플릿 엔진 호환용 추천 메타데이터
        # - Django 템플릿은 underscore(_) 로 시작하는 속성 접근을 금지하므로
        #   템플릿에 전달할 임시 속성은 일반 식별자 형태로 유지합니다.
        # ---------------------------------------------------------------------
        article.recommend_reason = "최근 인기 기사"
        article.recommend_reason_code = "major_recent"
        article.recommend_model_version = SUPPORT_RECOMMEND_MODEL_VERSION

        scored.append((score, article))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [article for _, article in scored[:limit]]


def get_recommended_articles_for_user(user, limit: int = 6, topic: str = "") -> List[SupportArticle]:
    """
    사용자 맞춤 추천 MVP

    현재 추천 구성:
    - 최근 기사 가중치
    - 사용자 토픽 선호
    - 언론사 선호
    - 기사 자체 평점/북마크 인기도
    - 관심없음/이미 높게 평가한 기사 제외
    """

    if not getattr(user, "is_authenticated", False):
        return get_major_articles(limit=limit, topic=topic)

    prefs = SupportUserPreference.objects.filter(user=user).select_related("article")
    hidden_ids = set(prefs.filter(is_hidden=True).values_list("article_id", flat=True))
    liked_qs = prefs.filter(Q(rating__gte=4) | Q(is_bookmarked=True))

    if not liked_qs.exists():
        return get_major_articles(limit=limit, topic=topic)

    topic_weights = Counter()
    source_weights = Counter()
    liked_ids = set()

    for pref in liked_qs:
        liked_ids.add(pref.article_id)

        if pref.article.topic:
            topic_weights[pref.article.topic] += 2 if pref.rating and pref.rating >= 4 else 1

        if pref.article.source_name:
            source_weights[pref.article.source_name] += 1

    now = timezone.now()
    recent_cutoff = now - timedelta(days=14)

    candidates = list(
        _base_queryset(topic=topic)
        .exclude(id__in=hidden_ids | liked_ids)
        .filter(Q(published_at__gte=recent_cutoff) | Q(published_at__isnull=True))[:120]
    )

    if not candidates:
        return get_major_articles(limit=limit, topic=topic)

    scored = []

    for article in candidates:
        published = article.published_at or now
        age_hours = max(1.0, (now - published).total_seconds() / 3600.0)

        recency_score = max(0.0, 96.0 - age_hours) * 0.15
        topic_score = float(topic_weights.get(article.topic, 0)) * 1.8
        source_score = float(source_weights.get(article.source_name, 0)) * 1.2
        rating_score = float(article.avg_rating or 0.0) * 1.5
        bookmark_score = float(article.bookmark_count or 0) * 0.4

        total = recency_score + topic_score + source_score + rating_score + bookmark_score

        # ---------------------------------------------------------------------
        # 추천 사유 / 코드 / 모델 버전
        # - 템플릿 include에서 직접 접근하므로 underscore 접두어를 쓰지 않습니다.
        # ---------------------------------------------------------------------
        if topic_score >= source_score and article.topic:
            article.recommend_reason = f"최근 관심을 보인 {article.topic} 관련 기사입니다."
            article.recommend_reason_code = "topic_match"
        elif source_score > 0 and article.source_name:
            article.recommend_reason = f"{article.source_name} 출처 선호를 반영했습니다."
            article.recommend_reason_code = "source_match"
        else:
            article.recommend_reason = "최근성과 관심도 점수를 반영한 추천입니다."
            article.recommend_reason_code = "major_recent"

        article.recommend_model_version = SUPPORT_RECOMMEND_MODEL_VERSION
        scored.append((total, article))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [article for _, article in scored[:limit]]