# django_ma/commission/upload_utils/_convert.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

import pandas as pd

# =========================================================
# Constants
# =========================================================
DEC2 = Decimal("0.00")

# =========================================================
# Convert helpers
# =========================================================
def _to_int(v, default: int = 0) -> int:
    """숫자/문자/NaN 등을 안전하게 int로 변환."""
    try:
        if v is None:
            return default
        if hasattr(pd, "isna") and pd.isna(v):
            return default
        s = str(v).strip().replace(",", "")
        if s.lower() in ("", "nan", "none", "-"):
            return default
        return int(float(s))
    except Exception:
        return default


def _to_decimal(v, default: Decimal = Decimal("0.00")) -> Decimal:
    """숫자/문자/NaN 등을 안전하게 Decimal로 변환."""
    try:
        if v is None:
            return default
        if hasattr(pd, "isna") and pd.isna(v):
            return default
        s = str(v).strip().replace(",", "")
        if s.lower() in ("", "nan", "none", "-"):
            return default
        return Decimal(s)
    except (InvalidOperation, Exception):
        return default


def _safe_decimal_q2(v, default: Decimal = DEC2) -> Decimal:
    """통산손/생보 저장용: Decimal(2) 자리로 안전 quantize."""
    try:
        if v is None:
            return default
        if hasattr(pd, "isna") and pd.isna(v):
            return default
        s = str(v).strip().replace(",", "")
        if s.lower() in ("", "nan", "none", "-"):
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
        if not s or s.lower() in ("nan", "none", "-"):
            return None

        s = s.replace(".", "-").replace("/", "-")
        dt = pd.to_datetime(s, errors="coerce")
        return dt.date() if not pd.isna(dt) else None
    except Exception:
        return None


def _to_div(v, default: str = "") -> str:
    """분급여부/정상 여부 텍스트 정규화."""
    s = ("" if v is None else str(v)).strip()
    if not s or s.lower() in ("nan", "none"):
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
    if not s or s.lower() in ("nan", "none"):
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