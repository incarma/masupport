# django_ma/manual/services/sections.py

from __future__ import annotations

from django.shortcuts import get_object_or_404

from manual.models import Manual, ManualSection
from manual.utils.rules import ensure_default_section


def get_manual_sections(manual: Manual):
    """상세 페이지용 — 섹션 > 블록 > 첨부 prefetch 쿼리셋"""
    return (
        manual.sections
        .prefetch_related("blocks", "blocks__attachments")
        .order_by("sort_order", "created_at")
    )


def add_section(manual: Manual) -> ManualSection:
    """새 섹션 추가 — sort_order 자동 계산 포함"""
    last = manual.sections.order_by("-sort_order", "-id").first()
    next_order = (last.sort_order if last else 0) + 1
    return ManualSection.objects.create(manual=manual, sort_order=next_order, title="")


def get_section_or_404(section_id: int) -> ManualSection:
    return get_object_or_404(ManualSection, pk=section_id)


def update_section_title(sec: ManualSection, title: str) -> ManualSection:
    sec.title = title
    sec.save(update_fields=["title", "updated_at"])
    return sec


def delete_section(sec: ManualSection) -> ManualSection | None:
    """섹션 삭제. 섹션이 0개가 되면 기본 섹션을 자동 생성하여 반환한다."""
    manual = sec.manual
    sec.delete()
    if manual.sections.count() == 0:
        return ensure_default_section(manual)
    return None


def get_section_ids(manual: Manual) -> set[int]:
    return set(ManualSection.objects.filter(manual=manual).values_list("id", flat=True))
