# django_ma/partner/views/subadmin.py
# ------------------------------------------------------------
# ✅ 중간관리자(leader) 추가/삭제 API (FINAL - FIXED)
# - 핵심:
#   1) leader 승격 시 SubAdminTemp의 team/position 절대 초기화/덮어쓰기 금지
#   2) 삭제(강등) 시에도 SubAdminTemp row 삭제 금지, level만 초기화(팀/직급 보존)
# ------------------------------------------------------------

import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from accounts.models import CustomUser
from audit.constants import ACTION
from audit.services import log_action
from partner.models import SubAdminTemp

logger = logging.getLogger(__name__)


def _to_str(v) -> str:
    return ("" if v is None else str(v)).strip()


def _same_branch(a: str, b: str) -> bool:
    return _to_str(a) and _to_str(b) and _to_str(a) == _to_str(b)


@require_POST
@login_required
@grade_required("superuser", "head")
@transaction.atomic
def ajax_add_sub_admin(request):
    """
    ✅ 중간관리자 추가(= grade를 leader로 승격)
    - SubAdminTemp가 없으면 최소필드만 생성 (team/position은 절대 건드리지 않음)
    - SubAdminTemp가 있으면 name/part/branch/grade/level만 최소 최신화 (team/position touch 금지)
    """
    user_id = _to_str(request.POST.get("user_id") or request.POST.get("id"))
    if not user_id:
        return JsonResponse({"ok": False, "error": "user_id가 없습니다."}, status=400)

    try:
        u = CustomUser.objects.select_for_update().get(id=user_id)
    except CustomUser.DoesNotExist:
        return JsonResponse({"ok": False, "error": "사용자를 찾을 수 없습니다."}, status=404)

    # head는 본인 지점만 승격 가능
    if request.user.grade == "head":
        if _to_str(u.branch) and _to_str(request.user.branch) and not _same_branch(u.branch, request.user.branch):
            return JsonResponse({"ok": False, "error": "다른 지점 사용자는 추가할 수 없습니다."}, status=403)

    if u.grade in ("resign", "inactive"):
        return JsonResponse({"ok": False, "error": "퇴사/비활성 사용자는 추가할 수 없습니다."}, status=400)

    _old_grade = u.grade
    changed = (_old_grade != "leader")
    u.grade = "leader"
    u.save(update_fields=["grade"])

    try:
        log_action(
            request,
            ACTION.PARTNER_LEADER_ADD,
            obj=u,
            meta={"from_grade": _old_grade, "to_grade": "leader"},
        )
    except Exception:
        logger.exception("audit log 기록 실패 — ajax_add_sub_admin")

    # ✅ SubAdminTemp 생성/유지: team/position defaults 금지 (초기화 방지)
    sa, created = SubAdminTemp.objects.get_or_create(
        user=u,
        defaults={
            "name": (_to_str(u.name) or "-"),
            "branch": (_to_str(u.branch) or "-"),
            "part": (_to_str(u.part) or "-"),
            "grade": "leader",
            "level": "-",
            # ⚠️ team_a/b/c, position은 절대 넣지 않음 (NULL 유지)
        },
    )

    # ✅ 이미 존재하면 team/position 건드리지 말고 메타만 최신화
    updates = {}

    if _to_str(sa.name) != (_to_str(u.name) or "-"):
        updates["name"] = _to_str(u.name) or "-"
    if _to_str(sa.branch) != (_to_str(u.branch) or "-"):
        updates["branch"] = _to_str(u.branch) or "-"
    if _to_str(sa.part) != (_to_str(u.part) or "-"):
        updates["part"] = _to_str(u.part) or "-"
    if _to_str(sa.grade) != "leader":
        updates["grade"] = "leader"

    # level이 비어있을 때만 최소 보정
    if not _to_str(getattr(sa, "level", "")):
        updates["level"] = "-"

    if updates:
        SubAdminTemp.objects.filter(pk=sa.pk).update(**updates)

    return JsonResponse(
        {
            "ok": True,
            "changed": changed,
            "created_subadmin_temp": created,
            "user": {
                "id": u.id,
                "name": u.name,
                "branch": _to_str(u.branch),
                "part": _to_str(u.part),
                "grade": u.grade,
            },
        }
    )


@require_POST
@login_required
@grade_required("superuser", "head")
@transaction.atomic
def ajax_delete_subadmin(request):
    """
    ✅ 중간관리자 삭제(= grade를 basic으로 강등)
    - CustomUser.grade만 basic으로 변경
    - SubAdminTemp는 삭제하지 않음 (팀/직급 보존)
    - level만 초기화 + 메타만 최소 동기화
    """
    user_id = _to_str(request.POST.get("user_id") or request.POST.get("id"))
    if not user_id:
        return JsonResponse({"ok": False, "error": "user_id가 필요합니다."}, status=400)

    target = get_object_or_404(CustomUser, pk=user_id)

    # head는 본인 지점만 강등 가능
    if request.user.grade == "head":
        if _to_str(target.branch) and _to_str(request.user.branch) and not _same_branch(target.branch, request.user.branch):
            return JsonResponse({"ok": False, "error": "다른 지점 사용자는 삭제할 수 없습니다."}, status=403)

    # ✅ 1) grade 변경
    _old_grade = target.grade
    target.grade = "basic"
    target.save(update_fields=["grade"])

    try:
        log_action(
            request,
            ACTION.PARTNER_LEADER_DELETE,
            obj=target,
            meta={"from_grade": _old_grade, "to_grade": target.grade},
        )
    except Exception:
        logger.exception("audit log 기록 실패 — ajax_delete_subadmin")

    # ✅ 2) SubAdminTemp는 유지(팀/직급 보존), level만 초기화
    sa_qs = SubAdminTemp.objects.select_for_update().filter(user=target)
    if sa_qs.exists():
        sa_qs.update(
            grade="basic",
            level="-",
            name=_to_str(target.name) or "-",
            part=_to_str(target.part) or "-",
            branch=_to_str(target.branch) or "-",
        )

    return JsonResponse({"ok": True})
