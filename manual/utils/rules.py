# django_ma/manual/utils/rules.py

from __future__ import annotations

from typing import Tuple

from django.db import models

from manual.models import Manual, ManualSection
from .parsing import is_digits


def ensure_default_section(manual: Manual) -> ManualSection:
    """
    ✅ 섹션이 하나도 없을 경우 기본 섹션 1개 생성
    - 상세 화면이 완전히 비어버리는 상황 방지
    """
    first = manual.sections.order_by("sort_order", "id").first()
    if first:
        return first
    return ManualSection.objects.create(manual=manual, sort_order=1, title="")


def access_to_flags(access: str) -> Tuple[bool, bool]:
    """
    access 문자열(normal/admin/staff) -> (admin_only, is_published)

    - normal: (False, True)
    - admin : (True,  True)
    - staff : (False, False)  # 직원전용=비공개
    """
    if access == "admin":
        return True, True
    if access == "staff":
        return False, False
    return False, True


def clean_reorder_ids(raw_ids, *, label: str, duplicate_message: str) -> tuple[list[int] | None, str]:
    """
    정렬 요청 ID 목록 검증.

    기능 변화 0:
    - 기존 list 검증 유지
    - 숫자 문자열만 허용
    - 중복 ID 오류 유지
    """
    if not isinstance(raw_ids, list):
        return None, f"{label} 형식이 올바르지 않습니다."
    if not all(is_digits(item) for item in raw_ids):
        return None, f"{label} 형식이 올바르지 않습니다."

    cleaned = [int(item) for item in raw_ids]
    if len(cleaned) != len(set(cleaned)):
        return None, duplicate_message

    return cleaned, ""


def update_sort_order(model_cls: type[models.Model], ids: list[int], *, extra_filter: dict | None = None) -> None:
    """
    sort_order 저장 공통 함수.

    주의:
    - transaction.atomic()은 호출부에서 유지한다.
    - block move처럼 여러 update가 하나의 transaction에 묶여야 하는 흐름을 깨지 않는다.
    """
    filters = extra_filter or {}
    for idx, obj_id in enumerate(ids, start=1):
        model_cls.objects.filter(id=obj_id, **filters).update(sort_order=idx)
