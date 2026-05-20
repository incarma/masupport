# django_ma/commission/services/rate_example_normalizers/_common/decimal.py
from __future__ import annotations

"""
RateExample parser 공통 Decimal helper.

핵심 원칙:
- 생명보험 환산율 Excel percent format은 화면 표시 기준 백분율 수치로 저장한다.
  예: openpyxl value=0.7, number_format='0%' → Decimal('70')
- 손해보험 수정률 raw 그대로 저장, PDF ×12, 지급률 /0.97 같은 특수 정책은
  이 공통 helper로 억지 통합하지 않는다.
"""

from decimal import Decimal, InvalidOperation
from typing import Any


def decimal_from_text(value: Any) -> Decimal | None:
    """
    문자열/숫자를 Decimal로 변환한다.

    처리:
    - comma 제거
    - percent 기호 제거
    - 공란/대시 값은 None
    """
    if value is None:
        return None

    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none"} or text in {"-", "–", "—"}:
        return None

    text = text.replace("%", "").replace("％", "").strip()
    if not text:
        return None

    try:
        return Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        return None


def decimal_percent_cell(cell, *, normalize_integral: bool = False) -> Decimal | None:
    """
    Excel 셀을 백분율 표시 기준 Decimal로 변환한다.

    정책:
    - 셀 값 문자열에 '%'가 직접 있으면 표시 숫자로 본다.
    - number_format에 '%'가 있고 cell.value가 숫자이면 ×100 보정한다.
    - normalize_integral=True이면 Decimal('70.0') → Decimal('70') 형태로 정리한다.

    적용 대상:
    - life_dongyang.py
    - life_met.py
    - 향후 같은 정책을 가진 생보 parser
    """
    value = getattr(cell, "value", None)
    dec = decimal_from_text(value)
    if dec is None:
        return None

    number_format = str(getattr(cell, "number_format", "") or "")
    value_text = str(value or "")

    if "%" in number_format and "%" not in value_text:
        dec *= Decimal("100")

    if normalize_integral and dec == dec.to_integral():
        return dec.normalize()

    return dec


def decimal_percent_value(
    value: Any,
    *,
    number_format: str = "",
    normalize_integral: bool = False,
    scale_small_percent_text: bool = False,
) -> Decimal | None:
    """
    셀 객체가 아니라 value + number_format을 따로 받는 백분율 Decimal helper.

    적용 대상:
    - parser 내부에서 이미 cell.value와 cell.number_format을 분리해 전달하는 코드
    - 예: life_KDB.py

    정책:
    - 문자열 "100%"는 Decimal("100")
    - 숫자 1.0 + number_format "%"는 Decimal("100")
    - 숫자 100 + General은 Decimal("100")
    - scale_small_percent_text=True이면 기존 신한 parser 정책처럼
      문자열 "0.8%" 계열도 Decimal("80")으로 보정한다.
    """
    dec = decimal_from_text(value)
    if dec is None:
        return None

    value_text = str(value or "")
    has_percent_text = "%" in value_text or "％" in value_text

    if scale_small_percent_text and has_percent_text and abs(dec) <= Decimal("10"):
        dec *= Decimal("100")
    elif "%" in str(number_format or "") and not has_percent_text:
        dec *= Decimal("100")

    if normalize_integral and dec == dec.to_integral():
        return dec.normalize()

    return dec