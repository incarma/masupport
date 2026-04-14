# django_ma/board/industry_models.py
# =========================================================
# Board Industry Proxy Models
#
# 목적:
# - 업계정보 기능의 "코드 소유권"을 board로 이동
# - 실제 DB 테이블/물리 모델은 기존 support 앱 것을 그대로 사용
# - 4단계에서는 proxy model 방식으로 안전하게 전환
#
# 장점:
# - migration으로 테이블 생성/변경 없음
# - 기존 support_* 테이블 재사용
# - board 내부에서는 board 모델처럼 import 가능
# =========================================================

from __future__ import annotations

from support.models import (
    SupportArticle,
    SupportCollectJobLog,
    SupportRecommendation,
    SupportUserPreference,
)


class IndustryArticle(SupportArticle):
    """
    업계정보 기사 Proxy Model

    - 실제 저장 테이블: support_article
    - board 내부에서 기사 도메인 명칭으로 사용
    """

    class Meta:
        proxy = True
        verbose_name = "업계정보 기사"
        verbose_name_plural = "업계정보 기사 목록"


class IndustryUserPreference(SupportUserPreference):
    """
    업계정보 사용자 선호도 Proxy Model

    - 실제 저장 테이블: support_user_preference
    - 평점/북마크/관심없음/읽음 상태 관리
    """

    class Meta:
        proxy = True
        verbose_name = "업계정보 사용자 선호도"
        verbose_name_plural = "업계정보 사용자 선호도 목록"


class IndustryRecommendation(SupportRecommendation):
    """
    업계정보 추천 스냅샷 Proxy Model

    - 실제 저장 테이블: support_recommendation
    - 추천 점수/사유/모델버전 확인용
    """

    class Meta:
        proxy = True
        verbose_name = "업계정보 추천"
        verbose_name_plural = "업계정보 추천 목록"


class IndustryCollectJobLog(SupportCollectJobLog):
    """
    업계정보 수집 작업 로그 Proxy Model

    - 실제 저장 테이블: support_collect_job_log
    - 기사 수집 배치 성공/실패 추적용
    """

    class Meta:
        proxy = True
        verbose_name = "업계정보 수집 작업 로그"
        verbose_name_plural = "업계정보 수집 작업 로그 목록"