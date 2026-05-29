# django_ma/manual/views/section.py

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.views.decorators.http import require_POST

from audit.constants import ACTION
from audit.services import log_action

from ..constants import SECTION_TITLE_MAX_LEN
from ..models import ManualSection
from ..services import manuals as manuals_svc
from ..services import sections as sections_svc
from ..utils import (
    fail,
    is_digits,
    json_body,
    ok,
    to_str,
    ensure_superuser_or_403,
    clean_reorder_ids,
    update_sort_order,
)


@require_POST
@login_required
def manual_section_add_ajax(request):
    """superuser 전용: 섹션(카드) 추가"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    manual_id = payload.get("manual_id")

    if not is_digits(manual_id):
        return fail("manual_id가 올바르지 않습니다.", 400)

    m = manuals_svc.get_manual_or_404(int(manual_id))
    sec = sections_svc.add_section(m)

    log_action(
        request,
        ACTION.MANUAL_SECTION_CREATE,
        obj=sec,
        meta={
            "manual_id": m.id,
            "section_id": sec.id,
            "sort_order": sec.sort_order,
        },
    )

    return ok(
        {"section": {"id": sec.id, "sort_order": sec.sort_order, "updated_at": sec.updated_at.strftime("%Y-%m-%d %H:%M")}}
    )


@require_POST
@login_required
def manual_section_title_update_ajax(request):
    """superuser 전용: 섹션 소제목(title) 수정"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    section_id = payload.get("section_id")
    title = to_str(payload.get("title"))

    if not is_digits(section_id):
        return fail("section_id가 올바르지 않습니다.", 400)
    if len(title) > SECTION_TITLE_MAX_LEN:
        return fail(f"소제목은 최대 {SECTION_TITLE_MAX_LEN}자까지 가능합니다.", 400)

    sec = sections_svc.get_section_or_404(int(section_id))
    sec = sections_svc.update_section_title(sec, title)

    log_action(
        request,
        ACTION.MANUAL_SECTION_UPDATE,
        obj=sec,
        meta={
            "manual_id": sec.manual_id,
            "section_id": sec.id,
            "title_len": len(title),
        },
    )

    return ok({"section": {"id": sec.id, "title": sec.title, "updated_at": sec.updated_at.strftime("%Y-%m-%d %H:%M")}})


@require_POST
@login_required
def manual_section_delete_ajax(request):
    """superuser 전용: 섹션 삭제 (0개가 되면 기본 섹션 자동 생성)"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    section_id = payload.get("section_id")

    if not is_digits(section_id):
        return fail("section_id가 올바르지 않습니다.", 400)

    sec = sections_svc.get_section_or_404(int(section_id))
    manual = sec.manual
    deleted_section_id = sec.id

    new_sec = sections_svc.delete_section(sec)

    log_action(
        request,
        ACTION.MANUAL_SECTION_DELETE,
        obj=manual,
        meta={
            "manual_id": manual.id,
            "section_id": deleted_section_id,
        },
    )

    new_section = {"id": new_sec.id, "title": new_sec.title or ""} if new_sec else None
    return ok({"new_section": new_section})


@require_POST
@login_required
def manual_section_reorder_ajax(request):
    """superuser 전용: 섹션(카드) 순서 저장"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    manual_id = payload.get("manual_id")
    section_ids = payload.get("section_ids") or []

    if not is_digits(manual_id) or not isinstance(section_ids, list):
        return fail("요청값이 올바르지 않습니다.", 400)

    manual = manuals_svc.get_manual_or_404(int(manual_id))

    cleaned, err = clean_reorder_ids(
        section_ids,
        label="section_ids",
        duplicate_message="중복된 섹션 ID가 포함되어 있습니다.",
    )
    if err:
        return fail(err, 400)

    existing = sections_svc.get_section_ids(manual)
    if set(cleaned) != existing:
        return fail("현재 매뉴얼의 섹션 목록과 요청값이 일치하지 않습니다.", 400)

    with transaction.atomic():
        update_sort_order(ManualSection, cleaned)

    log_action(
        request,
        ACTION.MANUAL_SECTION_REORDER,
        obj=manual,
        meta={
            "manual_id": manual.id,
            "section_ids": cleaned,
        },
    )

    return ok()
