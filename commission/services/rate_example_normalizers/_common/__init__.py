# django_ma/commission/services/rate_example_normalizers/_common/__init__.py
from __future__ import annotations

"""
RateExample normalizer 공통 helper 패키지.

주의:
- 이 패키지는 parser별 저장 정책을 바꾸기 위한 모듈이 아니다.
- 공백 정리, Decimal 변환, 파일 내부 중복 방지처럼 의미가 동일한 작은 기능만 제공한다.
- 보험사별 특수 규칙은 각 life_*.py / fire_*.py parser에 그대로 둔다.
"""

from .decimal import decimal_percent_cell, decimal_percent_value, decimal_from_text
from .excel import (
    build_merged_value_map,
    build_worksheet_value_map,
    cell_value_with_merged,
    filled_value_above,
)
from .rows import append_unique
from .text import clean_text, clean_spaces, is_empty_like

__all__ = [
    "clean_text",
    "clean_spaces",
    "is_empty_like",
    "decimal_from_text",
    "decimal_percent_cell",
    "build_merged_value_map",
    "build_worksheet_value_map",
    "cell_value_with_merged",
    "filled_value_above",
    "append_unique",
    "decimal_percent_value",
]