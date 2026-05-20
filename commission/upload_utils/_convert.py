# django_ma/commission/upload_utils/_convert.py

"""
commission 업로드 값 변환 유틸 SSOT.

주의:
- 핸들러에서 직접 int()/Decimal()/pd.to_datetime()을 호출하지 않고 이 모듈을 경유한다.
- 실패 시 예외를 전파하지 않고 도메인별 기본값을 반환한다.
- 금액 정규화와 통산손/생보 q2 저장 정책을 분리한다.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

import pandas as pd

# =========================================================
# Constants
# =========================================================
DEC2 = Decimal("0.00")
EMPTY_LIKE_VALUES = frozenset({"", "nan", "none", "-"})


def _is_empty_like(v) -> bool:
    """
    업로드 raw 값 공란 판정 SSOT.
    - 기존 각 handler/parser에 흩어져 있던 "", nan, none, "-" 판정을 통일한다.
    - 사번/금액/날짜 변환 정책 자체는 변경하지 않는다.
    """
    if v is None:
        return True
    if hasattr(pd, "isna") and pd.isna(v):
        return True
    return str(v).strip().lower() in EMPTY_LIKE_VALUES

# =========================================================
# Convert helpers
# =========================================================
def _to_int(v, default: int = 0) -> int:
    """숫자/문자/NaN 값을 int로 변환한다. 실패 시 default 반환."""
    try:
        if v is None:
            return default
        if hasattr(pd, "isna") and pd.isna(v):
            return default
        s = str(v).strip().replace(",", "")
        if s.lower() in EMPTY_LIKE_VALUES:
            return default
        return int(float(s))
    except Exception:
        return default


def _to_decimal(v, default: Decimal = Decimal("0.00")) -> Decimal:
    """
    일반 금액/실적 필드용 Decimal 변환.

    - 콤마 제거 후 Decimal로 변환한다.
    - 소수점 자리수 quantize는 하지 않는다.
    - 저장 필드가 소수 2자리 고정이면 _safe_decimal_q2()를 사용한다.
    """
    try:
        if v is None:
            return default
        if hasattr(pd, "isna") and pd.isna(v):
            return default
        s = str(v).strip().replace(",", "")
        if s.lower() in EMPTY_LIKE_VALUES:
            return default
        return Decimal(s)
    except (InvalidOperation, Exception):
        return default


def _safe_decimal_q2(v, default: Decimal = DEC2) -> Decimal:
    """
    DecimalField(decimal_places=2) 저장용 변환.

    통산손/생보처럼 DB 저장 전 소수 2자리 반올림이 필요한 필드에서만 사용한다.
    일반 업로드 금액은 _to_decimal()을 사용해 기존 저장 단위를 유지한다.
    """
    try:
        if v is None:
            return default
        if hasattr(pd, "isna") and pd.isna(v):
            return default
        s = str(v).strip().replace(",", "")
        if s.lower() in EMPTY_LIKE_VALUES:
            return default
        return Decimal(s).quantize(DEC2, rounding=ROUND_HALF_UP)
    except Exception:
        return default


def _to_date(v):
    """pandas Timestamp / datetime / 문자열 날짜를 date로 안전 변환."""
    try:
        if v is None:
            return None
        if hasattr(pd, "isna") and pd.isna(v):
            return None
        if isinstance(v, pd.Timestamp):
            return v.date()
        if hasattr(v, "date") and callable(v.date):
            return v.date()

        s = str(v).strip()
        if s.lower() in EMPTY_LIKE_VALUES:
            return None

        s = s.replace(".", "-").replace("/", "-")
        dt = pd.to_datetime(s, errors="coerce")
        return dt.date() if not pd.isna(dt) else None
    except Exception:
        return None


def _to_div(v, default: str = "") -> str:
    """분급여부/정상 여부 텍스트 정규화."""
    s = ("" if v is None else str(v)).strip()
    if s.lower() in EMPTY_LIKE_VALUES:
        return default
    if "분급" in s:
        return "분급"
    if "정상" in s:
        return "정상"
    return default


def _norm_emp_id(v) -> str:
    """사번/사원코드 정규화: '1234567.0' → '1234567'."""
    if v is None:
        return ""
    if hasattr(pd, "isna") and pd.isna(v):
        return ""
    s = str(v).strip()
    if s.lower() in EMPTY_LIKE_VALUES:
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    return s.strip()


def _extract_emp7_from_a(raw) -> str:
    """
    통산손/생보 raw matrix A열에서 사번 7자리 추출.
    emp7 = s[-8:-1]
    """
    s = "" if raw is None else str(raw).strip()
    if len(s) < 8:
        return ""
    emp7 = s[-8:-1]
    return emp7 if emp7.isdigit() and len(emp7) == 7 else ""