# django_ma/support/views/pages.py

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from support.constants import TOPIC_CHOICES
from support.models import SupportArticle, SupportUserPreference
from support.services.recommend import get_major_articles, get_recommended_articles_for_user


@login_required
def industry_info(request):
    """
    업계정보 최초 랜딩페이지

    설계 원칙:
    - 모든 로그인 사용자가 접근 가능
    - 최신 기사 목록은 항상 먼저 렌더
    - 추천 계산이 실패해도 페이지 전체는 정상 동작
    """

    topic = (request.GET.get("topic") or "").strip()

    latest_qs = SupportArticle.objects.filter(
        is_active=True,
        is_hidden=False,
    ).order_by("-published_at", "-id")

    if topic:
        latest_qs = latest_qs.filter(topic=topic)

    latest_articles = list(latest_qs[:20])

    try:
        recommended_articles = get_recommended_articles_for_user(
            request.user,
            limit=6,
            topic=topic,
        )
    except Exception:
        recommended_articles = get_major_articles(limit=6, topic=topic)

    article_ids = [article.id for article in latest_articles + recommended_articles]
    pref_map = {
        pref.article_id: pref
        for pref in SupportUserPreference.objects.filter(
            user=request.user,
            article_id__in=article_ids,
        )
    }

    context = {
        "topics": TOPIC_CHOICES,
        "selected_topic": topic,
        "recommended_articles": recommended_articles,
        "latest_articles": latest_articles,
        "pref_map": pref_map,
    }
    return render(request, "support/industry_info.html", context)