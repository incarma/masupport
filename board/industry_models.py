# django_ma/board/industry_models.py
"""
board.industry_models

업계정보 모델 공개 import surface
-------------------------------
board 내부 다른 모듈에서는 이 파일을 통해 업계정보 모델을 참조합니다.
실체 모델은 board.models_industry 에 있습니다.
"""

from .models_industry import (
    IndustryArticle,
    IndustryCollectJobLog,
    IndustryRecommendation,
    IndustryUserPreference,
)

__all__ = [
    "IndustryArticle",
    "IndustryUserPreference",
    "IndustryRecommendation",
    "IndustryCollectJobLog",
]