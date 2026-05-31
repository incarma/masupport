# django_ma/web_ma/views.py
import logging
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseServerError
from django.shortcuts import redirect
from django.views.decorators.csrf import requires_csrf_token
from django.views.decorators.cache import never_cache


logger = logging.getLogger(__name__)


@never_cache
def healthz(request):
    return HttpResponse("ok\n", content_type="text/plain")


@requires_csrf_token
def handler500(request):
    # 현재 예외 컨텍스트를 강제로 로깅 (traceback 포함)
    logger.exception("Unhandled server error (500)")
    return HttpResponseServerError("Server Error (500)")


@login_required
@never_cache
def landing_view(request):
    """
    루트 뷰. 로그인한 사용자만 진입 가능.
    - 인증된 사용자  : board:industry_info 로 즉시 리다이렉트
    - 미인증 사용자  : /login/?next=/ 로 리다이렉트
    """
    return redirect("board:industry_info")