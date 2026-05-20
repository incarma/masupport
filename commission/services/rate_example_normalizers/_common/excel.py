# django_ma/commission/services/rate_example_normalizers/_common/excel.py
from __future__ import annotations

"""
RateExample Excel parser 공통 helper.

주의:
- worksheet 자체를 unmerge 하거나 값을 직접 쓰지 않는다.
- 병합 셀 값을 parser 내부 lookup으로만 전파한다.
"""

from typing import Any

from openpyxl.worksheet.worksheet import Worksheet


def build_merged_value_map(ws: Worksheet) -> dict[tuple[int, int], Any]:
    """
    병합 셀의 좌상단 값을 병합 범위 전체 좌표에 매핑한다.
    """
    merged_map: dict[tuple[int, int], Any] = {}

    for merged_range in ws.merged_cells.ranges:
        top_left = ws.cell(
            row=merged_range.min_row,
            column=merged_range.min_col,
        ).value

        for row_no in range(merged_range.min_row, merged_range.max_row + 1):
            for col_no in range(merged_range.min_col, merged_range.max_col + 1):
                merged_map[(row_no, col_no)] = top_left

    return merged_map


def cell_value_with_merged(
    ws: Worksheet,
    merged_map: dict[tuple[int, int], Any],
    row_no: int,
    col_no: int,
) -> Any:
    """
    일반 셀/병합 셀 값을 동일하게 읽는다.

    우선순위:
    1. 실제 셀 값
    2. 병합 map 전파값
    """
    value = ws.cell(row=row_no, column=col_no).value
    if value not in (None, ""):
        return value
    return merged_map.get((row_no, col_no))