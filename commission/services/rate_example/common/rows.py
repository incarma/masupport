# django_ma/commission/services/rate_example/common/rows.py
from __future__ import annotations

"""
RateExample row list 공통 helper.

주의:
- DB 저장은 상위 normalizer가 담당한다.
- 이 모듈은 파일 내부 중복 row append 방지만 담당한다.
"""


def append_unique(
    rows: list,
    seen: set[tuple],
    row,
    key: tuple,
) -> None:
    """
    파일 내부 완전 중복 row를 방지한다.

    append 업로드 정책은 DB 기존 row 보존 정책이므로,
    여기서는 같은 파일에서 생성된 중복만 제거한다.
    """
    if key in seen:
        return
    seen.add(key)
    rows.append(row)
