# django_ma/board/views/industry_info.py

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.constants import ACTION
from audit.services import log_action

from board.constants_industry import TOPIC_CHOICES
from board.industry_models import IndustryArticle, IndustryUserPreference
from board.services.industry_recommend import (
    get_major_articles,
    get_recommended_articles_for_user,
)


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


def _json_ok(message: str = "ok", **data) -> JsonResponse:
    return JsonResponse({"ok": True, "message": message, "data": data})


def _json_err(message: str = "error", status: int = 400, **data) -> JsonResponse:
    return JsonResponse({"ok": False, "message": message, "data": data}, status=status)


def _get_per_page(request: HttpRequest) -> int:
    """per_page 파라미터 정규화 — 허용값 외는 기본값으로 fallback"""
    try:
        val = int(request.GET.get("per_page", INDUSTRY_PER_PAGE_DEFAULT))
    except (TypeError, ValueError):
        val = INDUSTRY_PER_PAGE_DEFAULT
    return val if val in INDUSTRY_PER_PAGE_CHOICES else INDUSTRY_PER_PAGE_DEFAULT


# =========================================================
# Page View — 메인
# =========================================================
@login_required
def industry_info(request: HttpRequest) -> HttpResponse:
    topic = (request.GET.get("topic") or "").strip()
    per_page = _get_per_page(request)

    latest_qs = IndustryArticle.objects.filter(
        is_active=True,
        is_hidden=False,
    ).order_by("-published_at", "-id")

    if topic:
        latest_qs = latest_qs.filter(topic=topic)

    # 페이지네이션
    paginator = Paginator(latest_qs, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))
    latest_articles = list(page_obj)

    try:
        recommended_articles = get_recommended_articles_for_user(
            request.user,
            limit=6,
            topic=topic,
        )
    except Exception:
        logger.exception("industry_info recommendation failed; fallback to major articles")
        recommended_articles = get_major_articles(limit=6, topic=topic)

    article_ids = [a.id for a in (latest_articles + recommended_articles)]
    pref_map = {
        pref.article_id: pref
        for pref in IndustryUserPreference.objects.filter(
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
        "bookmarked_only": False,
        "bookmark_count": IndustryUserPreference.objects.filter(
            user=request.user,
            is_bookmarked=True,
        ).count(),
        # 페이지네이션
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

    bookmarked_ids = (
        IndustryUserPreference.objects
        .filter(user=request.user, is_bookmarked=True)
        .values_list("article_id", flat=True)
    )

    latest_qs = (
        IndustryArticle.objects
        .filter(
            id__in=bookmarked_ids,
            is_active=True,
            is_hidden=False,
        )
        .order_by("-published_at", "-id")
    )

    if topic:
        latest_qs = latest_qs.filter(topic=topic)

    # 페이지네이션
    paginator = Paginator(latest_qs, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))
    latest_articles = list(page_obj)

    bookmark_count = IndustryUserPreference.objects.filter(
        user=request.user,
        is_bookmarked=True,
    ).count()

    article_ids = [a.id for a in latest_articles]
    pref_map = {
        pref.article_id: pref
        for pref in IndustryUserPreference.objects.filter(
            user=request.user,
            article_id__in=article_ids,
        )
    }

    context = {
        "topics": TOPIC_CHOICES,
        "selected_topic": topic,
        "recommended_articles": [],
        "latest_articles": latest_articles,
        "pref_map": pref_map,
        "bookmarked_only": True,
        "bookmark_count": bookmark_count,
        # 페이지네이션
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
    article = get_object_or_404(
        IndustryArticle,
        pk=article_id,
        is_active=True,
        is_hidden=False,
    )

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
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

    pref, _ = IndustryUserPreference.objects.get_or_create(
        user=request.user,
        article=article,
    )

    changed_actions: list[str] = []

    if rating is not None:
        pref.rating = rating
        changed_actions.append(ACTION.SUPPORT_USER_RATE)

    if is_bookmarked is not None:
        pref.is_bookmarked = bool(is_bookmarked)
        changed_actions.append(ACTION.SUPPORT_USER_BOOKMARK)

    if is_hidden is not None:
        pref.is_hidden = bool(is_hidden)
        changed_actions.append(ACTION.SUPPORT_USER_HIDE)

    pref.updated_at = timezone.now()
    pref.save()

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
    article = get_object_or_404(
        IndustryArticle,
        pk=article_id,
        is_active=True,
        is_hidden=False,
    )

    pref, _ = IndustryUserPreference.objects.get_or_create(
        user=request.user,
        article=article,
    )

    pref.clicked_at = timezone.now()
    pref.is_read = True
    pref.read_at = pref.read_at or timezone.now()
    pref.save(update_fields=["clicked_at", "is_read", "read_at", "updated_at"])

    return _json_ok("기록되었습니다.", article_id=article.id)