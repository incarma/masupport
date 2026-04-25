# django_ma/accounts/policies/password_policy.py
from __future__ import annotations

"""
Phase 3 (Force Password Change) - Policy Engine (SSOT)

핵심 목표:
- 미들웨어는 '강제 대상인지'만 판단해야 하고, 그 판단 기준은 should_enforce()로 단일화합니다.
- 기본 비밀번호(id / incar+id) 여부는 미들웨어에서 판별하지 않습니다.
  (원문 비밀번호를 알 수 없으므로) → 로그인 성공 훅에서 must_change_password 플래그로 수렴합니다.

정책 설계 원칙:
- 전역 토글(FORCE_PASSWORD_CHANGE_ENABLED)로 즉시 롤백 가능
- deny-first + 우선순위 고정(branch > part > channel)
- grade 예외(superuser/head 기본 제외)로 운영 사고 방지
- 현재는 settings 기반 스코프를 SSOT로 사용하되,
  향후 DB 기반 Scope 모델이 생기면 "optional"로 자동 확장 가능하도록 설계합니다.
"""

from dataclasses import dataclass
from typing import Optional

from django.apps import apps
from django.conf import settings


# -----------------------------------------------------------------------------
# 내부 데이터 모델(옵션): DB Scope가 존재할 경우 사용
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class ScopeDecision:
    allow: bool
    deny: bool


def _get_user_grade(user) -> str:
    return (getattr(user, "grade", "") or "").strip()


def _get_org(user, key: str) -> str:
    return (getattr(user, key, "") or "").strip()


def _set_from_settings(name: str) -> set[str]:
    v = getattr(settings, name, None)
    if isinstance(v, set):
        return v
    if isinstance(v, (list, tuple)):
        return {str(x).strip() for x in v if str(x).strip()}
    return set()


def _decide_with_settings(user) -> ScopeDecision:
    """
    settings 기반 스코프 판정 (deny-first)
    - allow 세트가 모두 비어있으면 "스코프 미설정"으로 보고 allow=False 처리(=점진 적용 안전)
    """
    b = _get_org(user, "branch")
    p = _get_org(user, "part")
    c = _get_org(user, "channel")

    deny_b = _set_from_settings("FORCE_PASSWORD_CHANGE_DENY_BRANCHES")
    deny_p = _set_from_settings("FORCE_PASSWORD_CHANGE_DENY_PARTS")
    deny_c = _set_from_settings("FORCE_PASSWORD_CHANGE_DENY_CHANNELS")

    if (b and b in deny_b) or (p and p in deny_p) or (c and c in deny_c):
        return ScopeDecision(allow=False, deny=True)

    allow_b = _set_from_settings("FORCE_PASSWORD_CHANGE_SCOPE_BRANCHES")
    allow_p = _set_from_settings("FORCE_PASSWORD_CHANGE_SCOPE_PARTS")
    allow_c = _set_from_settings("FORCE_PASSWORD_CHANGE_SCOPE_CHANNELS")

    # 우선순위: branch > part > channel
    if b and b in allow_b:
        return ScopeDecision(allow=True, deny=False)
    if p and p in allow_p:
        return ScopeDecision(allow=True, deny=False)
    if c and c in allow_c:
        return ScopeDecision(allow=True, deny=False)

    # allow 리스트가 전부 비어있으면 "아직 점진 적용 전"으로 보고 allow=False(안전)
    if not allow_b and not allow_p and not allow_c:
        return ScopeDecision(allow=False, deny=False)

    return ScopeDecision(allow=False, deny=False)


def _decide_with_db(user) -> Optional[ScopeDecision]:
    """
    (옵션) DB 기반 스코프가 존재하면 사용.
    - 이 함수는 "모델이 없으면 None"을 반환하여 settings 방식으로 자연스럽게 폴백합니다.

    기대 모델(향후):
    - PasswordPolicyScope 같은 이름의 모델이 accounts 앱에 존재
    - 필드 예시: scope_type(branch/part/channel), scope_key, is_enabled, is_deny, approved_at 등

    ※ 현재 프로젝트에는 아직 해당 모델이 없을 수 있으므로, 절대 하드 의존하지 않습니다.
    """
    try:
        Model = apps.get_model("accounts", "PasswordPolicyScope")
    except Exception:
        return None

    try:
        qs = Model.objects.filter(is_enabled=True)
        # deny-first: 하나라도 deny에 걸리면 즉시 deny
        b = _get_org(user, "branch")
        p = _get_org(user, "part")
        c = _get_org(user, "channel")

        if b and qs.filter(scope_type="branch", scope_key=b, is_deny=True).exists():
            return ScopeDecision(allow=False, deny=True)
        if p and qs.filter(scope_type="part", scope_key=p, is_deny=True).exists():
            return ScopeDecision(allow=False, deny=True)
        if c and qs.filter(scope_type="channel", scope_key=c, is_deny=True).exists():
            return ScopeDecision(allow=False, deny=True)

        # allow 우선순위: branch > part > channel
        if b and qs.filter(scope_type="branch", scope_key=b, is_deny=False).exists():
            return ScopeDecision(allow=True, deny=False)
        if p and qs.filter(scope_type="part", scope_key=p, is_deny=False).exists():
            return ScopeDecision(allow=True, deny=False)
        if c and qs.filter(scope_type="channel", scope_key=c, is_deny=False).exists():
            return ScopeDecision(allow=True, deny=False)

        return ScopeDecision(allow=False, deny=False)
    except Exception:
        # DB 모델이 있어도 장애가 나면 정책 판단이 전체 장애로 이어지지 않게 폴백
        return ScopeDecision(allow=False, deny=False)


def should_enforce(user, request=None) -> bool:
    """
    최종 강제 여부 (SSOT)

    True 조건:
    - 전역 토글 ON
    - user가 인증됨
    - user.must_change_password == True
    - grade 예외가 아님
    - (DB scope 또는 settings scope)에서 allow=True AND deny=False
    """
    if not getattr(settings, "FORCE_PASSWORD_CHANGE_ENABLED", False):
        return False

    if not user or not getattr(user, "is_authenticated", False):
        return False

    if not getattr(user, "must_change_password", False):
        return False

    grade = _get_user_grade(user)
    exempt = _set_from_settings("FORCE_PASSWORD_CHANGE_EXEMPT_GRADES")
    if grade and grade in exempt:
        return False

    # 1) DB 스코프가 있으면 우선 적용(옵션)
    d = _decide_with_db(user)
    if d is None:
        # 2) settings 기반
        d = _decide_with_settings(user)

    if d.deny:
        return False
    if not d.allow:
        return False

    return True