# partner/views/structure.py
# ------------------------------------------------------------
# ✅ Structure(편제변경) API
# - core: ajax_save / ajax_delete / ajax_fetch
# - 신규 네이밍: structure_save / structure_delete / structure_fetch
# - legacy alias 유지 (기존 URL/호출부 영향 없음)
# ------------------------------------------------------------

import traceback

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import grade_required
from accounts.models import CustomUser
from partner.models import PartnerChangeLog, StructureChange

from .responses import json_err, json_ok, parse_json_body
from .utils import (
    build_affiliation_display,
    get_level_team_filter_user_ids,
    normalize_month,
    resolve_branch_for_query,
    resolve_branch_for_write,
    resolve_part_for_write,
)

# ------------------------------------------------------------
# Constants
# ------------------------------------------------------------
ALLOWED_GRADES = ("superuser", "head", "leader")
DELETE_PRIVILEGED_GRADES = ("superuser", "head")


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _safe_str(v) -> str:
    return str(v or "").strip()


def _to_date_str(dt) -> str:
    """datetime/date → 'YYYY-MM-DD' (없으면 '')"""
    if not dt:
        return ""
    try:
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _serialize_structure_change(sc: StructureChange) -> dict:
    """StructureChange → API row dict (기존 키 유지)"""
    requester = getattr(sc, "requester", None)
    target = getattr(sc, "target", None)

    return {
        "id": sc.id,
        "requester_id": getattr(requester, "id", "") if requester else "",
        "requester_name": getattr(requester, "name", "") if requester else "",
        "requester_branch": build_affiliation_display(requester) if requester else "",
        "target_id": getattr(target, "id", "") if target else "",
        "target_name": getattr(target, "name", "") if target else "",
        "target_branch": sc.target_branch or "",
        "chg_branch": sc.chg_branch or "",
        "rank": sc.rank or "",
        "chg_rank": sc.chg_rank or "",
        "or_flag": bool(sc.or_flag),
        "memo": sc.memo or "",
        "request_date": _to_date_str(getattr(sc, "created_at", None)),
        "process_date": _to_date_str(getattr(sc, "process_date", None)),
    }


def _can_delete_record(user, record: StructureChange) -> bool:
    """
    ✅ 삭제 권한 규칙 (기존 로직 그대로)
    - superuser/head는 삭제 가능
    - leader는 자신이 요청한 건만 삭제 가능
    """
    if getattr(user, "grade", None) in DELETE_PRIVILEGED_GRADES:
        return True
    return _safe_str(getattr(record, "requester_id", "")) == _safe_str(getattr(user, "id", ""))


def _build_leader_scope_q(user) -> Q:
    """
    ✅ leader 권한 스코프(기존 유지)
    - 본인 요청 + 팀 스코프(requester_id in allowed_ids)
    """
    allowed_ids = get_level_team_filter_user_ids(user)
    team_q = Q(requester_id__in=allowed_ids) if allowed_ids else Q()
    return Q(requester_id=user.id) | team_q


def _can_use_target(user, target: CustomUser, branch: str) -> bool:
    grade = getattr(user, "grade", "")
    target_branch = _safe_str(getattr(target, "branch", ""))

    if grade == "superuser":
        return True

    if target_branch != _safe_str(branch):
        return False

    if grade == "head":
        return target_branch == _safe_str(getattr(user, "branch", ""))

    if grade == "leader":
        allowed_ids = set(str(x) for x in get_level_team_filter_user_ids(user))
        return str(target.id) == str(user.id) or str(target.id) in allowed_ids

    return False


# ------------------------------------------------------------
# Core APIs (legacy endpoints)
# ------------------------------------------------------------
@require_POST
@login_required
@grade_required(*ALLOWED_GRADES)
@transaction.atomic
def ajax_save(request):
    """✅ Structure 저장 (rows 리스트를 받아 StructureChange 생성)"""
    try:
        payload = parse_json_body(request)

        items = payload.get("rows", [])
        month = normalize_month(payload.get("month") or "")

        user = request.user
        part = resolve_part_for_write(user, payload.get("part") or "")
        branch = resolve_branch_for_write(user, payload.get("branch") or "")

        created_count = 0

        for row in items:
            target_id = _safe_str(row.get("target_id"))
            if not target_id:
                continue

            target = CustomUser.objects.filter(id=target_id).first()
            if not target:
                continue
            if not _can_use_target(user, target, branch):
                return json_err("권한 범위 밖의 대상자가 포함되어 있습니다.", status=403)

            StructureChange.objects.create(
                requester=user,
                target=target,
                part=part,
                branch=branch,
                month=month,
                # target snapshot
                target_branch=build_affiliation_display(target),
                # change payload
                chg_branch=_safe_str(row.get("chg_branch") or "-") or "-",
                or_flag=bool(row.get("or_flag", False)),
                rank=_safe_str(row.get("tg_rank") or row.get("rank") or "-") or "-",
                chg_rank=_safe_str(row.get("chg_rank") or "-") or "-",
                memo=_safe_str(row.get("memo")),
            )
            created_count += 1

        PartnerChangeLog.objects.create(
            user=user,
            action="save",
            detail=f"{created_count}건 저장 (structure / 월:{month} / 부서:{part} / 지점:{branch})",
        )

        return json_ok({"saved_count": created_count})
    except Exception as e:
        traceback.print_exc()
        return json_err(str(e), status=400)


@require_POST
@login_required
@grade_required(*ALLOWED_GRADES)
@transaction.atomic
def ajax_delete(request):
    """✅ Structure 단건 삭제"""
    try:
        data = parse_json_body(request)
        record_id = data.get("id")

        if not record_id:
            return json_err("id 누락", status=400)

        record = get_object_or_404(StructureChange, id=record_id)
        user = request.user

        if not _can_delete_record(user, record):
            return json_err("삭제 권한이 없습니다.", status=403)

        deleted_id = record.id
        record.delete()

        PartnerChangeLog.objects.create(
            user=user,
            action="delete",
            detail=f"StructureChange #{deleted_id} 삭제",
        )
        return json_ok({"message": f"#{deleted_id} 삭제 완료"})
    except Exception as e:
        traceback.print_exc()
        return json_err(str(e), status=500)


@require_GET
@login_required
@grade_required(*ALLOWED_GRADES)
def ajax_fetch(request):
    """✅ Structure 조회 (권한 스코프 동일 유지)"""
    try:
        user = request.user

        month = normalize_month(request.GET.get("month") or "")
        branch_param = _safe_str(request.GET.get("branch"))
        branch = resolve_branch_for_query(user, branch_param)

        qs = (
            StructureChange.objects.filter(month=month)
            .select_related("requester", "target")
        )

        # ✅ superuser는 branch 파라미터 있으면 그 branch만, 없으면 전체
        # ✅ 그 외 등급은 자신의 branch로 고정
        if user.grade == "superuser":
            if branch:
                qs = qs.filter(branch__iexact=branch)
        else:
            qs = qs.filter(branch__iexact=branch)

        # ✅ leader는 본인 요청 + 팀 스코프
        if user.grade == "leader":
            qs = qs.filter(_build_leader_scope_q(user))

        rows = [_serialize_structure_change(sc) for sc in qs.order_by("-id")]

        return json_ok({"kind": "structure", "rows": rows})
    except Exception as e:
        traceback.print_exc()
        return json_err(str(e), status=500, extra={"rows": []})


# ------------------------------------------------------------
# ✅ 신규 API 이름 + Legacy alias (기능 동일)
# ------------------------------------------------------------
@require_GET
@login_required
@grade_required(*ALLOWED_GRADES)
def structure_fetch(request):
    return ajax_fetch(request)


@require_POST
@login_required
@grade_required(*ALLOWED_GRADES)
@transaction.atomic
def structure_save(request):
    return ajax_save(request)


@require_POST
@login_required
@grade_required(*ALLOWED_GRADES)
@transaction.atomic
def structure_delete(request):
    return ajax_delete(request)
