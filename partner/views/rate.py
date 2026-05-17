# partner/views/rate.py
# ------------------------------------------------------------
# ✅ RateChange(요율변경 요청) API
# ------------------------------------------------------------

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import grade_required
from accounts.models import CustomUser
from partner.models import RateChange, RateTable, SubAdminTemp  # ✅ SubAdminTemp 추가

from audit.services import log_action
from audit.constants import ACTION

from .responses import json_err, json_ok, parse_json_body
from .utils import (
    can_use_target_in_branch,
    find_table_rate,
    get_level_team_filter_user_ids,
    team_affiliation,
    normalize_month,
    resolve_branch_for_query,
    resolve_branch_for_write,
    resolve_part_for_write,
    to_str,
)


logger = logging.getLogger(__name__)


def _to_str(v) -> str:
    # ✅ 기능 변화 0: 기존 로컬 함수명은 유지하고 공통 SSOT로 위임
    return to_str(v)


def _team_affiliation(a: str, b: str, c: str) -> str:
    # ✅ 기능 변화 0: 기존 표시 규칙("-", 빈값 제외)을 공통화
    return team_affiliation(a, b, c)


def _can_use_target(user, target: CustomUser, branch: str) -> bool:
    # ✅ 기능 변화 0: manage-rate 저장 대상자 branch 검증을 공통 SSOT로 위임
    return can_use_target_in_branch(user, target, branch)


@require_GET
@login_required
@grade_required("superuser", "head", "leader")
def rate_fetch(request):
    """✅ RateChange 조회"""
    user = request.user
    month = normalize_month(request.GET.get("month") or "")
    branch_param = _to_str(request.GET.get("branch") or "")
    branch = resolve_branch_for_query(user, branch_param)

    qs = RateChange.objects.filter(month=month).select_related("requester", "target")

    if user.grade == "superuser":
        if branch:
            qs = qs.filter(branch__iexact=branch)
    else:
        qs = qs.filter(branch__iexact=branch)

    if user.grade == "leader":
        allowed_ids = get_level_team_filter_user_ids(user)
        team_q = Q(requester_id__in=allowed_ids) if allowed_ids else Q()
        qs = qs.filter(Q(requester_id=user.id) | team_q)

    qs = qs.order_by("-id")

    # =========================================================
    # ✅ 대상자 팀 정보(SubAdminTemp) bulk load (기존 영향 X: rows에 키만 "추가")
    # =========================================================
    target_ids = list(qs.values_list("target_id", flat=True))
    sub_map = {
        str(sa.user_id): sa
        for sa in SubAdminTemp.objects.filter(user_id__in=target_ids).only(
            "user_id", "team_a", "team_b", "team_c"
        )
    }

    rows = []
    for rc in qs:
        tid = str(rc.target_id)
        sa = sub_map.get(tid)

        tg_team_a = _to_str(getattr(sa, "team_a", "")) or "-"
        tg_team_b = _to_str(getattr(sa, "team_b", "")) or "-"
        tg_team_c = _to_str(getattr(sa, "team_c", "")) or "-"
        tg_affiliation = _team_affiliation(tg_team_a, tg_team_b, tg_team_c)

        rows.append(
            {
                "id": rc.id,
                "requester_name": rc.requester.name,
                "requester_id": rc.requester.id,
                "target_name": rc.target.name,
                "target_id": rc.target.id,

                # ✅ 추가(호환 키): 소속/팀 (프론트에서 사용)
                "tg_team_a": tg_team_a,
                "tg_team_b": tg_team_b,
                "tg_team_c": tg_team_c,
                "tg_affiliation": tg_affiliation,

                "before_ftable": rc.before_ftable,
                "before_frate": rc.before_frate,
                "after_ftable": rc.after_ftable,
                "after_frate": rc.after_frate,
                "before_ltable": rc.before_ltable,
                "before_lrate": rc.before_lrate,
                "after_ltable": rc.after_ltable,
                "after_lrate": rc.after_lrate,
                "memo": rc.memo,
                "request_date": rc.created_at.strftime("%Y-%m-%d") if rc.created_at else "",
                "process_date": rc.process_date.strftime("%Y-%m-%d") if rc.process_date else "",
            }
        )

    return json_ok({"kind": "rate", "rows": rows})


@require_POST
@login_required
@grade_required("superuser", "head", "leader")
@transaction.atomic
def rate_save(request):
    """✅ RateChange 저장"""
    payload = parse_json_body(request)
    rows = payload.get("rows", [])
    month = normalize_month(payload.get("month") or "")

    user = request.user
    part = resolve_part_for_write(user, payload.get("part") or "")
    branch = resolve_branch_for_write(user, payload.get("branch") or "")

    saved = 0
    target_ids = []

    try:
        for r in rows:
            target_id = _to_str(r.get("target_id") or "")
            if not target_id:
                continue

            target = CustomUser.objects.filter(id=target_id).first()
            if not target:
                continue
            if not _can_use_target(user, target, branch):
                return json_err("권한 범위 밖의 대상자가 포함되어 있습니다.", status=403)

            rt = RateTable.objects.filter(user=target).first()
            before_ftable = rt.non_life_table if rt else ""
            before_ltable = rt.life_table if rt else ""

            before_frate = find_table_rate(target.branch, before_ftable)
            before_lrate = find_table_rate(target.branch, before_ltable)

            after_ftable = _to_str(r.get("after_ftable") or "")
            after_ltable = _to_str(r.get("after_ltable") or "")

            after_frate = find_table_rate(target.branch, after_ftable)
            after_lrate = find_table_rate(target.branch, after_ltable)

            memo = _to_str(r.get("memo") or "")

            RateChange.objects.create(
                requester=user,
                target=target,
                part=part,
                branch=branch,
                month=month,
                before_ftable=before_ftable,
                before_frate=before_frate,
                before_ltable=before_ltable,
                before_lrate=before_lrate,
                after_ftable=after_ftable,
                after_frate=after_frate,
                after_ltable=after_ltable,
                after_lrate=after_lrate,
                memo=memo,
            )
            saved += 1
            target_ids.append(str(target.id))

        # ✅ AuditLog (success)
        try:
            log_action(
                request,
                ACTION.PARTNER_RATE_SAVE,
                meta={
                    "month": month,
                    "part": part,
                    "branch": branch,
                    "saved_count": saved,
                    "targets_sample": target_ids[:20],
                },
                success=True,
            )
        except Exception:
            logger.exception("[partner.rate] audit failed: rate_save success")

        return json_ok({"saved_count": saved})

    except Exception as e:
        # ✅ AuditLog (failure)
        try:
            log_action(
                request,
                ACTION.PARTNER_RATE_SAVE,
                meta={
                    "month": month,
                    "part": part,
                    "branch": branch,
                    "saved_count": saved,
                    "targets_sample": target_ids[:20],
                    "error": str(e),
                },
                success=False,
            )
        except Exception:
            logger.exception("[partner.rate] audit failed: rate_save failure")
        raise


@require_POST
@login_required
@grade_required("superuser", "head")
@transaction.atomic
def rate_delete(request):
    """✅ RateChange 삭제"""
    data = parse_json_body(request)
    record_id = data.get("id")
    if not record_id:
        return json_err("id 누락", status=400)

    rc = get_object_or_404(RateChange, id=record_id)
    user = request.user

    if not (user.grade in ["superuser", "head"] or rc.requester_id == user.id):
        return json_err("삭제 권한이 없습니다.", status=403)
    
    # ✅ AuditLog: 삭제 직전(삭제 후 객체 소실)
    try:
        log_action(
            request,
            ACTION.PARTNER_RATE_DELETE,
            obj=rc,
            meta={
                "id": rc.id,
                "month": getattr(rc, "month", ""),
                "part": getattr(rc, "part", ""),
                "branch": getattr(rc, "branch", ""),
                "requester_id": getattr(rc, "requester_id", None),
                "target_id": getattr(rc, "target_id", None),
                "after_ftable": getattr(rc, "after_ftable", ""),
                "after_ltable": getattr(rc, "after_ltable", ""),
            },
            success=True,
        )
    except Exception:
        logger.exception("[partner.rate] audit failed: rate_delete id=%s", getattr(rc, "id", None))

    rc.delete()

    
    return json_ok({})
