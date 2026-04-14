# django_ma/board/views/industry_info.py
# =========================================================
# Board Industry Info Views
# - support 업계정보 기능을 board로 1차 브리지 이관
# - DB/테이블은 기존 support 모델을 그대로 사용
# - board는 URL / 템플릿 / JS 진입점만 우선 제공
# =========================================================

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
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
    "industry_save_preference",
    "industry_mark_click",
]


# =========================================================
# JSON Helpers
# - board 내 다른 JSON 응답 패턴과 유사하게 통일
# =========================================================
def _json_ok(message: str = "ok", **data) -> JsonResponse:
    return JsonResponse({"ok": True, "message": message, "data": data})


def _json_err(message: str = "error", status: int = 400, **data) -> JsonResponse:
    return JsonResponse({"ok": False, "message": message, "data": data}, status=status)


# =========================================================
# Page View
# =========================================================
@login_required
def industry_info(request: HttpRequest) -> HttpResponse:
    """
    board 업계정보 메인 페이지

    설계 원칙:
    - 로그인 사용자 전체 허용
    - support의 기존 추천 로직/데이터를 재사용
    - board 템플릿으로만 진입점을 먼저 이동
    - 추천 실패 시 fallback 기사 목록으로 안전 복구
    """
    topic = (request.GET.get("topic") or "").strip()

    latest_qs = IndustryArticle.objects.filter(
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
        logger.exception("industry_info recommendation failed; fallback to major articles")
        recommended_articles = get_major_articles(limit=6, topic=topic)

    article_ids = [article.id for article in (latest_articles + recommended_articles)]
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
    }
    return render(request, "board/industry_info.html", context)


# =========================================================
# Preference API
# - rating / bookmark / hide
# =========================================================
@login_required
@require_POST
def industry_save_preference(request: HttpRequest, article_id: int) -> JsonResponse:
    """
    board 업계정보 사용자 선호도 저장 API

    저장 대상:
    - rating
    - is_bookmarked
    - is_hidden

    1단계에서는 support_user_preference 테이블에 그대로 저장한다.
    """

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
# - 원문보기 클릭 기록
# =========================================================
@login_required
@require_POST
def industry_mark_click(request: HttpRequest, article_id: int) -> JsonResponse:
    """
    board 업계정보 기사 클릭 기록 API

    처리 내용:
    - clicked_at
    - is_read
    - read_at
    """
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