# django_ma/web_ma/middleware.py

from __future__ import annotations

from django.middleware.csrf import get_token
from django.utils.cache import add_never_cache_headers
from django.conf import settings


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
    

class CleanupLegacyCSRFCookieMiddleware:
    """
    운영 환경에서 과거 host-only csrftoken 쿠키를 정리합니다.

    배경:
    - 현재 운영 정책은 CSRF_COOKIE_DOMAIN=".ma-support.kr"
    - 그런데 과거 배포/브라우저 잔존 상태로 host-only 쿠키(ma-support.kr)가
      함께 남아 있으면, 브라우저가 csrftoken을 2개 전송할 수 있습니다.
    - 이 경우 프론트 JS가 첫 번째 쿠키만 읽어 X-CSRFToken 헤더에 넣고,
      Django는 다른 쿠키 값을 기준으로 검증하면서 403이 발생할 수 있습니다.

    방침:
    - 영향 범위를 최소화하기 위해 "운영 도메인" + "csrftoken 중복 존재"일 때만 정리합니다.
    - 현재 정책 쿠키(.ma-support.kr)는 유지하고,
      현재 호스트 기준 host-only csrftoken만 expire 처리합니다.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # ---------------------------------------------------------------------
        # 1) 운영 도메인에서만 동작
        # ---------------------------------------------------------------------
        host = (request.get_host() or "").split(":")[0].strip().lower()
        is_prod_host = host == "ma-support.kr" or host.endswith(".ma-support.kr")
        if not is_prod_host:
            return response

        # ---------------------------------------------------------------------
        # 2) 요청 Cookie 헤더에서 csrftoken 중복 여부 확인
        #    예:
        #    csrftoken=old; csrftoken=new; sessionid=...
        # ---------------------------------------------------------------------
        raw_cookie = request.META.get("HTTP_COOKIE", "") or ""
        csrf_occurrences = raw_cookie.count("csrftoken=")
        if csrf_occurrences < 2:
            return response

        # ---------------------------------------------------------------------
        # 3) 현재 호스트 기준 host-only csrftoken 삭제
        #
        #    - domain 인자를 주지 않으면 현재 호스트 기준 host-only 쿠키 삭제
        #    - 현재 정책 쿠키(.ma-support.kr)는 유지됨
        # ---------------------------------------------------------------------
        response.delete_cookie(
            key="csrftoken",
            path="/",
            samesite=getattr(settings, "CSRF_COOKIE_SAMESITE", "Lax"),
            secure=bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
        )
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
