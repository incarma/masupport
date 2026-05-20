# django_ma/commission/services/rate_example_normalizers/_common/text.py
from __future__ import annotations

"""
RateExample parser 공통 텍스트 helper.

공통화 범위:
- None/nan/none/- 같은 공란성 값 판정
- 단순 문자열 trim
- 연속 공백 축약

공통화 금지:
- 상품명 줄바꿈을 붙일지, 공백으로 합칠지는 보험사별 정책이 다르다.
  따라서 이 모듈은 기본 helper만 제공한다.
"""

import re
from typing import Any

EMPTY_LIKE_TEXTS = {"", "nan", "none", "-"}


def clean_text(value: Any) -> str:
    """
    셀/PDF 값을 단순 저장용 문자열로 변환한다.

    기능 변화 방지:
    - 줄바꿈 병합 정책은 적용하지 않는다.
    - 값 자체의 의미 변환은 하지 않는다.
    """
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def clean_spaces(value: Any) -> str:
    """
    연속 공백/줄바꿈을 1칸으로 축약한다.

    PDF 추출 텍스트처럼 공백 흔들림이 큰 parser에서만 사용한다.
    """
    text = clean_text(value)
    return re.sub(r"\s+", " ", text).strip()


def is_empty_like(value: Any) -> bool:
    """
    parser 공통 공란성 값 판정.

    주의:
    - 업로드 엑셀 일반 변환용 SSOT는 commission.upload_utils._is_empty_like다.
    - 이 함수는 RateExample normalizer 내부에서만 사용한다.
    """
    return clean_text(value).lower() in EMPTY_LIKE_TEXTS


__all__ = [
    "EMPTY_LIKE_TEXTS",
    "clean_text",
    "clean_spaces",
    "is_empty_like",
]