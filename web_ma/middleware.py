# django_ma/web_ma/middleware.py

from __future__ import annotations

from django.middleware.csrf import get_token
from django.utils.cache import add_never_cache_headers


class ForceCSRFCookieOnLoginMiddleware:
    """
    ✅ /login/ (및 /admin/login/) GET 시점에 csrftoken 쿠키를 강제로 발급.
    - URL이 어떤 LoginView를 쓰든 상관 없이 동작(=가장 안전)
    - 캐시/프록시가 로그인 HTML을 캐시해도, no-store로 차단
    """

    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        path = request.path or ""
        # ✅ 타겟을 "정확히" 좁힘 (의도치 않은 경로 포함 방지)
        is_login_page = (
            path == "/login/"
            or path.startswith("/admin/login/")
        )

        if request.method == "GET" and is_login_page:
            # ✅ 토큰 생성 + "쿠키 업데이트 필요" 플래그를 강제
            # - 일부 브라우저/캐시 조합에서 get_token만으로 Set-Cookie가 누락되는 케이스 방어
            get_token(request)
            request.META["CSRF_COOKIE_NEEDS_UPDATE"] = True

        response = self.get_response(request)

        if request.method == "GET" and is_login_page:
            # ✅ 로그인 페이지는 절대 캐시되면 안 됨(Set-Cookie 유실/재사용 이슈 방지)
            # add_never_cache_headers가 Expires/Cache-Control/Pragma까지 표준적으로 처리
            add_never_cache_headers(response)
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"

        return response
    

# -----------------------------------------------------------------------------
# NOTE (Phase 3)
# -----------------------------------------------------------------------------
# 강제 비밀번호 변경 미들웨어는 "accounts 앱 스코프"로 관리합니다.
# - 구현 파일: django_ma/accounts/middleware/force_password_change.py
# - settings.py의 MIDDLEWARE에는 다음 dotted-path로 등록합니다:
#   "accounts.middleware.force_password_change.ForcePasswordChangeMiddleware"
#
# 이유:
# - 정책 엔진(should_enforce) 및 accounts URL name whitelist 등 SSOT가
#   accounts 도메인에 더 가깝고, 장기 운영에서 변경 범위를 좁히기 위함입니다.
