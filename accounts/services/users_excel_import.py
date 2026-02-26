# django_ma/accounts/services/users_excel_import.py
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional, Tuple


# =============================================================================
# Required Excel Columns (SSOT)
# =============================================================================

REQUIRED_COLS = [
    "사원번호",
    "성명",
    "재직여부",
    "소속부서",
    "영업가족명",
    "입사일자(사원)",
    "퇴사일자(사원)",
]


# =============================================================================
# Parsing helpers
# =============================================================================

def _to_str(v: Any) -> str:
    return ("" if v is None else str(v)).strip()


def _is_nan(v: Any) -> bool:
    return isinstance(v, float) and math.isnan(v)


def normalize_emp_id(v: Any) -> str:
    """
    엑셀 '사원번호'가 float(2533454.0)로 들어오는 케이스 정규화.
    - None/NaN → ""
    - int/정수형 float → 정수 문자열
    - "2533454.0" → "2533454"
    """
    if v is None or _is_nan(v):
        return ""

    try:
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float) and float(v).is_integer():
            return str(int(v))
    except Exception:
        pass

    s = _to_str(v)
    if not s:
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    return s


def normalize_part(v: Any) -> str:
    """
    엑셀 업로드 시 part(소속부서) 값 정규화(SSOT).

    요구사항:
      - '1인GA사업부' -> 'MA사업4부'
    """
    s = _to_str(v)
    if not s:
        return ""
    if s == "1인GA사업부":
        return "MA사업4부"
    return s


def parse_excel_date(value: Any) -> Optional[date]:
    """
    엑셀 날짜가 datetime/date/문자열 혼합으로 올 수 있어 안전 변환.
    """
    if value is None or _is_nan(value):
        return None

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    s = _to_str(value)
    if not s:
        return None

    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# =============================================================================
# Business rules (channel / grade / status)
# =============================================================================

def infer_channel(part_text: str) -> str:
    """
    규칙 1. 부문 설정
      - 소속부서에 'GA' 포함 -> 'MA부문'
      - 소속부서에 'MA' 포함 -> 'MA부문'
      - 소속부서에 'CA' 포함 -> 'CA부문'
      - 소속부서에 'PA' 포함 -> 'PA부문'
      - 그 외 -> '전략부문'
    """
    t = _to_str(part_text).upper()
    if "GA" in t or "MA" in t:
        return "MA부문"
    if "CA" in t:
        return "CA부문"
    if "PA" in t:
        return "PA부문"
    return "전략부문"


def infer_grade(name: str, employed_flag: str) -> str:
    """
    규칙 2. 권한 설정
      - 기본값: basic
      - 재직여부 == '퇴사' -> resign
      - 성명 없거나 OR 성명에 '*' 포함 -> inactive
    ✅ 우선순위: inactive 최상
    """
    n = _to_str(name)
    r = _to_str(employed_flag)

    if (not n) or ("*" in n):
        return "inactive"
    if r == "퇴사":
        return "resign"
    return "basic"


def infer_status(grade: str) -> str:
    """
    규칙 3. 상태 설정
      - grade == basic -> '재직'
      - resign/inactive -> '퇴사'
    """
    return "재직" if grade == "basic" else "퇴사"


# =============================================================================
# Worksheet picking (sheet name independent)
# =============================================================================

def _read_header(ws) -> list[str]:
    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header:
        return []
    return [_to_str(v) for v in header]


def pick_worksheet_by_required_cols(wb) -> Tuple[str, Any, list[str]]:
    """
    REQUIRED_COLS를 모두 포함한 첫 번째 '표시(visible)' 시트를 선택.
    """
    for name in wb.sheetnames:
        ws = wb[name]
        if ws.sheet_state in ("hidden", "veryHidden"):
            continue
        headers = _read_header(ws)
        if all(c in set(headers) for c in REQUIRED_COLS):
            return name, ws, headers

    # 디버깅 정보 포함
    visible = []
    for name in wb.sheetnames:
        ws = wb[name]
        if ws.sheet_state in ("hidden", "veryHidden"):
            continue
        headers = _read_header(ws)
        visible.append((name, headers[:20]))

    raise ValueError(
        "필수 컬럼을 포함한 업로드 시트를 찾을 수 없습니다. "
        f"(필수: {REQUIRED_COLS}) / 시트 목록: {wb.sheetnames} / "
        f"표시 시트 헤더(앞 20개): {visible}"
    )


# =============================================================================
# Row → defaults builder (tasks.py가 SSOT로 사용)
# =============================================================================

def build_defaults_from_row(headers: Iterable[str], row: Tuple[Any, ...]) -> Tuple[str, str, Dict[str, Any]]:
    """
    openpyxl iter_rows(values_only=True)의 row를 받아
    - emp_id
    - name
    - defaults dict
    를 생성한다.
    """
    row_data = dict(zip(list(headers), row))

    emp_id = normalize_emp_id(row_data.get("사원번호"))
    name = _to_str(row_data.get("성명"))
    employed = _to_str(row_data.get("재직여부"))
    part = normalize_part(row_data.get("소속부서"))
    branch = _to_str(row_data.get("영업가족명"))

    channel = infer_channel(part)
    grade = infer_grade(name, employed)
    status = infer_status(grade)

    enter = parse_excel_date(row_data.get("입사일자(사원)"))
    quit_ = parse_excel_date(row_data.get("퇴사일자(사원)"))

    defaults: Dict[str, Any] = {
        "name": name or "",
        "channel": channel,
        "division": "",          # 요구사항: 빈값 유지
        "part": part or "",
        "branch": branch or "",
        "grade": grade,
        "status": status,
        "enter": enter,
        "quit": quit_,
        "is_staff": False,
        "is_active": (grade != "inactive"),
        "is_superuser": False,
    }

    return emp_id, name, defaults
