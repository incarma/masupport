# django_ma/dash/viewmods/utils/excel.py
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple

import pandas as pd

from dash.viewmods.constants import LIFE_INSURERS, PART_MAP


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def is_auto_excel(df: pd.DataFrame) -> bool:
    return "물건구분" in df.columns


def to_date(v) -> Optional[date]:
    if pd.isna(v) or v == "":
        return None

    if isinstance(v, (pd.Timestamp, datetime)):
        try:
            return v.date()
        except (AttributeError, ValueError):
            return None

    if isinstance(v, date):
        return v

    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None

    # 자동차 파일: "26/01/03"
    if re.match(r"^\d{2}/\d{2}/\d{2}$", s):
        try:
            return datetime.strptime(s, "%y/%m/%d").date()
        except ValueError:
            return None

    # "20260103"
    if re.match(r"^\d{8}$", s):
        try:
            return datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            return None

    try:
        dt = pd.to_datetime(s, errors="coerce")
        return None if pd.isna(dt) else dt.date()
    except Exception:  # pandas OutOfBoundsDatetime 등 버전별 다양한 예외 방어
        return None


def to_str_emp_id(v) -> Optional[str]:
    if pd.isna(v) or v == "":
        return None
    try:
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        s = str(v).strip()
        if s.endswith(".0"):
            s = s[:-2]
        return s
    except (AttributeError, ValueError):
        return str(v).strip()


def to_int_money(v) -> Optional[int]:
    if pd.isna(v) or v == "":
        return None
    try:
        s = str(v).strip().replace(",", "")
        if s == "" or s.lower() == "nan":
            return None
        return int(float(s))
    except ValueError:
        return None


def to_policy_no(v) -> Optional[str]:
    if pd.isna(v) or v == "":
        return None
    s = str(v).strip().replace(" ", "")
    if not s or s.lower() == "nan":
        return None

    m = re.match(r"^(\d+)\.0+$", s)
    if m:
        return m.group(1)

    m2 = re.match(r"^(\d+)\.(\d+)$", s)
    if m2 and set(m2.group(2)) <= {"0"}:
        return m2.group(1)

    return s


def normalize_part_snapshot(part: str | None) -> str | None:
    if not part:
        return part
    part = str(part).strip()
    return PART_MAP.get(part, part)


def life_nl_from_insurer(insurer: str) -> str:
    insurer = (insurer or "").strip()
    return "생보" if insurer in LIFE_INSURERS else "손보"


def parse_ins_period(v) -> Tuple[Optional[date], Optional[date]]:
    if pd.isna(v) or v == "":
        return (None, None)
    s = str(v).strip()
    if "~" not in s:
        return (None, None)

    a, b = [x.strip() for x in s.split("~", 1)]
    ds = de = None
    try:
        ds = datetime.strptime(a, "%Y%m%d").date() if len(a) == 8 else None
    except ValueError:
        ds = None
    try:
        de = datetime.strptime(b, "%Y%m%d").date() if len(b) == 8 else None
    except ValueError:
        de = None
    return (ds, de)