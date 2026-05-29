# django_ma/manual/utils/__init__.py

"""
manual.utils 패키지

- http        : JSON 파싱/통일 응답
- permissions : 권한(grade 기반)
- rules       : 비즈니스 규칙
- serializers : DOM 즉시 렌더용 dict 변환

기존 코드 호환을 위해 여기서 주요 함수를 re-export 합니다.
"""

from .http import json_body, ok, fail
from .permissions import (
    user_grade,
    is_superuser,
    is_head,
    ensure_superuser_or_403,
    manual_accessible_or_denied,
    filter_manuals_for_user,
)
from .rules import (
    ensure_default_section,
    access_to_flags,
    clean_reorder_ids,
    update_sort_order,
)
from .serializers import attachment_to_dict, block_to_dict
from .parsing import to_str, is_digits
from .files import open_manual_fileresponse

__all__ = [
    "json_body",
    "ok",
    "fail",
    "user_grade",
    "is_superuser",
    "is_head",
    "ensure_superuser_or_403",
    "manual_accessible_or_denied",
    "filter_manuals_for_user",
    "ensure_default_section",
    "access_to_flags",
    "clean_reorder_ids",
    "update_sort_order",
    "attachment_to_dict",
    "block_to_dict",
    "to_str",
    "is_digits",
    "open_manual_fileresponse",
]
