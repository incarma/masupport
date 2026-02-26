# django_ma/commission/views/_excel_export.py
from __future__ import annotations

"""
Excel export helpers (views layer SSOT)

목표:
- downloads.py 등에서 반복되는 "rows -> pandas DataFrame -> xlsx -> HttpResponse" 패턴 공통화
- 기능 변화 없이, 재사용성과 가독성만 개선

주의:
- 기존과 동일하게 pandas + openpyxl 엔진을 사용
- 파일명 세팅은 utils_json._set_attachment_filename을 그대로 사용
"""

import io
from typing import Any, Iterable, Mapping

from django.http import HttpResponse

from .utils_json import _set_attachment_filename

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def rows_to_xlsx_bytes(*, rows: list[dict[str, Any]], sheet_name: str) -> bytes:
    """
    rows(list[dict]) -> xlsx bytes

    - rows가 비어있으면 빈 엑셀을 만들지 않고 빈 bytes 반환(호출부에서 404 처리하는 기존 패턴 유지 권장)
    """
    if not rows:
        return b""

    if pd is None:
        raise RuntimeError("pandas is not available")

    df = pd.DataFrame(rows)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return out.getvalue()


def xlsx_bytes_response(*, content: bytes, filename: str) -> HttpResponse:
    """
    xlsx bytes -> HttpResponse(attachment)
    """
    resp = HttpResponse(content, content_type=XLSX_MIME)
    _set_attachment_filename(resp, filename)
    return resp


def rows_to_excel_response(*, rows: list[dict[str, Any]], sheet_name: str, filename: str) -> HttpResponse:
    """
    one-shot helper:
    rows -> xlsx bytes -> response
    """
    content = rows_to_xlsx_bytes(rows=rows, sheet_name=sheet_name)
    return xlsx_bytes_response(content=content, filename=filename)