# partner/views/structure.py
# ------------------------------------------------------------
# ✅ Structure(편제변경) API
# - core: ajax_save / ajax_delete / ajax_fetch
# - 신규 네이밍: structure_save / structure_delete / structure_fetch
# - legacy alias 유지 (기존 URL/호출부 영향 없음)
# ------------------------------------------------------------

import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import grade_required
from audit.constants import ACTION
from audit.services import log_action
from partner.models import StructureChange
from partner.services import structure as svc

from .responses import json_err, json_ok, parse_json_body
from .utils import (
    build_affiliation_display,
    date_to_yyyy_mm_dd,
    normalize_month,
    resolve_branch_for_query,
    resolve_branch_for_write,
    resolve_part_for_write,
    to_str,
)


logger = logging.getLogger(__name__)

ALLOWED_GRADES = ("superuser", "head", "leader")


# ------------------------------------------------------------
# Serializer
# ------------------------------------------------------------
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
        "request_date": date_to_yyyy_mm_dd(getattr(sc, "created_at", None)),
        "process_date": date_to_yyyy_mm_dd(getattr(sc, "process_date", None)),
    }


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

        created_count = svc.create_structure_rows(
            user, items, month=month, part=part, branch=branch
        )

        try:
            log_action(
                request,
                ACTION.PARTNER_STRUCTURE_SAVE,
                meta={
                    "month": month,
                    "part": part,
                    "branch": branch,
                    "saved_count": created_count,
                },
                success=True,
            )
        except Exception:
            logger.exception("[partner.structure] audit failed: ajax_save")

        return json_ok({"saved_count": created_count})

    except PermissionError as e:
        return json_err(str(e), status=403)
    except Exception:
        logger.exception("[partner.structure] save failed")
        return json_err("저장 중 오류가 발생했습니다.", status=400)


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

        deleted_id = svc.delete_structure_change(record, user)

        try:
            log_action(
                request,
                ACTION.PARTNER_STRUCTURE_DELETE,
                meta={"deleted_id": deleted_id},
                success=True,
            )
        except Exception:
            logger.exception("[partner.structure] audit failed: ajax_delete id=%s", deleted_id)

        return json_ok({"message": f"#{deleted_id} 삭제 완료"})

    except PermissionError as e:
        return json_err(str(e), status=403)
    except Exception:
        logger.exception("[partner.structure] delete failed")
        return json_err("삭제 중 오류가 발생했습니다.", status=500)


@require_GET
@login_required
@grade_required(*ALLOWED_GRADES)
def ajax_fetch(request):
    """✅ Structure 조회 (권한 스코프 동일 유지)"""
    try:
        user = request.user
        month = normalize_month(request.GET.get("month") or "")
        branch = resolve_branch_for_query(user, to_str(request.GET.get("branch")))

        qs = svc.get_structure_queryset(user, month=month, branch=branch)
        rows = [_serialize_structure_change(sc) for sc in qs]

        return json_ok({"kind": "structure", "rows": rows})

    except Exception:
        logger.exception("[partner.structure] fetch failed")
        return json_err("조회 중 오류가 발생했습니다.", status=500, extra={"rows": []})


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
