# django_ma/manual/services/manuals.py

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone

from manual.models import Manual
from manual.utils.permissions import filter_manuals_for_user


def get_manual_list(user) -> "QuerySet[Manual]":
    """목록 쿼리 — 권한 필터 + 정렬 포함"""
    qs = Manual.objects.all()
    qs = filter_manuals_for_user(qs, user)
    return qs.order_by("sort_order", "-updated_at")


def get_manual_or_404(manual_id: int) -> Manual:
    return get_object_or_404(Manual, pk=manual_id)


def create_manual(*, title: str, admin_only: bool, is_published: bool) -> Manual:
    return Manual.objects.create(title=title, admin_only=admin_only, is_published=is_published)


def update_manual_title(manual: Manual, title: str) -> Manual:
    manual.title = title
    manual.save(update_fields=["title", "updated_at"])
    return manual


def update_manual(manual: Manual, *, title: str, admin_only: bool, is_published: bool) -> Manual:
    manual.title = title
    manual.admin_only = admin_only
    manual.is_published = is_published
    manual.save(update_fields=["title", "admin_only", "is_published", "updated_at"])
    return manual


def count_existing_manuals(manual_ids: list[int]) -> int:
    return Manual.objects.filter(id__in=manual_ids).count()


def get_manuals_by_ids(manual_ids: list[int]) -> "QuerySet[Manual]":
    return Manual.objects.filter(id__in=manual_ids)


def bulk_update_manuals(manuals_data: list[dict]) -> list[Manual]:
    """
    여러 매뉴얼 일괄 수정 (bulk_update).

    manuals_data: [{"manual": Manual, "title": str, "admin_only": bool, "is_published": bool}, ...]

    auto_now 필드(updated_at)를 명시적으로 갱신한다.
    transaction.atomic()은 호출부에서 적용한다.
    """
    now = timezone.now()
    to_update = []
    for d in manuals_data:
        m = d["manual"]
        m.title = d["title"]
        m.admin_only = d["admin_only"]
        m.is_published = d["is_published"]
        m.updated_at = now
        to_update.append(m)

    if to_update:
        Manual.objects.bulk_update(
            to_update,
            ["title", "admin_only", "is_published", "updated_at"],
        )

    return to_update
