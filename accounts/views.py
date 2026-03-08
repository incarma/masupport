# django_ma/accounts/views.py
from __future__ import annotations
from pathlib import Path
from typing import Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordChangeDoneView,
)
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse, FileResponse, Http404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from django.forms.forms import NON_FIELD_ERRORS

from .constants import (
    CACHE_ERROR_PREFIX,
    CACHE_PROGRESS_PREFIX,
    CACHE_RESULT_PATH_PREFIX,
    CACHE_STATUS_PREFIX,
    cache_key,
    LOGIN_FAIL_MAX_COUNT,
    LOCK_REASON_LOGIN_FAIL_MAX,
    INVALID_LOGIN_MESSAGE_HEAD,
    INVALID_LOGIN_MESSAGE_PROGRESS_TEMPLATE,
    ACCOUNT_LOCKED_MESSAGE,
)
from .forms import ActiveOnlyAuthenticationForm, StrictPasswordChangeForm
from .search_api import search_users_for_api

import logging
from django.http import HttpResponseForbidden

from audit.constants import ACTION
from audit.services import log_action

logger = logging.getLogger("django.security.csrf")
access_logger = logging.getLogger("accounts.access")
UserModel = get_user_model()

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
                try:
                    log_action(
                        self.request,
                        ACTION.ACCOUNTS_PASSWORD_CHANGE_COMPLETED,
                        obj=u,
                        meta={"user_id": getattr(u, "id", "")},
                        success=True,
                    )
                except Exception:
                    # audit 실패가 비밀번호 변경 완료를 막으면 안 됨
                    access_logger.exception("PASSWORD_CHANGE_COMPLETED audit failed")

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
    
    def get_success_url(self) -> str:
        """
        로그인 성공 후 최초 랜딩페이지를 업계정보로 통일합니다.
        - settings.LOGIN_REDIRECT_URL도 동일하게 support:industry_info로 맞추지만,
          실제 로그인 흐름의 SSOT는 여기로 두어 의도를 분명히 합니다.
        - ForcePasswordChangeMiddleware는 인증 이후 별도 정책으로 동작하므로,
          강제 비밀번호 변경 대상자는 미들웨어가 우선 처리합니다.
        """
        return reverse("support:industry_info")
    
    
    # -------------------------------------------------------------------------
    # Internal helpers (Lockout)
    # -------------------------------------------------------------------------
    def _extract_login_id(self) -> str:
        """
        Django AuthenticationForm의 기본 필드명(username) + 방어적 fallback(id)
        """
        return (self.request.POST.get("username") or self.request.POST.get("id") or "").strip()

    def _get_submitted_user(self):
        login_id = self._extract_login_id()
        if not login_id:
            return None
        return UserModel.objects.filter(pk=login_id).first()
    
    def _build_invalid_login_message(self, count: int) -> str:
        """
        일반 로그인 실패 메시지:
        - 1~4회 실패 시 (N/5) 진행 상태를 안내
        """
        safe_count = max(1, min(int(count or 0), LOGIN_FAIL_MAX_COUNT - 1))
        return (
            f"{INVALID_LOGIN_MESSAGE_HEAD}\n"
            f"{INVALID_LOGIN_MESSAGE_PROGRESS_TEMPLATE.format(count=safe_count, max_count=LOGIN_FAIL_MAX_COUNT)}"
        )

    def _build_locked_message(self) -> str:
        return ACCOUNT_LOCKED_MESSAGE

    def _replace_non_field_error(self, form, message: str, code: str) -> None:
        # 기존 invalid_login 메시지와 중복되지 않도록 non-field error 교체
        try:
            _ = form.errors
        except Exception:
            pass
        try:
            form._errors.pop(NON_FIELD_ERRORS, None)
        except Exception:
            pass
        form.add_error(None, ValidationError(message, code=code))

    def _audit_safe(self, request, action: str, **kwargs) -> None:
        try:
            log_action(request, action, **kwargs)
        except Exception:
            access_logger.exception("AUDIT_LOG_ACTION_FAILED action=%s", action)

    def _mark_login_failed(self, user):
        """
        잘못된 비밀번호로 인증 실패한 경우에만 연속 실패 횟수 누적.
        select_for_update()로 동시 로그인 시도 경쟁 조건을 완화한다.
        """
        with transaction.atomic():
            locked_user = UserModel.objects.select_for_update().get(pk=user.pk)
            now = timezone.now()
            became_locked = False

            if locked_user.is_locked:
                return locked_user, False

            locked_user.login_fail_count = int(getattr(locked_user, "login_fail_count", 0) or 0) + 1
            locked_user.last_login_fail_at = now

            update_fields = ["login_fail_count", "last_login_fail_at"]
            if locked_user.login_fail_count >= LOGIN_FAIL_MAX_COUNT:
                locked_user.login_fail_count = LOGIN_FAIL_MAX_COUNT
                locked_user.is_locked = True
                locked_user.locked_at = now
                locked_user.lock_reason = LOCK_REASON_LOGIN_FAIL_MAX
                update_fields.extend(["is_locked", "locked_at", "lock_reason"])
                became_locked = True

            locked_user.save(update_fields=list(dict.fromkeys(update_fields)))
            return locked_user, became_locked

    def _reset_login_fail_state(self, user) -> None:
        with transaction.atomic():
            target = UserModel.objects.select_for_update().get(pk=user.pk)
            update_fields = []

            if int(getattr(target, "login_fail_count", 0) or 0) != 0:
                target.login_fail_count = 0
                update_fields.append("login_fail_count")

            # 잠겨 있지 않은 정상 로그인 사용자에 대해서만 보조 필드를 정리
            if not getattr(target, "is_locked", False):
                if getattr(target, "lock_reason", ""):
                    target.lock_reason = ""
                    update_fields.append("lock_reason")

            if update_fields:
                target.save(update_fields=update_fields)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """
        잠긴 계정은 비밀번호가 맞더라도 로그인 시도 자체를 막는다.
        - form_invalid 경로로 내려 보내 잠금 메시지를 동일하게 렌더
        """
        submitted_user = self._get_submitted_user()
        if submitted_user and getattr(submitted_user, "is_locked", False):
            form = self.get_form()
            self._replace_non_field_error(form, self._build_locked_message(), "locked")
            self._audit_safe(
                request,
                ACTION.AUTH_LOGIN_BLOCKED_LOCKED,
                obj=submitted_user,
                meta={
                    "user_id": getattr(submitted_user, "id", ""),
                    "login_fail_count": int(getattr(submitted_user, "login_fail_count", 0) or 0),
                    "lock_reason": getattr(submitted_user, "lock_reason", ""),
                },
                success=False,
                reason="locked_account",
            )
            return self.form_invalid(form)

        return super().post(request, *args, **kwargs)

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

        # ✅ 성공 로그인 시 연속 실패 횟수 초기화
        try:
            if user and getattr(user, "is_authenticated", True):
                self._reset_login_fail_state(user)
        except Exception:
            access_logger.exception("LOGIN_FAIL_COUNTER_RESET failed user=%s", getattr(user, "id", ""))

        try:
            if user:
                self._audit_safe(self.request, ACTION.AUTH_LOGIN_SUCCESS, obj=user, success=True)
        except Exception:
            access_logger.exception("AUTH_LOGIN_SUCCESS audit failed")

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
    
    def form_invalid(self, form) -> HttpResponse:
        """
        잘못된 비밀번호로 인한 invalid_login만 연속 실패 횟수에 반영한다.
        inactive / locked / 기타 폼 에러는 누적하지 않는다.
        """
        submitted_user = self._get_submitted_user()

        try:
            error_data = form.errors.as_data().get(NON_FIELD_ERRORS, [])
            error_codes = {getattr(err, "code", "") for err in error_data}
        except Exception:
            error_codes = set()

        if submitted_user and "invalid_login" in error_codes and not getattr(submitted_user, "is_locked", False):
            try:
                updated_user, became_locked = self._mark_login_failed(submitted_user)

                self._audit_safe(
                    self.request,
                    ACTION.AUTH_LOGIN_FAIL,
                    obj=updated_user,
                    meta={
                        "user_id": getattr(updated_user, "id", ""),
                        "login_fail_count": int(getattr(updated_user, "login_fail_count", 0) or 0),
                    },
                    success=False,
                    reason="invalid_login",
                )

                if became_locked:
                    self._replace_non_field_error(form, self._build_locked_message(), "locked")
                    self._audit_safe(
                        self.request,
                        ACTION.AUTH_LOGIN_LOCKED,
                        obj=updated_user,
                        meta={
                            "user_id": getattr(updated_user, "id", ""),
                            "login_fail_count": int(getattr(updated_user, "login_fail_count", 0) or 0),
                            "lock_reason": getattr(updated_user, "lock_reason", ""),
                        },
                        success=False,
                        reason="login_fail_limit_reached",
                    )
                else:
                    self._replace_non_field_error(
                        form,
                        self._build_invalid_login_message(updated_user.login_fail_count),
                        "invalid_login",
                    )
            except Exception:
                access_logger.exception("AUTH_LOGIN_FAIL handling failed user=%s", getattr(submitted_user, "id", ""))

        return super().form_invalid(form)


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