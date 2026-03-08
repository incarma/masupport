# django_ma/support/views/api.py

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.constants import ACTION
from audit.services import log_action
from support.models import SupportArticle, SupportUserPreference


def _json_ok(message="ok", **data):
    """
    support 앱 공용 성공 JSON 응답
    """
    return JsonResponse({"ok": True, "message": message, "data": data})


def _json_err(message="error", status=400, **data):
    """
    support 앱 공용 실패 JSON 응답
    """
    return JsonResponse({"ok": False, "message": message, "data": data}, status=status)


@login_required
@require_POST
def save_preference(request, article_id: int):
    """
    사용자 선호도 저장 API

    저장 대상:
    - 평점(1~5)
    - 북마크 여부
    - 관심없음 여부
    """

    article = get_object_or_404(
        SupportArticle,
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

    pref, _ = SupportUserPreference.objects.get_or_create(
        user=request.user,
        article=article,
    )

    changed_actions = []

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
        log_action(
            request,
            action,
            object_type="SupportArticle",
            object_id=str(article.id),
            meta={
                "article_id": article.id,
                "title": article.title[:120],
                "rating": pref.rating,
                "is_bookmarked": pref.is_bookmarked,
                "is_hidden": pref.is_hidden,
            },
        )

    return _json_ok(
        "저장되었습니다.",
        article_id=article.id,
        rating=pref.rating,
        is_bookmarked=pref.is_bookmarked,
        is_hidden=pref.is_hidden,
    )


@login_required
@require_POST
def mark_click(request, article_id: int):
    """
    원문보기 클릭 기록 API

    처리 방식:
    - 클릭 이벤트는 과도한 감사로그 폭증을 피하기 위해
      preference 상태 갱신 위주로 처리합니다.
    """

    article = get_object_or_404(
        SupportArticle,
        pk=article_id,
        is_active=True,
        is_hidden=False,
    )

    pref, _ = SupportUserPreference.objects.get_or_create(
        user=request.user,
        article=article,
    )

    pref.clicked_at = timezone.now()
    pref.is_read = True
    pref.read_at = pref.read_at or timezone.now()
    pref.save(update_fields=["clicked_at", "is_read", "read_at", "updated_at"])

    return _json_ok("기록되었습니다.", article_id=article.id)