# django_ma/board/views/forms.py
# =========================================================
# Form / PDF / Search Views
# - support_form / states_form
# - search_user
# - generate_request_support / generate_request_states
# =========================================================

from __future__ import annotations

from typing import Any, Dict, List
import logging

from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from accounts.decorators import grade_required
from accounts.search_api import search_users_for_api

from audit.services import log_action
from audit.constants import ACTION

from ..constants import (
    BOARD_ALLOWED_GRADES,
    SUPPORT_FORM, STATES_FORM,
    SUPPORT_TARGET_FIELDS, SUPPORT_CONTRACT_FIELDS,
)
from ..policies import can_access_states_form, can_access_support_form
from board.utils import generate_request_support as build_support
from board.utils import generate_request_states as build_states


__all__ = [
    "support_form",
    "states_form",
    "generate_request_support",
    "generate_request_states",
    "search_user",
]


logger = logging.getLogger(__name__)


def _safe_action(name: str, default: str) -> str:
    return getattr(ACTION, name, default)


def _is_ajax_request(request: HttpRequest) -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _json_err(message: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "message": message}, status=status)


def _deny_form_access(request: HttpRequest, *, ajax_message: str, html_message: str, redirect_to: str, status: int = 403) -> HttpResponse:
    if _is_ajax_request(request):
        return _json_err(ajax_message, status=status)
    messages.error(request, html_message)
    return redirect(redirect_to)


def _count_non_empty_contract_rows(rows: List[Dict[str, Any]]) -> int:
    count = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if any(str(v or "").strip() for v in row.values()):
            count += 1
    return count


def _pdf_meta(request: HttpRequest) -> Dict[str, Any]:
    contracts = request.POST.getlist("contract")
    return {
        "path": request.path,
        "method": request.method,
        "target_name": (request.POST.get("name") or "").strip(),
        "target_emp_id": (request.POST.get("emp_id") or "").strip(),
        "contract_rows": len(contracts),
    }


def _log_pdf_action(request: HttpRequest, *, action_name: str, success: bool, reason: str = "") -> None:
    try:
        log_action(
            request,
            action_name,
            object_type="board_pdf",
            object_id=(request.POST.get("emp_id") or request.user.pk or ""),
            meta=_pdf_meta(request),
            success=success,
            reason=reason or "",
        )
    except Exception:
        logger.exception("board PDF audit logging failed")


# ---------------------------------------------------------
# ✅ SSOT: support/states form context
# ---------------------------------------------------------
def build_support_form_context() -> Dict[str, Any]:
    """
    support_form / states_form 공용 컨텍스트(SSOT)
    - templates expected: fields, contracts
    """
    return {
        "fields": SUPPORT_TARGET_FIELDS,
        "contracts": SUPPORT_CONTRACT_FIELDS,
        # ✅ 템플릿에서 "not in 문자열" 오용 방지용
        #    (support_form에서 권한 안내/방어적 표기)
        "grades_allowed": list(BOARD_ALLOWED_GRADES),
    }


# ---------------------------------------------------------
# ✅ Support / States Form
# ---------------------------------------------------------
@login_required
@grade_required(*BOARD_ALLOWED_GRADES)
def support_form(request: HttpRequest) -> HttpResponse:
    """업무요청서 작성 페이지 (superuser/head/leader)"""
    if not can_access_support_form(request.user):
        messages.error(request, "접근 권한이 없습니다.")
        return redirect("home")
    return render(request, "board/support_form.html", build_support_form_context())


@login_required
def states_form(request: HttpRequest) -> HttpResponse:
    """FA소명서 작성 페이지 (inactive 외 모두)"""
    if not can_access_states_form(request.user):
        return _deny_form_access(
            request,
            ajax_message="접근 권한이 없습니다.",
            html_message="접근 권한이 없습니다.",
            redirect_to="home",
            status=403,
        )
    return render(request, "board/states_form.html", build_support_form_context())


# ---------------------------------------------------------
# ✅ Search User (Legacy alias 유지)
# ---------------------------------------------------------
@login_required
@grade_required(*BOARD_ALLOWED_GRADES)
def search_user(request: HttpRequest) -> JsonResponse:
    """
    Legacy alias: /board/search-user/
    실제 구현은 accounts.search_api.search_users_for_api(SSOT)
    """
    return JsonResponse(search_users_for_api(request))


# ---------------------------------------------------------
# ✅ PDF Generate
# ---------------------------------------------------------
@login_required
@grade_required(*BOARD_ALLOWED_GRADES)
def generate_request_support(request: HttpRequest) -> HttpResponse:
    """업무요청서 PDF (superuser/head/leader)"""
    if not can_access_support_form(request.user):
        _log_pdf_action(
            request,
            action_name=_safe_action("BOARD_SUPPORT_PDF_GENERATE", "board_support_pdf_generate"),
            success=False,
            reason="permission_denied",
        )
        return _deny_form_access(
            request,
            ajax_message="접근 권한이 없습니다.",
            html_message="접근 권한이 없습니다.",
            redirect_to="home",
            status=403,
        )

    pdf_response = build_support(request)
    if pdf_response is None:
        _log_pdf_action(
            request,
            action_name=_safe_action("BOARD_SUPPORT_PDF_GENERATE", "board_support_pdf_generate"),
            success=False,
            reason="pdf_build_failed",
        )
        if _is_ajax_request(request):
            return _json_err("PDF 생성 중 오류가 발생했습니다.", status=400)
        messages.error(request, "PDF 생성 중 오류가 발생했습니다.")
        return redirect(SUPPORT_FORM)

    _log_pdf_action(
        request,
        action_name=_safe_action("BOARD_SUPPORT_PDF_GENERATE", "board_support_pdf_generate"),
        success=True,
    )
    return pdf_response


@login_required
@require_POST
def generate_request_states(request: HttpRequest) -> HttpResponse:
    """FA소명서 PDF (inactive 외 모두)"""
    if not can_access_states_form(request.user):
        _log_pdf_action(
            request,
            action_name=_safe_action("BOARD_STATES_PDF_GENERATE", "board_states_pdf_generate"),
            success=False,
            reason="permission_denied",
        )
        return _deny_form_access(request, ajax_message="접근 권한이 없습니다.", html_message="접근 권한이 없습니다.", redirect_to="home", status=403)


    pdf_response = build_states(request)
    if pdf_response is None:
        _log_pdf_action(
            request,
            action_name=_safe_action("BOARD_STATES_PDF_GENERATE", "board_states_pdf_generate"),
            success=False,
            reason="pdf_build_failed",
        )
        if _is_ajax_request(request):
            return _json_err("PDF 생성 중 오류가 발생했습니다.", status=400)
        messages.error(request, "PDF 생성 중 오류가 발생했습니다.")
        return redirect(STATES_FORM)
    
    _log_pdf_action(
        request,
        action_name=_safe_action("BOARD_STATES_PDF_GENERATE", "board_states_pdf_generate"),
        success=True,
    )
    return pdf_response
