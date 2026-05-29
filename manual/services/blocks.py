# django_ma/manual/services/blocks.py

from __future__ import annotations

from django.shortcuts import get_object_or_404

from manual.models import ManualBlock, ManualSection


def get_section_for_block(section_id: int, manual_id: int) -> ManualSection | None:
    """블록 추가 시 사용. 섹션이 없으면 None 반환."""
    return ManualSection.objects.filter(id=section_id, manual_id=manual_id).first()


def add_block(sec: ManualSection, *, content: str, image) -> ManualBlock:
    """블록 추가 — sort_order 자동 계산 포함"""
    last_order = ManualBlock.objects.filter(section=sec).count()
    return ManualBlock.objects.create(
        manual=sec.manual,
        section=sec,
        content=content,
        image=image if image else None,
        sort_order=last_order + 1,
    )


def get_block_or_404_for_update(block_id: int) -> ManualBlock:
    return get_object_or_404(
        ManualBlock.objects.select_related("section__manual").prefetch_related("attachments"),
        id=block_id,
    )


def update_block(block: ManualBlock, *, content: str, remove_image: bool, new_image) -> ManualBlock:
    """블록 내용/이미지 수정 — 파일 삭제 포함. transaction.atomic()은 호출부에서 적용한다."""
    block.content = content
    if remove_image:
        if block.image:
            block.image.delete(save=False)
        block.image = None
    if new_image:
        if block.image:
            block.image.delete(save=False)
        block.image = new_image
    block.save()
    return block


def get_block_or_404_for_delete(block_id: int) -> ManualBlock:
    return get_object_or_404(
        ManualBlock.objects.prefetch_related("attachments"),
        pk=block_id,
    )


def get_block_or_404_for_image(block_id: int) -> ManualBlock:
    return get_object_or_404(
        ManualBlock.objects.select_related("section__manual", "manual"),
        pk=block_id,
    )


def get_section_block_ids(section: ManualSection) -> set[int]:
    return set(ManualBlock.objects.filter(section=section).values_list("id", flat=True))


def get_block_ids_for_sections(section_ids: list[int]) -> set[int]:
    return set(ManualBlock.objects.filter(section_id__in=section_ids).values_list("id", flat=True))


def move_blocks_to_section(block_ids: list[int], section_id: int) -> None:
    """bulk update — transaction.atomic()은 호출부에서 적용한다."""
    ManualBlock.objects.filter(id__in=block_ids).update(section_id=section_id)
