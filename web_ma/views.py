# django_ma/web_ma/views.py
import logging
from django.http import HttpResponseServerError
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.csrf import requires_csrf_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)

@requires_csrf_token
def handler500(request):
    # 현재 예외 컨텍스트를 강제로 로깅 (traceback 포함)
    logger.exception("Unhandled server error (500)")
    return HttpResponseServerError("Server Error (500)")


@ensure_csrf_cookie
@never_cache
def landing_view(request):
    """
    랜딩 페이지 뷰.
    - 인증된 사용자  : support:industry_info 로 즉시 리다이렉트
   - 미인증 사용자  : 랜딩 페이지 렌더링 (DB 쿼리 없음 — 정적 에셋만)
    """
    if request.user.is_authenticated:
        return redirect("support:industry_info")

    context = {
        "next_url": reverse("support:industry_info"),
    }
    return render(request, "landing/index.html", context)