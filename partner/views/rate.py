# partner/views/rate.py
# ------------------------------------------------------------
# ✅ RateChange(요율변경 요청) API
# ------------------------------------------------------------

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import grade_required
from partner.models import RateChange, SubAdminTemp
from partner.services import rate as svc

from audit.services import log_action
from audit.constants import ACTION

from .responses import json_err, json_ok, parse_json_body
from .utils import (
    normalize_month,
    resolve_branch_for_query,
    resolve_branch_for_write,
    resolve_part_for_write,
    team_affiliation,
    to_str,
)


logger = logging.getLogger(__name__)


@require_GET
@login_required
@grade_required("superuser", "head", "leader")
def rate_fetch(request):
    """✅ RateChange 조회"""
    user = request.user
    month = normalize_month(request.GET.get("month") or "")
    branch = resolve_branch_for_query(user, to_str(request.GET.get("branch") or ""))

    qs = svc.get_rate_queryset(user, month=month, branch=branch)

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
        tg_team_a = to_str(getattr(sa, "team_a", "")) or "-"
        tg_team_b = to_str(getattr(sa, "team_b", "")) or "-"
        tg_team_c = to_str(getattr(sa, "team_c", "")) or "-"
        tg_affiliation = team_affiliation(tg_team_a, tg_team_b, tg_team_c)

        rows.append(
            {
                "id": rc.id,
                "requester_name": rc.requester.name,
                "requester_id": rc.requester.id,
                "target_name": rc.target.name,
                "target_id": rc.target.id,
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

    try:
        saved, target_ids = svc.create_rate_rows(
            user, rows, month=month, part=part, branch=branch
        )

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

    except PermissionError as e:
        return json_err(str(e), status=403)
    except Exception as e:
        try:
            log_action(
                request,
                ACTION.PARTNER_RATE_SAVE,
                meta={
                    "month": month,
                    "part": part,
                    "branch": branch,
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
