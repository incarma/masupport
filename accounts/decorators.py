# django_ma/accounts/decorators.py
from __future__ import annotations

from functools import wraps
from typing import Iterable, Set

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import render


# =============================================================================
# Grade-based Permission Decorators
# =============================================================================

# main_admin/sub_admin은 legacy grade로 전환 완료 대상.
# 신규 권한 판정은 head/leader만 사용한다.
GRADE_ALIAS_MAP = {}


def _expand_allowed_grades(allowed: Iterable[str]) -> Set[str]:
    expanded: Set[str] = set()
    for g in allowed:
        expanded |= GRADE_ALIAS_MAP.get(g, {g})
    return expanded


def grade_required(*allowed_grades: str, forbidden_template: str = "no_permission_popup.html"):
    """
    등급(grade) 기반 접근 제어 데코레이터.

    사용 예)
      @grade_required("head")          -> head 허용
      @grade_required("leader")        -> leader 허용
      @grade_required("superuser")     -> superuser만
      @grade_required("head", "leader")-> head + leader 허용

    forbidden_template
      - 기본: 프로젝트 UX와 맞춘 팝업 템플릿 렌더
      - None/"": API 등에서 템플릿 없이 403 반환
    """
    # grade_required(["superuser", "main_admin"]) 형태도 지원
    if len(allowed_grades) == 1 and isinstance(allowed_grades[0], (list, tuple, set)):
        allowed_grades = tuple(allowed_grades[0])

    allowed_set = _expand_allowed_grades(allowed_grades)

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            user_grade = getattr(request.user, "grade", None)

            if user_grade not in allowed_set:
                if forbidden_template:
                    return render(request, forbidden_template)
                return HttpResponseForbidden("권한이 없습니다.")

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def not_inactive_required(view_func):
    """
    grade == 'inactive' 사용자는 접근 차단 (템플릿 팝업 방식)
    """
    @login_required
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if getattr(request.user, "grade", None) == "inactive":
            return render(request, "no_permission_popup.html")
        return view_func(request, *args, **kwargs)

    return _wrapped
