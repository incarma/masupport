# django_ma/board/constants_industry.py
"""
Board Industry Info SSOT Constants

목적:
- support 앱의 업계정보 기능을 board로 통합하기 위한 상수 SSOT
- 1단계에서는 support.constants와 의미를 동일하게 유지
- 이후 support 제거 단계에서도 이 파일을 board 기준 상수로 계속 사용

주의:
- 추천 모델 버전 / 토픽 / 기본 수집 키워드 / 토픽 추론 키워드는
  기능 변화 0를 위해 현재 support 기준을 그대로 반영한다.
"""

from __future__ import annotations

# =============================================================================
# 기사 토픽 분류
# =============================================================================
TOPIC_REAL = "실손보험"
TOPIC_AUTO = "자동차보험"
TOPIC_LIFE = "생명보험"
TOPIC_NL = "손해보험"
TOPIC_GA = "GA"
TOPIC_REG = "보험규제"
TOPIC_CONSUMER = "소비자 이슈"
TOPIC_TREND = "업계동향"

TOPIC_CHOICES = [
    (TOPIC_REAL, TOPIC_REAL),
    (TOPIC_AUTO, TOPIC_AUTO),
    (TOPIC_LIFE, TOPIC_LIFE),
    (TOPIC_NL, TOPIC_NL),
    (TOPIC_GA, TOPIC_GA),
    (TOPIC_REG, TOPIC_REG),
    (TOPIC_CONSUMER, TOPIC_CONSUMER),
    (TOPIC_TREND, TOPIC_TREND),
]

# =============================================================================
# 뉴스 소스 구분
# =============================================================================
SOURCE_NAVER = "naver"
SOURCE_DAUM = "daum"
SOURCE_DIRECT = "direct"

SOURCE_CHOICES = [
    (SOURCE_NAVER, "Naver"),
    (SOURCE_DAUM, "Daum"),
    (SOURCE_DIRECT, "Direct"),
]

# =============================================================================
# 추천 모델 버전
# =============================================================================
INDUSTRY_RECOMMEND_MODEL_VERSION = "rule_v1"

# =============================================================================
# 기본 수집 키워드
# =============================================================================
DEFAULT_INDUSTRY_NEWS_QUERIES = [
    "보험",
    "실손보험",
    "자동차보험",
    "생명보험",
    "손해보험",
    "보험대리점",
    "GA",
    "보험규제",
    "금융소비자보호",
    "보험업계",
]

# =============================================================================
# 토픽 추론용 키워드
# =============================================================================
TOPIC_KEYWORDS = {
    TOPIC_REAL: ["실손", "실비"],
    TOPIC_AUTO: ["자동차보험", "자차", "대물", "대인"],
    TOPIC_LIFE: ["생명보험", "종신", "변액", "CI보험"],
    TOPIC_NL: ["손해보험", "화재보험", "상해보험"],
    TOPIC_GA: ["GA", "법인보험대리점", "보험대리점", "설계사", "FA"],
    TOPIC_REG: ["규제", "감독", "법", "제도", "당국", "금감원", "금융위"],
    TOPIC_CONSUMER: ["민원", "피해", "분쟁", "소비자", "불완전판매"],
    TOPIC_TREND: ["실적", "시장", "업계", "트렌드", "전망", "동향"],
}