# django_ma/accounts/views.py
from __future__ import annotations
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordChangeDoneView,
)
from django.utils import timezone
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse, FileResponse, Http404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache

from .constants import (
    CACHE_ERROR_PREFIX,
    CACHE_PROGRESS_PREFIX,
    CACHE_RESULT_PATH_PREFIX,
    CACHE_STATUS_PREFIX,
    cache_key,
)
from .forms import ActiveOnlyAuthenticationForm, StrictPasswordChangeForm
from .search_api import search_users_for_api

import logging
from django.http import HttpResponseForbidden

logger = logging.getLogger("django.security.csrf")
access_logger = logging.getLogger("accounts.access")

def csrf_failure(request, reason=""):
    logger.warning(
        "CSRF FAILED | reason=%s | path=%s | method=%s | host=%s | secure=%s | "
        "xf_proto=%s | xf_host=%s | referer=%s | origin=%s | cookie=%s | ua=%s",
        reason,
        request.path,
        request.method,
        request.get_host(),
        request.is_secure(),
        request.META.get("HTTP_X_FORWARDED_PROTO"),
        request.META.get("HTTP_X_FORWARDED_HOST"),
        request.META.get("HTTP_REFERER"),
        request.META.get("HTTP_ORIGIN"),
        request.META.get("HTTP_COOKIE"),
        request.META.get("HTTP_USER_AGENT"),
    )
    return HttpResponseForbidden(f"CSRF Failed: {reason}")

def _set_no_store_headers(response: HttpResponse) -> HttpResponse:
    # 로그인 페이지/CSRF 관련 페이지는 캐시되면 안 됨
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# =============================================================================
# Password Change (로그인 사용자 비밀번호 변경)
# =============================================================================
@method_decorator(login_required, name="dispatch")
class UserPasswordChangeView(PasswordChangeView):
    """
    ✅ 1단계: 로그인 사용자가 직접 비밀번호를 변경할 수 있는 페이지

    - Django 표준 PasswordChangeView 사용
    - 성공 시 done 페이지로 이동
    - template은 registration/password_change_form.html 사용
    """
    template_name = "registration/password_change_form.html"
    form_class = StrictPasswordChangeForm

    def get_success_url(self) -> str:
        return reverse("accounts:password_change_done")
    
    def form_valid(self, form) -> HttpResponse:
        """
        Phase 3:
        - 비밀번호 변경 성공 시 must_change_password 플래그를 해제합니다.
        - '기본 비번 여부'는 여기서 판별하지 않습니다(불필요/위험).
        """
        response = super().form_valid(form)
        try:
            u = getattr(self.request, "user", None)
            if u and getattr(u, "is_authenticated", False) and getattr(u, "must_change_password", False):
                u.must_change_password = False
                u.must_change_password_cleared_at = timezone.now()
                u.save(update_fields=["must_change_password", "must_change_password_cleared_at"])
                access_logger.info("PASSWORD_CHANGE_COMPLETED user=%s", getattr(u, "id", ""))
        except Exception:
            # 사용자에게는 노출하지 않고, 서버 로그만 남기기(운영 안정성)
            access_logger.exception("PASSWORD_CHANGE_COMPLETED log failed")
        return response


@method_decorator(login_required, name="dispatch")
class UserPasswordChangeDoneView(PasswordChangeDoneView):
    """
    ✅ 비밀번호 변경 완료 페이지
    - template은 registration/password_change_done.html 사용
    """
    template_name = "registration/password_change_done.html"


# 함수형 alias (urls.py에서 직접 참조)
password_change_view = UserPasswordChangeView.as_view()
password_change_done_view = UserPasswordChangeDoneView.as_view()


# =============================================================================
# Upload Progress (Excel 업로드 진행률 / 상태 조회)
# =============================================================================
@login_required
def upload_progress_view(request: HttpRequest) -> JsonResponse:
    task_id = (request.GET.get("task_id") or "").strip()
    if not task_id:
        return JsonResponse({"percent": 0, "status": "PENDING", "error": "", "download_url": ""})

    percent = cache.get(cache_key(CACHE_PROGRESS_PREFIX, task_id), 0) or 0
    status = cache.get(cache_key(CACHE_STATUS_PREFIX, task_id), "PENDING") or "PENDING"
    error = cache.get(cache_key(CACHE_ERROR_PREFIX, task_id), "") or ""

    download_url = ""
    if status == "SUCCESS":
        # ✅ 기본은 accounts 결과 다운로드(항상 존재)
        download_url = reverse("accounts:accounts_upload_result", args=[task_id])

        # (선택) admin url이 정확히 존재하는 경우에만 덮어쓰기
        try:
            download_url = reverse("admin:upload_users_result", args=[task_id])
        except Exception:
            pass

    return JsonResponse(
        {
            "percent": int(percent),
            "status": str(status),
            "error": str(error),
            "download_url": str(download_url),
        }
    )


@login_required
def upload_result_view(request: HttpRequest, task_id: str) -> FileResponse:
    result_path = cache.get(cache_key(CACHE_RESULT_PATH_PREFIX, task_id))
    if not result_path:
        raise Http404("결과 파일을 찾을 수 없습니다.")

    p = Path(result_path)
    if not p.exists() or not p.is_file():
        raise Http404("파일을 찾을 수 없습니다.")

    return FileResponse(open(p, "rb"), as_attachment=True, filename=p.name)


# =============================================================================
# Auth (로그인 후 브라우저 종료 시 세션 만료)
# =============================================================================
@method_decorator(never_cache, name="dispatch")
@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionCloseLoginView(LoginView):
    authentication_form = ActiveOnlyAuthenticationForm

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """
        ✅ CSRF cookie not set 방지
        - ensure_csrf_cookie로 GET /login 시점에 csrftoken 강제 발급
        - never_cache + no-store 헤더로 캐시 재사용 이슈 차단
        """
        response = super().dispatch(request, *args, **kwargs)
        return _set_no_store_headers(response)


    def form_valid(self, form) -> HttpResponse:
        """
        Phase 3:
        - 로그인 성공 시점은 사용자가 입력한 원문 비밀번호를 알 수 있는 유일한 지점입니다.
        - 따라서 "기본 비번(id / incar+id) 로그인"이면 must_change_password 플래그를 True로 수렴합니다.
        """
        raw_pw = ""
        try:
            raw_pw = (form.cleaned_data.get("password") or "").strip()
        except Exception:
            raw_pw = (self.request.POST.get("password") or "").strip()

        user = None
        try:
            user = form.get_user()
        except Exception:
            user = None

        response = super().form_valid(form)
        self.request.session.set_expiry(0)

        # ✅ 로그인 성공 후에만 플래그 수렴(인증 실패 케이스 오염 방지)
        try:
            if user and getattr(user, "is_authenticated", True):
                emp_id = (getattr(user, "id", "") or "").strip()
                if emp_id:
                    default_pw_1 = emp_id
                    default_pw_2 = f"incar{emp_id}"
                    is_default = raw_pw != "" and (raw_pw == default_pw_1 or raw_pw == default_pw_2)

                    if is_default and not getattr(user, "must_change_password", False):
                        user.must_change_password = True
                        user.must_change_password_set_at = timezone.now()
                        user.save(update_fields=["must_change_password", "must_change_password_set_at"])
                        access_logger.info(
                            "PASSWORD_CHANGE_REQUIRED_SET user=%s via=login_default_pw",
                            emp_id,
                        )
        except Exception:
            access_logger.exception("PASSWORD_CHANGE_REQUIRED_SET failed")

        return response


# =============================================================================
# User Search API (SSOT 호출 wrapper)
# =============================================================================

@login_required
def api_search_user(request: HttpRequest) -> JsonResponse:
    """
    ✅ 정식 검색 구현(search_api.search_users_for_api)을 호출하는 thin wrapper
    """
    return JsonResponse(search_users_for_api(request))


# ✅ 레거시 alias (기존 /search-user/ 유지)
@login_required
def search_user(request: HttpRequest) -> JsonResponse:
    return api_search_user(request)