# django_ma/manual/views/manual.py

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.urls import reverse
from django.views.decorators.http import require_POST

from audit.constants import ACTION
from audit.services import log_action

from ..constants import MANUAL_TITLE_MAX_LEN
from ..models import Manual
from ..services import manuals as manuals_svc
from ..utils import (
    access_to_flags,
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
    manual = manuals_svc.create_manual(title=title, admin_only=admin_only, is_published=is_published)

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

    m = manuals_svc.get_manual_or_404(int(mid))
    m = manuals_svc.update_manual_title(m, title)

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

    # 1단계: 모든 항목 검증 (DB 미접촉)
    validated = []
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

        admin_only, is_published = access_to_flags(access)
        validated.append({
            "id": int(mid),
            "title": title,
            "admin_only": admin_only,
            "is_published": is_published,
            "access": access,
        })

    if not validated:
        return ok({"updated": []})

    # 2단계: 한 번의 쿼리로 전체 조회
    id_list = [v["id"] for v in validated]
    manual_map = {m.id: m for m in manuals_svc.get_manuals_by_ids(id_list)}
    if set(manual_map) != set(id_list):
        return fail("존재하지 않는 매뉴얼이 포함되어 있습니다.", 400)

    # 3단계: bulk_update (N회 save → 1회 UPDATE)
    manuals_data = [
        {
            "manual": manual_map[v["id"]],
            "title": v["title"],
            "admin_only": v["admin_only"],
            "is_published": v["is_published"],
        }
        for v in validated
    ]
    with transaction.atomic():
        updated_manuals = manuals_svc.bulk_update_manuals(manuals_data)

    # 4단계: 감사 로그 + 응답 구성
    updated = []
    for m, v in zip(updated_manuals, validated):
        log_action(
            request,
            ACTION.MANUAL_BULK_UPDATE,
            obj=m,
            meta={"field": "bulk_update", "title": m.title, "access": v["access"]},
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

    ordered_ids, err = clean_reorder_ids(
        ordered_ids,
        label="ordered_ids",
        duplicate_message="중복된 매뉴얼 ID가 포함되어 있습니다.",
    )
    if err:
        return fail(err, 400)

    exist_count = manuals_svc.count_existing_manuals(ordered_ids)
    if exist_count != len(ordered_ids):
        return fail("존재하지 않는 매뉴얼이 포함되어 있습니다.", 400)

    with transaction.atomic():
        # update_sort_order는 utils/rules.py의 공통 헬퍼 — 모델 클래스를 인자로 받는다
        update_sort_order(Manual, ordered_ids)

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

    m = manuals_svc.get_manual_or_404(int(mid))

    log_action(
        request,
        ACTION.MANUAL_DELETE,
        obj=m,
        meta={"title": m.title},
    )

    m.delete()
    return ok()
