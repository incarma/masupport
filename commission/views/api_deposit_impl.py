# django_ma/commission/views/api_deposit_impl.py
from __future__ import annotations

import logging
from typing import Optional, Tuple

from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts.models import CustomUser
from commission.services.deposit import (
    get_deposit_other_queryset,
    get_deposit_summary,
    get_deposit_surety_queryset,
)
from commission.services.deposit_serializers import (
    apply_deposit_summary_totals,
    json_rows,
    json_user_detail,
    other_to_payload,
    summary_to_payload,
    surety_to_payload,
    to_str,
    user_to_payload,
)
from commission.views.utils_json import _json_error

logger = logging.getLogger(__name__)


# =============================================================================
# 1) Request → target user resolver
# =============================================================================


def _get_user_id_from_request(request) -> str:
    """레거시/호환을 위해 다양한 키를 허용."""
    return to_str(
        request.GET.get("user")
        or request.GET.get("id")
        or request.GET.get("emp_id")
        or request.GET.get("employee_id")
        or request.GET.get("regist")
        or request.GET.get("username")
        or ""
    )


def _find_user_by_any_id(user_id: str) -> Optional[CustomUser]:
    """
    - 기본은 CustomUser.pk(id=사번)
    - 레거시 필드(emp_id/regist/username)도 방어적으로 탐색
    - 조회 필드는 only()로 최소화(성능/보안)
    """
    user_id = to_str(user_id)
    if not user_id:
        return None

    base = CustomUser.objects.only(
        "id",
        "name",
        "part",
        "branch",
        "enter",
        "quit",
        "regist",
        "grade",
    )

    # 1) pk/id
    u = base.filter(Q(pk=user_id) | Q(id=user_id)).first()
    if u:
        return u

    # 2) optional legacy ids
    if hasattr(CustomUser, "emp_id"):
        u = base.filter(emp_id=user_id).first()
        if u:
            return u

    u = base.filter(regist=user_id).first()
    if u:
        return u

    if hasattr(CustomUser, "username"):
        u = base.filter(username=user_id).first()
        if u:
            return u

    return None


# =============================================================================
# 2) Permission
# =============================================================================


def _can_view_target(request, target: CustomUser) -> bool:
    """Deposit(채권현황)은 개인정보/정산정보 성격 → 열람 권한 제한."""
    u = getattr(request, "user", None)
    if not u or not u.is_authenticated:
        return False

    grade = getattr(u, "grade", "")
    if grade in ("superuser", "main_admin", "head"):
        return True

    # 본인만
    return str(u.pk) == str(target.pk)


def _require_view_permission(request, target: CustomUser) -> Optional[JsonResponse]:
    if _can_view_target(request, target):
        return None
    return _json_error("권한이 없습니다.", status=403)


def _resolve_target_or_err(request) -> Tuple[Optional[CustomUser], Optional[JsonResponse], str]:
    """
    공통 흐름:
      1) user 파라미터 파싱
      2) 대상자 조회
      3) 권한 체크(403)
    """
    user_id = _get_user_id_from_request(request)
    if not user_id:
        return None, _json_error("user 파라미터가 필요합니다."), ""

    target = _find_user_by_any_id(user_id)
    if not target:
        return None, _json_error("대상자를 찾지 못했습니다.", status=404), user_id

    perm = _require_view_permission(request, target)
    if perm:
        return None, perm, user_id

    return target, None, user_id


def _resolve_target_or_empty_rows(
    request,
) -> Tuple[Optional[CustomUser], Optional[JsonResponse]]:
    """
    Deposit rows API 공통 대상자 해석.

    기존 동작 유지:
    - user 파라미터 없음: 400 JSON error
    - 대상자 없음: ok=True, rows=[]
    - 권한 없음: 403 JSON error
    """
    user_id = _get_user_id_from_request(request)
    if not user_id:
        return None, _json_error("user 파라미터가 필요합니다.")

    target = _find_user_by_any_id(user_id)
    if not target:
        return None, json_rows([])

    perm = _require_view_permission(request, target)
    if perm:
        return None, perm

    return target, None


# =============================================================================
# 3) APIs
# =============================================================================

@require_GET
def api_user_detail(request):
    target, err, _ = _resolve_target_or_err(request)
    if err:
        return err

    payload = user_to_payload(target)
    # legacy: data + user 둘 다 내려줌(기존 유지)
    return json_user_detail(payload)


@require_GET
def api_deposit_summary(request):
    target, err = _resolve_target_or_empty_rows(request)
    if err:
        return err

    s = get_deposit_summary(target.pk)
    if not s:
        return json_rows([])

    payload = summary_to_payload(s)
    payload = apply_deposit_summary_totals(payload, target.pk)

    return json_rows([payload])


@require_GET
def api_deposit_surety_list(request):
    target, err = _resolve_target_or_empty_rows(request)
    if err:
        return err

    qs = get_deposit_surety_queryset(target.pk)
    return json_rows([surety_to_payload(x) for x in qs])


@require_GET
def api_deposit_other_list(request):
    target, err = _resolve_target_or_empty_rows(request)
    if err:
        return err

    qs = get_deposit_other_queryset(target.pk)
    return json_rows([other_to_payload(x) for x in qs])