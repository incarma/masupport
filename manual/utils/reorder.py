# django_ma/manual/utils/reorder.py

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db import models

from .parsing import is_digits


def clean_ordered_ids(
    raw_ids: Any,
    *,
    label: str,
    duplicate_message: str,
) -> tuple[list[int] | None, str]:
    """
    ✅ 정렬 요청 ID 목록 검증 공통 헬퍼

    목적:
    - manual / section / block reorder 뷰의 반복 검증 로직을 제거한다.
    - list 여부, 숫자 변환 가능 여부, 중복 여부를 한 곳에서 처리한다.

    반환:
    - ([1, 2, 3], ""): 정상
    - (None, "오류 메시지"): 실패

    기능 변화 0:
    - 기존과 동일하게 숫자 문자열만 허용한다.
    - 중복 ID는 기존처럼 오류 처리한다.
    """
    if not isinstance(raw_ids, list):
        return None, f"{label} 형식이 올바르지 않습니다."

    if not all(is_digits(item) for item in raw_ids):
        return None, f"{label} 형식이 올바르지 않습니다."

    cleaned = [int(item) for item in raw_ids]

    if len(cleaned) != len(set(cleaned)):
        return None, duplicate_message

    return cleaned, ""


def require_same_id_set(
    *,
    requested_ids: Iterable[int],
    existing_ids: Iterable[int],
    message: str,
) -> str:
    """
    ✅ 요청 ID 목록과 DB의 현재 ID 목록 일치 검증

    목적:
    - 프론트에서 일부 ID가 누락되거나 다른 섹션/매뉴얼의 ID가 섞인 경우 차단한다.

    기능 변화 0:
    - 기존 set(cleaned) != existing 검증과 동일한 판단을 수행한다.
    """
    if set(requested_ids) != set(existing_ids):
        return message
    return ""


def update_sort_order_rows(
    model_cls: type[models.Model],
    ordered_ids: list[int],
    *,
    extra_filter: dict[str, Any] | None = None,
) -> None:
    """
    ✅ sort_order 저장 공통 헬퍼

    목적:
    - 반복되는 for idx, id in enumerate(...): update(sort_order=idx) 패턴을 통합한다.

    주의:
    - transaction.atomic()은 호출부에서 감싼다.
    - 블록 이동처럼 여러 업데이트를 하나의 transaction 안에서 묶어야 하는 케이스를 위해
      이 함수 내부에서는 transaction.atomic()을 열지 않는다.

    기능 변화 0:
    - 기존과 동일하게 sort_order는 1부터 저장한다.
    - 기존과 동일하게 QuerySet.update()를 사용한다.
    """
    filters = extra_filter or {}

    for idx, obj_id in enumerate(ordered_ids, start=1):
        model_cls.objects.filter(id=obj_id, **filters).update(sort_order=idx)