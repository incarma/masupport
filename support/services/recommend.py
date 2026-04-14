# django_ma/support/services/recommend.py
from __future__ import annotations

"""
support.services.recommend

레거시 호환 래퍼
----------------
3단계부터 업계정보 추천 서비스의 실제 SSOT는 board.services.industry_recommend 로 이동합니다.

이 파일은 기존 import 경로 호환을 위해 유지합니다.
"""

from board.services.industry_recommend import (  # noqa: F401
    _base_queryset,
    get_major_articles,
    get_recommended_articles_for_user,
)

__all__ = [
    "_base_queryset",
    "get_major_articles",
    "get_recommended_articles_for_user",
]
