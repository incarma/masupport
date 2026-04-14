# django_ma/board/tasks/__init__.py

from .industry_info import collect_board_industry_news

__all__ = [
    "collect_board_industry_news",
]