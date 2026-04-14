# django_ma/support/views/__init__.py
"""
support.views public API

레거시 호환 목적:
- 업계정보 관련 실제 구현은 board 쪽으로 이동
- 기존 import surface는 유지
"""

from .pages import industry_info
from .api import save_preference, mark_click

__all__ = [
    "industry_info",
    "save_preference",
    "mark_click",
]