# django_ma/board/views/industry_info.py

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from audit.constants import ACTION
from audit.services import log_action

from board.constants_industry import TOPIC_CHOICES
from board.industry_models import IndustryArticle
from board.services.industry import (
    get_article_qs,
    get_bookmark_count,
    get_bookmarked_article_qs,
    get_or_create_pref,
    get_pref_map,
    mark_clicked,
    update_and_save_pref,
)
from board.services.industry_recommend import (
    get_major_articles,
    get_recommended_articles_for_user,
)
from board.services.industry_news import normalize_external_url
from board.services.rate_limit import check_rate_limit, rate_limited_json
from board.views._json import _json_ok, _json_err


logger = logging.getLogger(__name__)

__all__ = [
    "industry_info",
    "industry_bookmarks",
    "industry_save_preference",
    "industry_mark_click",
]


# =========================================================
# 상수
# =========================================================
INDUSTRY_PER_PAGE_CHOICES = [20, 50, 100, 150]
INDUSTRY_PER_PAGE_DEFAULT = 20


def _get_per_page(request: HttpRequest) -> int:
    """per_page 파라미터 정규화 — 허용값 외는 기본값으로 fallback"""
    try:
        val = int(request.GET.get("per_page", INDUSTRY_PER_PAGE_DEFAULT))
    except (TypeError, ValueError):
        val = INDUSTRY_PER_PAGE_DEFAULT
    return val if val in INDUSTRY_PER_PAGE_CHOICES else INDUSTRY_PER_PAGE_DEFAULT


def _attach_safe_display_url(articles) -> list:
    """
    기존 DB에 이미 저장된 비정상 URL까지 화면 출력 단계에서 차단한다.
    - 수집 단계 검증은 신규 데이터 방어
    - 이 함수는 과거 데이터/수동 입력/DB 오염 방어
    """
    out = list(articles or [])
    for article in out:
        raw = (
            getattr(article, "display_url", "")
            or getattr(article, "original_url", "")
            or getattr(article, "portal_url", "")
            or ""
        )
        article.safe_display_url = normalize_external_url(raw)
    return out


# =========================================================
# Page View — 메인
# =========================================================
@login_required
def industry_info(request: HttpRequest) -> HttpResponse:
    topic = (request.GET.get("topic") or "").strip()
    per_page = _get_per_page(request)

    paginator = Paginator(get_article_qs(topic=topic), per_page)
    page_obj = paginator.get_page(request.GET.get("page"))
    latest_articles = _attach_safe_display_url(page_obj)

    try:
        recommended_articles = get_recommended_articles_for_user(
            request.user,
            limit=6,
            topic=topic,
        )
    except Exception:
        logger.exception("industry_info recommendation failed; fallback to major articles")
        recommended_articles = get_major_articles(limit=6, topic=topic)

    recommended_articles = _attach_safe_display_url(recommended_articles)

    article_ids = [a.id for a in (latest_articles + recommended_articles)]
    context = {
        "topics": TOPIC_CHOICES,
        "selected_topic": topic,
        "recommended_articles": recommended_articles,
        "latest_articles": latest_articles,
        "pref_map": get_pref_map(request.user, article_ids),
        "bookmarked_only": False,
        "bookmark_count": get_bookmark_count(request.user),
        "page_obj": page_obj,
        "per_page": per_page,
        "per_page_choices": INDUSTRY_PER_PAGE_CHOICES,
    }
    return render(request, "board/industry_info.html", context)


# =========================================================
# Page View — 북마크
# =========================================================
@login_required
def industry_bookmarks(request: HttpRequest) -> HttpResponse:
    topic = (request.GET.get("topic") or "").strip()
    per_page = _get_per_page(request)

    paginator = Paginator(get_bookmarked_article_qs(request.user, topic=topic), per_page)
    page_obj = paginator.get_page(request.GET.get("page"))
    latest_articles = _attach_safe_display_url(page_obj)

    article_ids = [a.id for a in latest_articles]
    context = {
        "topics": TOPIC_CHOICES,
        "selected_topic": topic,
        "recommended_articles": [],
        "latest_articles": latest_articles,
        "pref_map": get_pref_map(request.user, article_ids),
        "bookmarked_only": True,
        "bookmark_count": get_bookmark_count(request.user),
        "page_obj": page_obj,
        "per_page": per_page,
        "per_page_choices": INDUSTRY_PER_PAGE_CHOICES,
    }
    return render(request, "board/industry_info.html", context)


# =========================================================
# Preference API
# =========================================================
@login_required
@require_POST
def industry_save_preference(request: HttpRequest, article_id: int) -> JsonResponse:
    rl = check_rate_limit(
        request,
        scope="industry:preference",
        rule=getattr(settings, "BOARD_INDUSTRY_PREF_RATE_LIMIT", "30/60"),
    )
    if not rl.allowed:
        return rate_limited_json(rl)
    
    article = get_object_or_404(
        IndustryArticle,
        pk=article_id,
        is_active=True,
        is_hidden=False,
    )

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _json_err("요청 본문이 올바르지 않습니다.")

    rating = body.get("rating")
    is_bookmarked = body.get("is_bookmarked")
    is_hidden = body.get("is_hidden")

    if rating in ("", None):
        rating = None

    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return _json_err("평점은 숫자여야 합니다.")
        if rating < 1 or rating > 5:
            return _json_err("평점은 1~5 사이여야 합니다.")

    pref, _ = get_or_create_pref(request.user, article)

    changed_actions: list[str] = []
    if rating is not None:
        changed_actions.append(ACTION.SUPPORT_USER_RATE)
    if is_bookmarked is not None:
        changed_actions.append(ACTION.SUPPORT_USER_BOOKMARK)
    if is_hidden is not None:
        changed_actions.append(ACTION.SUPPORT_USER_HIDE)

    update_and_save_pref(pref, rating=rating, is_bookmarked=is_bookmarked, is_hidden=is_hidden)

    for action in changed_actions:
        try:
            log_action(
                request,
                action,
                object_type="IndustryArticle",
                object_id=str(article.id),
                meta={
                    "article_id": article.id,
                    "title": article.title[:120],
                    "rating": pref.rating,
                    "is_bookmarked": pref.is_bookmarked,
                    "is_hidden": pref.is_hidden,
                    "source_app": "board",
                },
            )
        except Exception:
            logger.exception("industry preference audit log failed")

    return _json_ok(
        "저장되었습니다.",
        article_id=article.id,
        rating=pref.rating,
        is_bookmarked=pref.is_bookmarked,
        is_hidden=pref.is_hidden,
    )


# =========================================================
# Click API
# =========================================================
@login_required
@require_POST
def industry_mark_click(request: HttpRequest, article_id: int) -> JsonResponse:
    rl = check_rate_limit(
        request,
        scope="industry:click",
        rule=getattr(settings, "BOARD_INDUSTRY_CLICK_RATE_LIMIT", "60/60"),
    )
    if not rl.allowed:
        return rate_limited_json(rl)

    article = get_object_or_404(
        IndustryArticle,
        pk=article_id,
        is_active=True,
        is_hidden=False,
    )

    pref, _ = get_or_create_pref(request.user, article)
    mark_clicked(pref)
    return _json_ok("기록되었습니다.", article_id=article.id)