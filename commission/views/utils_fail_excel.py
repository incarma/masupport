# django_ma/commission/views/utils_fail_excel.py
from __future__ import annotations

import io
import uuid
from typing import Any

from django.core.cache import cache

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

FAIL_TTL_SECONDS = 60 * 60  # 1 hour


def store_fail_rows_as_excel(
    *,
    rows: list[dict[str, Any]],
    filename: str,
    owner_id: str = "",
) -> str:
    """
    실패 rows를 xlsx로 만들어 cache에 저장하고 token 반환.

    rows 예:
      [{"user_id": "...", "reason": "...", ...}, ...]

    owner_id:
      token 탈취/공유 시 다운로드 범위를 제한하기 위한 업로드 실행자 PK.
      과거 token과의 호환을 위해 빈 값도 허용하지만,
      신규 호출부는 반드시 request.user.pk를 넘긴다.
    """
    if not rows:
        return ""

    if pd is None:
        # 현재 프로젝트는 pandas/openpyxl 사용 전제로 보이므로 빈 토큰 반환.
        return ""

    df = pd.DataFrame(rows)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="fail_rows")

    token = uuid.uuid4().hex
    key = f"commission:upload_fail:{token}"
    cache.set(
        key,
        {
            "content": out.getvalue(),
            "filename": filename,
            "owner_id": str(owner_id or ""),
        },
        timeout=FAIL_TTL_SECONDS,
    )
    return token


__all__ = ["store_fail_rows_as_excel", "FAIL_TTL_SECONDS"]
