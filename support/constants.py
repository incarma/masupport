# django_ma/support/constants.py
"""
support.constants

레거시 호환 상수 래퍼
--------------------
6단계부터 업계정보 상수의 실제 SSOT는 board.constants_industry 로 통일합니다.

이 파일은 기존 import 경로 호환을 위해 유지합니다.
"""

from board.constants_industry import (  # noqa: F401
    DEFAULT_INDUSTRY_NEWS_QUERIES,
    INDUSTRY_RECOMMEND_MODEL_VERSION,
    SOURCE_CHOICES,
    SOURCE_DAUM,
    SOURCE_DIRECT,
    SOURCE_NAVER,
    TOPIC_AUTO,
    TOPIC_CHOICES,
    TOPIC_CONSUMER,
    TOPIC_GA,
    TOPIC_KEYWORDS,
    TOPIC_LIFE,
    TOPIC_NL,
    TOPIC_REAL,
    TOPIC_REG,
    TOPIC_TREND,
)

# -------------------------------------------------------------------------
# 기존 support 명칭 호환
# -------------------------------------------------------------------------
SUPPORT_RECOMMEND_MODEL_VERSION = INDUSTRY_RECOMMEND_MODEL_VERSION
DEFAULT_NAVER_QUERIES = DEFAULT_INDUSTRY_NEWS_QUERIES

__all__ = [
    "TOPIC_REAL",
    "TOPIC_AUTO",
    "TOPIC_LIFE",
    "TOPIC_NL",
    "TOPIC_GA",
    "TOPIC_REG",
    "TOPIC_CONSUMER",
    "TOPIC_TREND",
    "TOPIC_CHOICES",
    "SOURCE_NAVER",
    "SOURCE_DAUM",
    "SOURCE_DIRECT",
    "SOURCE_CHOICES",
    "INDUSTRY_RECOMMEND_MODEL_VERSION",
    "SUPPORT_RECOMMEND_MODEL_VERSION",
    "DEFAULT_INDUSTRY_NEWS_QUERIES",
    "DEFAULT_NAVER_QUERIES",
    "TOPIC_KEYWORDS",
]
