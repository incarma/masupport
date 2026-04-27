# django_ma/manual/views/manual.py

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from audit.constants import ACTION
from audit.services import log_action

from ..constants import MANUAL_TITLE_MAX_LEN
from ..models import Manual
from ..utils import (
    access_to_flags,
    fail,
    is_digits,
    json_body,
    ok,
    to_str,
    ensure_superuser_or_403,
)


@require_POST
@login_required
def manual_create_ajax(request):
    """superuser 전용: 모달 기반 생성(JSON)"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    title = to_str(payload.get("title"))
    access = to_str(payload.get("access") or "normal")

    if not title:
        return fail("매뉴얼 이름을 입력해주세요.", 400)
    if len(title) > MANUAL_TITLE_MAX_LEN:
        return fail(f"매뉴얼 이름은 {MANUAL_TITLE_MAX_LEN}자 이하여야 합니다.", 400)
    if access not in ("normal", "admin", "staff"):
        return fail("공개 범위 값이 올바르지 않습니다.", 400)

    admin_only, is_published = access_to_flags(access)
    manual = Manual.objects.create(title=title, admin_only=admin_only, is_published=is_published)

    log_action(
        request,
        ACTION.MANUAL_CREATE,
        obj=manual,
        meta={"title": manual.title, "access": access},
    )

    return ok({"redirect_url": reverse("manual:manual_detail", args=[manual.pk])})


@require_POST
@login_required
def manual_update_title_ajax(request):
    """superuser 전용: 매뉴얼 타이틀 단건 수정"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    mid = payload.get("id")
    title = to_str(payload.get("title"))

    if not is_digits(mid):
        return fail("id 값이 올바르지 않습니다.", 400)
    if not title:
        return fail("제목을 입력해주세요.", 400)
    if len(title) > MANUAL_TITLE_MAX_LEN:
        return fail(f"제목은 {MANUAL_TITLE_MAX_LEN}자 이하여야 합니다.", 400)

    m = get_object_or_404(Manual, id=int(mid))
    m.title = title
    m.save(update_fields=["title", "updated_at"])

    log_action(
        request,
        ACTION.MANUAL_UPDATE,
        obj=m,
        meta={"field": "title", "title": m.title},
    )

    return ok({"title": m.title})


@require_POST
@login_required
def manual_bulk_update_ajax(request):
    """superuser 전용: 여러 매뉴얼 title/access 일괄 업데이트"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    items = payload.get("items") or []

    if not isinstance(items, list):
        return fail("items 형식이 올바르지 않습니다.", 400)

    updated = []

    with transaction.atomic():
        for it in items:
            mid = it.get("id")
            title = to_str(it.get("title"))
            access = to_str(it.get("access") or "normal")

            if not is_digits(mid):
                return fail("id 값이 올바르지 않습니다.", 400)
            if not title:
                return fail("제목은 비워둘 수 없습니다.", 400)
            if len(title) > MANUAL_TITLE_MAX_LEN:
                return fail(f"제목은 {MANUAL_TITLE_MAX_LEN}자 이하여야 합니다.", 400)
            if access not in ("normal", "admin", "staff"):
                return fail("공개 범위 값이 올바르지 않습니다.", 400)

            m = get_object_or_404(Manual, id=int(mid))
            admin_only, is_published = access_to_flags(access)

            m.title = title
            m.admin_only = admin_only
            m.is_published = is_published
            m.save(update_fields=["title", "admin_only", "is_published", "updated_at"])

            log_action(
                request,
                ACTION.MANUAL_BULK_UPDATE,
                obj=m,
                meta={"field": "bulk_update", "title": m.title, "access": access},
            )

            updated.append(
                {"id": m.id, "title": m.title, "admin_only": m.admin_only, "is_published": m.is_published}
            )

    return ok({"updated": updated})


@require_POST
@login_required
def manual_reorder_ajax(request):
    """superuser 전용: 매뉴얼 목록 정렬 저장"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    ordered_ids = payload.get("ordered_ids") or []

    if (not isinstance(ordered_ids, list)) or (not all(is_digits(x) for x in ordered_ids)):
        return fail("ordered_ids 형식이 올바르지 않습니다.", 400)

    ordered_ids = [int(x) for x in ordered_ids]

    if len(ordered_ids) != len(set(ordered_ids)):
        return fail("중복된 매뉴얼 ID가 포함되어 있습니다.", 400)

    exist_count = Manual.objects.filter(id__in=ordered_ids).count()
    if exist_count != len(ordered_ids):
        return fail("존재하지 않는 매뉴얼이 포함되어 있습니다.", 400)

    with transaction.atomic():
        for idx, mid in enumerate(ordered_ids, start=1):
            Manual.objects.filter(id=mid).update(sort_order=idx)

    log_action(
        request,
        ACTION.MANUAL_REORDER,
        obj=None,
        meta={"ordered_ids": ordered_ids},
    )

    return ok()


@require_POST
@login_required
def manual_delete_ajax(request):
    """superuser 전용: 매뉴얼 삭제"""
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied

    payload = json_body(request)
    mid = payload.get("id")

    if not is_digits(mid):
        return fail("id 값이 올바르지 않습니다.", 400)

    m = get_object_or_404(Manual, id=int(mid))

    log_action(
        request,
        ACTION.MANUAL_DELETE,
        obj=m,
        meta={"title": m.title},
    )

    m.delete()
    return ok()
