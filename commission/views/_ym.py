# django_ma/commission/views/_ym.py
from __future__ import annotations

"""
YM parsing helpers (views layer SSOT)

목표:
- approval.py 등에서 중복되는 ym/year/month 파싱 및 검증 로직을 공통화
- 허용 입력 형식:
  - year=YYYY, month=MM  (기존 방식)
  - ym=YYYY-MM or YYYYMM (프론트/호환 방식)

기능 변화 없음:
- 기존 approval.py의 _split_ym/_validate_ym 동작을 그대로 옮김
"""

import re
from dataclasses import dataclass
from typing import Tuple


def pad2(n: int) -> str:
    return f"{n:02d}"


def split_ym(ym: str) -> Tuple[str, str]:
    """
    Accept ym formats:
      - 'YYYY-MM'  (e.g. 2026-02)
      - 'YYYYMM'   (e.g. 202602)
    Return (year, month) as strings or raise ValueError.
    """
    s = (ym or "").strip()
    if not s:
        raise ValueError("연/월을 선택해주세요.")

    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m:
        return m.group(1), m.group(2)

    m = re.fullmatch(r"(\d{4})(\d{2})", s)
    if m:
        return m.group(1), m.group(2)

    raise ValueError("연/월 형식이 올바르지 않습니다. (예: 2026-02)")


def validate_ym(year: str, month: str) -> str:
    """
    year/month 문자열을 검증하고 'YYYY-MM' 반환.
    """
    if not (year or "").isdigit():
        raise ValueError("연도를 선택해주세요.")
    if not (month or "").isdigit():
        raise ValueError("월을 선택해주세요.")

    y = int(year)
    m = int(month)
    if m < 1 or m > 12:
        raise ValueError("월은 1~12 범위여야 합니다.")
    return f"{y}-{pad2(m)}"


@dataclass(frozen=True)
class YMResolved:
    """
    resolve_ym() 결과:
    - ym: 'YYYY-MM'
    - year/month: 문자열(원래 파라미터가 없더라도 ym에서 보완)
    """
    ym: str
    year: str
    month: str


def resolve_ym(*, ym_param: str, year: str, month: str) -> YMResolved:
    """
    기존 approval.py 동작과 동일:
    1) year/month가 있으면 그것을 우선 사용
    2) 아니면 ym_param을 해석해 year/month를 보완
    """
    y = (year or "").strip()
    m = (month or "").strip()
    ym_raw = (ym_param or "").strip()

    if y and m:
        ym = validate_ym(y, m)
        return YMResolved(ym=ym, year=y, month=m)

    yy, mm = split_ym(ym_raw)
    y = y or yy
    m = m or mm
    ym = validate_ym(y, m)
    return YMResolved(ym=ym, year=y, month=m)