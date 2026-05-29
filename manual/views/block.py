# django_ma/manual/views/block.py

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.views.decorators.http import require_POST

from audit.constants import ACTION
from audit.services import log_action

from ..models import ManualBlock
from ..services import blocks as blocks_svc
from ..services import sections as sections_svc
from ..utils.uploads import validate_manual_image
from ..utils import (
    block_to_dict,
    fail,
    is_digits,
    json_body,
    ok,
    ensure_superuser_or_403,
    clean_reorder_ids,
    update_sort_order,
)


@require_POST
@login_required
def manual_block_add_ajax(request):
    """superuser 전용: 블록 추가 (multipart)"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    manual_id = request.POST.get("manual_id")
    section_id = request.POST.get("section_id")
    content = request.POST.get("content", "")  # sanitize는 ManualBlock.save()가 처리
    image = request.FILES.get("image")

    if image:
        err = validate_manual_image(image)
        if err:
            return fail(err, 400)

    if not (is_digits(manual_id) and is_digits(section_id)):
        return fail("요청값이 올바르지 않습니다.", 400)

    sec = blocks_svc.get_section_for_block(int(section_id), int(manual_id))
    if sec is None:
        return fail("섹션을 찾을 수 없습니다.", 404)

    b = blocks_svc.add_block(sec, content=content, image=image)

    log_action(
        request,
        ACTION.MANUAL_BLOCK_CREATE,
        obj=b,
        meta={"manual_id": sec.manual_id, "section_id": sec.id, "has_image": bool(image)},
    )

    return ok({"block": block_to_dict(b)})


@require_POST
@login_required
def manual_block_update_ajax(request):
    """superuser 전용: 블록 수정 (multipart)"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    block_id = request.POST.get("block_id")
    content = request.POST.get("content", "")  # sanitize는 ManualBlock.save()가 처리
    remove_image = request.POST.get("remove_image", "0")
    image = request.FILES.get("image")

    if not is_digits(block_id):
        return fail("block_id가 올바르지 않습니다.", 400)

    if image:
        err = validate_manual_image(image)
        if err:
            return fail(err, 400)

    b = blocks_svc.get_block_or_404_for_update(int(block_id))

    with transaction.atomic():
        b = blocks_svc.update_block(
            b,
            content=content,
            remove_image=(remove_image == "1"),
            new_image=image,
        )

    log_action(
        request,
        ACTION.MANUAL_BLOCK_UPDATE,
        obj=b,
        meta={
            "manual_id": b.manual_id,
            "section_id": b.section_id,
            "remove_image": remove_image == "1",
            "has_new_image": bool(image),
        },
    )

    return ok({"block": block_to_dict(b)})


@require_POST
@login_required
def manual_block_delete_ajax(request):
    """superuser 전용: 블록 삭제 (JSON)"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    block_id = payload.get("block_id")

    if not is_digits(block_id):
        return fail("block_id가 올바르지 않습니다.", 400)

    b = blocks_svc.get_block_or_404_for_delete(int(block_id))
    manual_id = b.manual_id
    section_id = b.section_id

    log_action(
        request,
        ACTION.MANUAL_BLOCK_DELETE,
        obj=b,
        meta={"manual_id": manual_id, "section_id": section_id},
    )

    b.delete()  # 이미지/첨부 파일은 모델 delete에서 처리(기존 전제 유지)

    return ok()


@require_POST
@login_required
def manual_block_reorder_ajax(request):
    """superuser 전용: 블록 순서 저장(섹션 단위)"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    section_id = payload.get("section_id")
    block_ids = payload.get("block_ids") or []

    if not is_digits(section_id) or not isinstance(block_ids, list):
        return fail("요청값이 올바르지 않습니다.", 400)

    section = sections_svc.get_section_or_404(int(section_id))

    cleaned, err = clean_reorder_ids(
        block_ids,
        label="block_ids",
        duplicate_message="중복된 블록 ID가 포함되어 있습니다.",
    )
    if err:
        return fail(err, 400)

    existing = blocks_svc.get_section_block_ids(section)
    if set(cleaned) != existing:
        return fail("현재 섹션의 블록 목록과 요청값이 일치하지 않습니다.", 400)

    with transaction.atomic():
        update_sort_order(ManualBlock, cleaned)

    log_action(
        request,
        ACTION.MANUAL_BLOCK_REORDER,
        obj=section,
        meta={
            "manual_id": section.manual_id,
            "section_id": section.id,
            "block_ids": cleaned,
        },
    )

    return ok()


@require_POST
@login_required
def manual_block_move_ajax(request):
    """superuser 전용: 블록을 다른 섹션으로 이동 + 양쪽 정렬 저장"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    from_section_id = payload.get("from_section_id")
    to_section_id = payload.get("to_section_id")
    from_block_ids = payload.get("from_block_ids") or []
    to_block_ids = payload.get("to_block_ids") or []

    if (not is_digits(from_section_id)) or (not is_digits(to_section_id)):
        return fail("section_id 값이 올바르지 않습니다.", 400)
    if (not isinstance(from_block_ids, list)) or (not isinstance(to_block_ids, list)):
        return fail("block_ids 형식이 올바르지 않습니다.", 400)

    from_sid = int(from_section_id)
    to_sid = int(to_section_id)

    from_sec = sections_svc.get_section_or_404(from_sid)
    to_sec = sections_svc.get_section_or_404(to_sid)

    if from_sec.manual_id != to_sec.manual_id:
        return fail("서로 다른 매뉴얼 간 이동은 허용되지 않습니다.", 400)

    cleaned_from, err = clean_reorder_ids(
        from_block_ids,
        label="from_block_ids",
        duplicate_message="중복된 블록 ID가 포함되어 있습니다.",
    )
    if err:
        return fail("from_block_ids 형식이 올바르지 않습니다.", 400)

    cleaned_to, err = clean_reorder_ids(
        to_block_ids,
        label="to_block_ids",
        duplicate_message="중복된 블록 ID가 포함되어 있습니다.",
    )
    if err:
        return fail("to_block_ids 형식이 올바르지 않습니다.", 400)

    all_requested = cleaned_from + cleaned_to
    if len(all_requested) != len(set(all_requested)):
        return fail("중복된 블록 ID가 포함되어 있습니다.", 400)

    existing_union = blocks_svc.get_block_ids_for_sections([from_sid, to_sid])
    if set(all_requested) != existing_union:
        return fail("이동 대상 섹션의 블록 목록과 요청값이 일치하지 않습니다.", 400)

    if not cleaned_to:
        return fail("이동 대상 블록 목록이 비어있습니다.", 400)

    with transaction.atomic():
        blocks_svc.move_blocks_to_section(cleaned_to, to_sid)

        # 양쪽 섹션 sort_order를 같은 transaction 안에서 저장
        update_sort_order(
            ManualBlock,
            cleaned_from,
            extra_filter={"section_id": from_sid},
        )
        update_sort_order(
            ManualBlock,
            cleaned_to,
            extra_filter={"section_id": to_sid},
        )

    log_action(
        request,
        ACTION.MANUAL_BLOCK_MOVE,
        obj=to_sec,
        meta={
            "manual_id": to_sec.manual_id,
            "from_section_id": from_sid,
            "to_section_id": to_sid,
            "from_block_ids": cleaned_from,
            "to_block_ids": cleaned_to,
        },
    )

    return ok()
