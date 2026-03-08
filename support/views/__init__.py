# django_ma/support/views/__init__.py

from .pages import industry_info
from .api import save_preference, mark_click

__all__ = [
    "industry_info",
    "save_preference",
    "mark_click",
]