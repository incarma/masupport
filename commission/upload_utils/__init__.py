# django_ma/commission/upload_utils/__init__.py
from __future__ import annotations

"""
commission.upload_utils public API (SSOT)

- 외부에서는 commission.upload_utils 로만 import 한다.
- 실제 구현은 하위 모듈로 분리되었고, 여기서 동일 심볼을 re-export 한다.
- 기능 영향 없이 가독성/유지보수성만 개선하는 목적.
"""

# ---- Converters / constants ----
from ._convert import (  # noqa: F401
    DEC2,
    _extract_emp7_from_a,
    _norm_emp_id,
    _safe_decimal_q2,
    _to_date,
    _to_decimal,
    _to_div,
    _to_int,
)

# ---- Column detection ----
from ._detect import (  # noqa: F401
    _best_match_col,
    _detect_col,
    _detect_emp_id_col,
    _detect_refundpay_col,
    _find_col_by_aliases,
    _find_exact_or_space_removed,
    _norm_col,
)

# ---- Readers ----
from ._readers import (  # noqa: F401
    _decode_bytes_best_effort,
    _parse_first_html_table,
    _read_excel_raw_matrix,
    _read_excel_safely,
    _read_text_table,
    _read_text_table_matrix,
)

# ---- DB helpers ----
from ._db import _bulk_existing_user_ids, _update_upload_log  # noqa: F401

__all__ = [
    # constants
    "DEC2",
    # convert
    "_to_int",
    "_to_decimal",
    "_safe_decimal_q2",
    "_to_date",
    "_to_div",
    "_norm_emp_id",
    "_extract_emp7_from_a",
    # detect
    "_norm_col",
    "_best_match_col",
    "_find_col_by_aliases",
    "_detect_emp_id_col",
    "_detect_col",
    "_find_exact_or_space_removed",
    "_detect_refundpay_col",
    # readers
    "_decode_bytes_best_effort",
    "_parse_first_html_table",
    "_read_text_table",
    "_read_text_table_matrix",
    "_read_excel_safely",
    "_read_excel_raw_matrix",
    # db
    "_bulk_existing_user_ids",
    "_update_upload_log",
]