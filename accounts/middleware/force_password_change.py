# django_ma/accounts/middleware/force_password_change.py
from __future__ import annotations

"""
Phase 3 (Force Password Change) - Middleware

역할:
- request.user가 인증된 상태에서 should_enforce(user)==True이면,
  URL name whitelist 외 모든 요청을 accounts:password_change로 리다이렉트합니다.

중요:
- 기본 비밀번호(id / incar+id) 판별은 여기서 하지 않습니다.
  → 로그인 성공 훅(SessionCloseLoginView.form_valid)에서 must_change_password 플래그로 수렴합니다.
"""

import logging

from django.conf import settings
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse

from accounts.policies.password_policy import should_enforce

log = logging.getLogger("accounts.access")


class ForcePasswordChangeMiddleware:
    """
    ✅ 운영 안정성 체크리스트(내장):
    - /static/, /media/ prefix bypass
    - URL name resolve 실패 시(Resolver404) 강제하지 않음(안전)
    - 무한 리다이렉트 방지: password_change/done 자체는 항상 허용
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or ""

        # ---------------------------------------------------------------------
        # 1) Prefix bypass (URL name 기반 whitelist로 커버 불가한 영역)
        # ---------------------------------------------------------------------
        if path.startswith("/static/") or path.startswith("/media/"):
            return self.get_response(request)

        # (선택) 파비콘/로봇 등도 안전하게 bypass
        if path in ("/favicon.ico", "/robots.txt"):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return self.get_response(request)

        # ---------------------------------------------------------------------
        # 2) URL name resolve
        # ---------------------------------------------------------------------
        try:
            match = resolve(path)
            url_name = (match.url_name or "").strip()
            ns = (match.namespace or "").strip()
            full_name = f"{ns}:{url_name}" if (ns and url_name) else (url_name or "")
        except Resolver404:
            # resolve 실패는 강제 정책으로 전체 장애가 되면 안 됨
            return self.get_response(request)
        except Exception:
            return self.get_response(request)

        # ---------------------------------------------------------------------
        # 3) Whitelist by URL name (SSOT)
        # ---------------------------------------------------------------------
        whitelist = getattr(settings, "FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES", None)
        if not whitelist:
            # settings 미설정이면 안전을 위해 강제하지 않음
            return self.get_response(request)

        # password_change/done은 항상 허용(루프 방지)
        if full_name in whitelist:
            return self.get_response(request)

        # ---------------------------------------------------------------------
        # 4) Policy check (SSOT)
        # ---------------------------------------------------------------------
        try:
            if should_enforce(user, request=request):
                # 강제 리다이렉트
                target = reverse("accounts:password_change")
                log.info("PASSWORD_ENFORCE_REDIRECT user=%s from=%s name=%s", getattr(user, "id", ""), path, full_name)
                return redirect(target)
        except Exception:
            # 정책 엔진 오류가 전체 장애로 이어지지 않게 방어
            log.exception("PASSWORD_ENFORCE_REDIRECT failed path=%s", path)

        return self.get_response(request)