# django_ma/commission/upload_utils/_detect.py

from __future__ import annotations

import re
from typing import Optional, Sequence

import pandas as pd

# =========================================================
# Column detection helpers
# =========================================================
def _norm_col(s: str) -> str:
    """컬럼명 normalize: 소문자/특수문자 제거/0→o(보증(0) 케이스)"""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"[^0-9a-z가-힣]", "", s)
    s = s.replace("0", "o")
    return s


def _best_match_col(
    df_cols: Sequence,
    required_tokens: Sequence[str],
    optional_tokens: Optional[Sequence[str]] = None,
    ban_tokens: Optional[Sequence[str]] = None,
):
    """df columns 중 required token 포함 + optional token 점수로 best match."""
    optional_tokens = optional_tokens or []
    ban_tokens = ban_tokens or []

    best = None
    best_score = -10**9

    for c in df_cols:
        nc = _norm_col(c)

        if any(bt and bt in nc for bt in ban_tokens):
            continue
        if not all(rt and rt in nc for rt in required_tokens):
            continue

        score = 100 * len(required_tokens)
        for ot in optional_tokens:
            if ot and ot in nc:
                score += 15
        score -= max(0, len(nc) - 20)

        if score > best_score:
            best_score = score
            best = c

    return best


def _find_col_by_aliases(df: pd.DataFrame, alias_groups, ban_groups=None):
    """여러 alias 후보 중 하나를 찾아 컬럼명 반환."""
    df_cols = list(df.columns)
    ban_groups = ban_groups or []

    ban_tokens = []
    for bg in ban_groups:
        ban_tokens += [_norm_col(x) for x in bg]

    for grp in alias_groups:
        req = [_norm_col(x) for x in grp]
        found = _best_match_col(df_cols, required_tokens=req, optional_tokens=[], ban_tokens=ban_tokens)
        if found:
            return found
    return None


def _detect_emp_id_col(df: pd.DataFrame):
    """사번/사원코드/등록번호/FC코드 컬럼 자동 탐지."""
    alias_groups = [
        ["사번"],
        ["사원", "코드"],
        ["사원", "번호"],
        ["사원번호"],
        ["등록", "번호"],
        ["등록번호"],
        ["fc", "코드"],
        ["설계사", "코드"],
        ["설계사", "번호"],
        ["id"],
    ]
    ban_groups = [["계약"], ["증권"], ["주민"], ["연락"], ["전화"], ["휴대"], ["메일"], ["email"]]
    return _find_col_by_aliases(df, alias_groups, ban_groups=ban_groups)


def _detect_col(
    df: pd.DataFrame,
    must_include: Sequence[str],
    any_include: Sequence[str] = (),
    ban: Sequence[str] = (),
):
    """
    DataFrame에서 컬럼명을 토큰 기반으로 탐지한다.

    - must_include: 모두 포함되어야 함 (AND)
    - any_include: 하나라도 포함되면 가산점 (OR)
    - ban: 포함되면 제외

    반환: 원본 df.columns 중 매칭된 컬럼명 (없으면 None)
    """
    if df is None or df.empty:
        return None

    required = [_norm_col(x) for x in (must_include or []) if x]
    optional = [_norm_col(x) for x in (any_include or []) if x]
    ban_tokens = [_norm_col(x) for x in (ban or []) if x]

    if not required:
        return None

    return _best_match_col(list(df.columns), required_tokens=required, optional_tokens=optional, ban_tokens=ban_tokens)


def _find_exact_or_space_removed(columns: Sequence, target: str):
    """
    컬럼명이 '정확히' 맞거나(공백/특수문자 제거 후) 동일하면 컬럼명을 반환한다.
    """
    if columns is None:
        return None
    try:
        if len(columns) == 0:
            return None
    except TypeError:
        columns = list(columns)
        if len(columns) == 0:
            return None

    if target is None:
        return None

    target_raw = str(target).strip()
    if not target_raw:
        return None

    # 1) 완전 일치 우선
    for c in columns:
        if str(c).strip() == target_raw:
            return c

    # 2) 공백 제거 일치
    def strip_spaces(x: str) -> str:
        return re.sub(r"\s+", "", x.strip())

    t2 = strip_spaces(target_raw)
    for c in columns:
        if strip_spaces(str(c)) == t2:
            return c

    # 3) 더 강한 normalize(공백/특수문자 제거) 일치
    t3 = _norm_col(target_raw)
    for c in columns:
        if _norm_col(str(c)) == t3:
            return c

    return None


def _detect_refundpay_col(df: pd.DataFrame, flag: Optional[str], kind: str, line: str):
    """
    환수/지급예상 업로드 컬럼 탐지 SSOT.

    - flag: None(일반), "o"(보증 O), "x"(보증 X)
    - kind: "refund" | "pay"
    - line: "ns"(손보) | "ls"(생보) | "total"(합계)
    """
    if df is None or df.empty:
        return None

    kind_tokens = ("환수",) if kind == "refund" else ("지급",)

    if line == "ns":
        line_tokens = ("손", "손보")
        ban_line = ("생", "생보")
    elif line == "ls":
        line_tokens = ("생", "생보")
        ban_line = ("손", "손보")
    else:
        line_tokens = ("합", "합계", "total")
        ban_line = ()

    flag_tokens = ()
    if flag == "o":
        flag_tokens = ("보증", "o")
    elif flag == "x":
        flag_tokens = ("보증", "x")

    line_rep = line_tokens[0] if line_tokens else ""
    required = tuple([*kind_tokens, *(flag_tokens or ()), line_rep] if line_rep else [*kind_tokens, *(flag_tokens or ())])
    optional = tuple(set([*line_tokens, *kind_tokens, *(flag_tokens or ())]))
    ban = tuple(set(ban_line))

    return _detect_col(df, must_include=required, any_include=optional, ban=ban)