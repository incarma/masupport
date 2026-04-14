# Add File: django_ma/support/tasks.py
from __future__ import annotations

"""
support.tasks

레거시 호환 래퍼
----------------
3단계부터 업계정보 기사 수집 task의 실제 SSOT는
board.tasks.industry_info.collect_board_industry_news 로 이동합니다.

기존 beat / 수동 호출 / import 경로 호환을 위해 이 파일은 유지합니다.
"""

from board.tasks.industry_info import collect_board_industry_news


def collect_support_naver_news(*args, **kwargs):
    """
    기존 support task 이름 호환용 alias wrapper
    """
    return collect_board_industry_news(*args, **kwargs)
