# django_ma/support/views/api.py
"""
support.views.api

레거시 호환 뷰 래퍼
-------------------
5단계부터 업계정보 액션 API의 실제 기준은 board.views.industry_info 로 통일합니다.
이 파일은 기존 support URL/API 호출 호환을 위해 board 뷰를 그대로 위임합니다.
"""

from board.views.industry_info import (
    industry_mark_click as mark_click,
    industry_save_preference as save_preference,
)

__all__ = [
    "save_preference",
    "mark_click",
]