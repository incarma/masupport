# django_ma/accounts/views.py
from __future__ import annotations
from pathlib import Path

from django.conf import settings
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
import requests as _requests
from django.http import HttpResponseForbidden

from audit.constants import ACTION
from audit.services import log_action
from audit.utils import mask_value

logger = logging.getLogger("django.security.csrf")
access_logger = logging.getLogger("accounts.access")
UserModel = get_user_model()


# =============================================================================
# reCAPTCHA v3 헬퍼 — SSOT: /login/ 전용
# =============================================================================

def _verify_recaptcha_v3(token: str, remote_ip: str = "") -> bool:
    """
    Google reCAPTCHA v3 서버사이드 검증 헬퍼.

    정책:
    - RECAPTCHA_PRIVATE_KEY 미설정 → True (dev/테스트 안전망)
    - Google 서버 오류 → True, fail-open (서비스 가용성 우선)
    - score < RECAPTCHA_SCORE_THRESHOLD → False (봇 판정)
    """
    secret = getattr(settings, "RECAPTCHA_PRIVATE_KEY", "")
    if not secret:
        return True

    try:
        resp = _requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": secret, "response": token, "remoteip": remote_ip},
            timeout=5,
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        logger.warning("[recaptcha] 검증 요청 실패(fail-open): %s", e)
        return True

    success = result.get("success", False)
    score = result.get("score", 0.0)
    threshold = getattr(settings, "RECAPTCHA_SCORE_THRESHOLD", 0.5)

    if not success:
        logger.warning("[recaptcha] 검증 실패 error-codes=%s", result.get("error-codes"))
        return False

    if score < threshold:
        logger.warning(
            "[recaptcha] score 미달 score=%.2f threshold=%.2f ip=%s",
            score, threshold, remote_ip,
        )
        return False

    return True

UPLOAD_TASK_OWNER_PREFIX = "accounts_upload_owner"


# =============================================================================
# CSRF Failure Handler
# =============================================================================

def csrf_failure(request, reason=""):
    logger.warning(
        "CSRF FAILED | reason=%s | path=%s | method=%s | host=%s | secure=%s | "
        "xf_proto=%s | xf_host=%s | referer=%s | origin=%s | cookie=%s | ua=%s",
        mask_value(reason),
        mask_value(request.path),
        request.method,
        mask_value(request.get_host()),
        request.is_secure(),
        mask_value(request.META.get("HTTP_X_FORWARDED_PROTO", "")),
        mask_value(request.META.get("HTTP_X_FORWARDED_HOST", "")),
        mask_value(request.META.get("HTTP_REFERER", "")),
        mask_value(request.META.get("HTTP_ORIGIN", "")),
        "***",
        mask_value(request.META.get("HTTP_USER_AGENT", "")),
    )
    return HttpResponseForbidden("CSRF Failed")


# =============================================================================
# Internal Helpers
# =============================================================================

def _set_no_store_headers(response: HttpResponse) -> HttpResponse:
    """로그인 페이지/CSRF 관련 페이지는 캐시되면 안 됨."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _is_ajax(request: HttpRequest) -> bool:
    """
    랜딩 모달 AJAX 요청 판별 SSOT.
    landing.js의 fetch() 호출에 'X-Requested-With: XMLHttpRequest' 헤더가 포함되어야 한다.
    """
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _task_owner_key(task_id: str) -> str:
    return cache_key(UPLOAD_TASK_OWNER_PREFIX, task_id)


def _is_upload_task_allowed(request: HttpRequest, task_id: str) -> bool:
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return False
    
    if not task_id:
        return False

    owner_id = cache.get(_task_owner_key(task_id))
    if owner_id:
        return str(owner_id) == str(getattr(user, "pk", ""))

    # 구버전 캐시에 owner가 없는 경우: superuser만 fallback 허용
    # accounts 업로드 결과는 사용자 계정/권한 정보가 포함될 수 있어 head까지 열면 안 된다.
    grade = (getattr(user, "grade", "") or "").strip()
    return bool(getattr(user, "is_superuser", False) or grade == "superuser")


def _safe_upload_result_path(raw_path: str | Path) -> Path:
    p = Path(raw_path).resolve()
    base = Path(getattr(settings, "UPLOAD_RESULT_DIR", settings.MEDIA_ROOT)).resolve()
    if base not in p.parents and p != base:
        raise Http404("파일을 찾을 수 없습니다.")
    if not p.exists() or not p.is_file():
        raise Http404("파일을 찾을 수 없습니다.")
    return p


# =============================================================================
# Password Change (로그인 사용자 비밀번호 변경)
# =============================================================================

@method_decorator(login_required, name="dispatch")
class UserPasswordChangeView(PasswordChangeView):
    """
    로그인 사용자가 직접 비밀번호를 변경할 수 있는 페이지.
    - Django 표준 PasswordChangeView 사용
    - 성공 시 done 페이지로 이동
    - template: registration/password_change_form.html
    """
    template_name = "registration/password_change_form.html"
    form_class = StrictPasswordChangeForm

    def get_success_url(self) -> str:
        return reverse("accounts:password_change_done")

    def form_valid(self, form) -> HttpResponse:
        """
        비밀번호 변경 성공 시 must_change_password 플래그를 해제한다.
        '기본 비번 여부'는 여기서 판별하지 않는다(불필요/위험).
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
            # 사용자에게는 노출하지 않고 서버 로그만 남기기(운영 안정성)
            access_logger.exception("PASSWORD_CHANGE_COMPLETED log failed")

        return response


@method_decorator(login_required, name="dispatch")
class UserPasswordChangeDoneView(PasswordChangeDoneView):
    """
    비밀번호 변경 완료 페이지.
    - template: registration/password_change_done.html
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

    if not _is_upload_task_allowed(request, task_id):
        return JsonResponse({"percent": 0, "status": "FORBIDDEN", "error": "권한이 없습니다.", "download_url": ""}, status=403)

    percent = cache.get(cache_key(CACHE_PROGRESS_PREFIX, task_id), 0) or 0
    status = cache.get(cache_key(CACHE_STATUS_PREFIX, task_id), "PENDING") or "PENDING"
    error = cache.get(cache_key(CACHE_ERROR_PREFIX, task_id), "") or ""

    download_url = ""
    if status == "SUCCESS":
        # 기본은 accounts 결과 다운로드(항상 존재)
        download_url = reverse("accounts:accounts_upload_result", args=[task_id])

        # (선택) admin url이 정확히 존재하는 경우에만 덮어쓰기
        try:
            download_url = reverse("admin:upload_users_result", args=[task_id])
        except Exception:
            access_logger.exception("ADMIN_UPLOAD_RESULT_REVERSE failed task_id=%s", task_id)

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
    if not _is_upload_task_allowed(request, task_id):
        raise Http404("결과 파일을 찾을 수 없습니다.")

    result_path = cache.get(cache_key(CACHE_RESULT_PATH_PREFIX, task_id))
    if not result_path:
        raise Http404("결과 파일을 찾을 수 없습니다.")

    p = _safe_upload_result_path(result_path)

    return FileResponse(open(p, "rb"), as_attachment=True, filename=p.name)


# =============================================================================
# Auth — SessionCloseLoginView
# 브라우저 종료 시 세션 만료 + 랜딩 모달 AJAX 로그인 지원
# =============================================================================

@method_decorator(never_cache, name="dispatch")
@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionCloseLoginView(LoginView):
    authentication_form = ActiveOnlyAuthenticationForm

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """
        CSRF cookie not set 방지:
        - ensure_csrf_cookie로 GET /login 시점에 csrftoken 강제 발급
        - never_cache + no-store 헤더로 캐시 재사용 이슈 차단
        """
        response = super().dispatch(request, *args, **kwargs)
        return _set_no_store_headers(response)

    def get_success_url(self) -> str:
        """
        로그인 성공 후 최초 랜딩페이지를 업계정보로 통일.
        - settings.LOGIN_REDIRECT_URL도 동일하게 board:industry_info로 맞추지만,
          실제 로그인 흐름의 SSOT는 여기로 두어 의도를 분명히 한다.
        - ForcePasswordChangeMiddleware는 인증 이후 별도 정책으로 동작하므로,
          강제 비밀번호 변경 대상자는 미들웨어가 우선 처리한다.
        """
        return reverse("board:industry_info")

    # -------------------------------------------------------------------------
    # Internal helpers (Lockout)
    # -------------------------------------------------------------------------

    def _extract_login_id(self) -> str:
        """Django AuthenticationForm 기본 필드명(username) + 방어적 fallback(id)."""
        return (self.request.POST.get("username") or self.request.POST.get("id") or "").strip()

    def _get_submitted_user(self):
        login_id = self._extract_login_id()
        if not login_id:
            return None
        return UserModel.objects.filter(pk=login_id).first()

    def _build_invalid_login_message(self, count: int) -> str:
        """1~4회 실패 시 (N/5) 진행 상태 안내 메시지."""
        safe_count = max(1, min(int(count or 0), LOGIN_FAIL_MAX_COUNT - 1))
        return (
            f"{INVALID_LOGIN_MESSAGE_HEAD}\n"
            f"{INVALID_LOGIN_MESSAGE_PROGRESS_TEMPLATE.format(count=safe_count, max_count=LOGIN_FAIL_MAX_COUNT)}"
        )

    def _build_locked_message(self) -> str:
        return ACCOUNT_LOCKED_MESSAGE

    def _replace_non_field_error(self, form, message: str, code: str) -> None:
        """기존 invalid_login 메시지와 중복되지 않도록 non-field error 교체."""
        try:
            _ = form.errors
        except Exception:
            access_logger.exception("FORM_ERRORS_EVALUATION failed")
        try:
            form._errors.pop(NON_FIELD_ERRORS, None)
        except Exception:
            access_logger.exception("NON_FIELD_ERRORS_POP failed")
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

    # -------------------------------------------------------------------------
    # Context
    # -------------------------------------------------------------------------

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recaptcha_site_key"] = getattr(settings, "RECAPTCHA_PUBLIC_KEY", "")
        return context

    # -------------------------------------------------------------------------
    # Request handlers
    # -------------------------------------------------------------------------

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """
        reCAPTCHA v3 검증 후 잠긴 계정 체크, 이후 기존 LoginView 흐름.
        """
        token = request.POST.get("g-recaptcha-response", "")
        remote_ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )
        if not _verify_recaptcha_v3(token, remote_ip):
            form = self.get_form()
            form.add_error(None, "자동화된 요청이 감지되었습니다. 잠시 후 다시 시도해 주세요.")
            return self.form_invalid(form)

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
        로그인 성공 경로.

        처리 순서:
        1. 원문 비밀번호 추출 (기본 비번 여부 판별용)
        2. super().form_valid() 호출 → 세션 생성 + redirect response 준비
        3. 세션 만료 정책 적용 (브라우저 종료 시 만료)
        4. 연속 실패 횟수 초기화
        5. audit 로그 기록
        6. 기본 비번 로그인 시 must_change_password 플래그 수렴
        7-a. AJAX 요청: JSON {"success": true, "next_url": ...} 반환
        7-b. 일반 form submit: 기존 redirect response 반환
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

        # super() 호출 → 세션 생성 + redirect response 객체 생성
        response = super().form_valid(form)

        # 브라우저 종료 시 세션 만료
        self.request.session.set_expiry(0)

        # 연속 실패 횟수 초기화
        try:
            if user and getattr(user, "is_authenticated", True):
                self._reset_login_fail_state(user)
        except Exception:
            access_logger.exception("LOGIN_FAIL_COUNTER_RESET failed user=%s", getattr(user, "id", ""))

        # audit 로그
        try:
            if user:
                self._audit_safe(self.request, ACTION.AUTH_LOGIN_SUCCESS, obj=user, success=True)
        except Exception:
            access_logger.exception("AUTH_LOGIN_SUCCESS audit failed")

        # 기본 비번(사번 / incar+사번) 로그인 시 must_change_password 플래그 수렴
        # 로그인 성공 후에만 수렴 (인증 실패 케이스 오염 방지)
        try:
            if user and getattr(user, "is_authenticated", True):
                emp_id = (getattr(user, "id", "") or "").strip()
                if emp_id:
                    is_default = raw_pw != "" and (
                        raw_pw == emp_id or raw_pw == f"incar{emp_id}"
                    )
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

        # ── AJAX 분기 (랜딩 모달 전용) ──────────────────────────────
        # landing.js의 fetch() 요청에는 X-Requested-With: XMLHttpRequest 헤더가 포함된다.
        # 이 헤더가 있을 때만 JSON을 반환하고, 없으면 기존 redirect response를 그대로 반환한다.
        if _is_ajax(self.request):
            return JsonResponse({
                "success": True,
                "next_url": self.get_success_url(),
            })
        # ── AJAX 분기 끝 ────────────────────────────────────────────

        return response

    def form_invalid(self, form) -> HttpResponse:
        """
        로그인 실패 경로.

        처리 순서:
        1. invalid_login 에러인 경우에만 연속 실패 횟수 누적
           (inactive / locked / 기타 폼 에러는 누적하지 않음)
        2. 잠금 임계치 도달 시 is_locked 처리 + 잠금 메시지 교체
        3. audit 로그 기록
        4-a. AJAX 요청: JSON {"success": false, "message": ...} 반환 (status 401)
        4-b. 일반 form submit: 기존 HTML 에러 페이지 반환
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
                access_logger.exception(
                    "AUTH_LOGIN_FAIL handling failed user=%s", getattr(submitted_user, "id", "")
                )

        # ── AJAX 분기 (랜딩 모달 전용) ──────────────────────────────
        # non_field_errors()의 첫 번째 메시지를 그대로 모달에 표시한다.
        # 잠금 메시지(_replace_non_field_error로 교체된 값)도 여기서 전달된다.
        if _is_ajax(self.request):
            try:
                error_list = form.non_field_errors()
                message = error_list[0] if error_list else "로그인에 실패했습니다."
            except Exception:
                message = "로그인에 실패했습니다."
            return JsonResponse({"success": False, "message": str(message)}, status=401)
        # ── AJAX 분기 끝 ────────────────────────────────────────────

        return super().form_invalid(form)


# =============================================================================
# User Search API (SSOT 호출 wrapper)
# =============================================================================

@login_required
def api_search_user(request: HttpRequest) -> JsonResponse:
    """정식 검색 구현(search_api.search_users_for_api)을 호출하는 thin wrapper."""
    return JsonResponse(search_users_for_api(request))


# 레거시 alias (기존 /search-user/ 유지)
@login_required
def search_user(request: HttpRequest) -> JsonResponse:
    return api_search_user(request)