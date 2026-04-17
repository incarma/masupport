# django_ma/board/tasks/__init__.py

from .industry_info import collect_board_industry_news, cleanup_old_industry_articles

__all__ = [
    "collect_board_industry_news",
    "cleanup_old_industry_articles",
]