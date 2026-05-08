# django_ma/commission/services/rate_example_normalizers/__init__.py
from __future__ import annotations

"""
RateExample 보험사별 정규화 모듈 패키지.

역할:
- 보험사별 raw 파일 파싱 규칙을 파일 단위로 분리한다.
- commission/services/rate_example_normalizer.py 는 정규화 진입점만 유지한다.
"""

from commission.services.rate_example_normalizers.life_abl import (
    build_life_abl_conversion_rows,
)
from commission.services.rate_example_normalizers.life_db import (
    build_life_db_conversion_rows,
)
from commission.services.rate_example_normalizers.life_im import (
    build_life_im_conversion_rows,
)

__all__ = [
    "build_life_abl_conversion_rows",
    "build_life_db_conversion_rows",
    "build_life_im_conversion_rows",
]