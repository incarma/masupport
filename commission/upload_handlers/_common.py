# django_ma/commission/upload_handlers/_common.py
from __future__ import annotations

"""
commission.upload_handlers 공통 helper.

목적:
- approval.py / efficiency.py 등 업로드 핸들러에서 반복되는
  raw cell 정규화와 결과 dict 생성을 한 곳으로 모은다.
- 업로드 registry, DB 저장 정책, row 처리 성능은 변경하지 않는다.
"""

from dataclasses import dataclass
from typing import Any

from commission.upload_utils import _is_empty_like


def safe_cell_text(value: Any) -> str:
    """
    raw matrix cell을 비교/저장 가능한 문자열로 정규화한다.

    보존 정책:
    - None / NaN / "nan" / "none" / "-" 계열은 공란 처리한다.
    - 그 외 값은 str(value).strip()만 적용한다.
    """
    if _is_empty_like(value):
        return ""
    return str(value).strip()


@dataclass(frozen=True)
class UploadHandlerResult:
    """
    업로드 핸들러 표준 결과.

    기존 view 계약을 유지하기 위해 최종 반환은 dict로 변환한다.
    """

    inserted_or_updated: int = 0
    missing_users: int = 0
    missing_sample: list[str] | None = None
    excluded_rows: list[dict[str, object]] | None = None
    excluded_summary: dict[str, int] | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "inserted_or_updated": self.inserted_or_updated,
            "missing_users": self.missing_users,
            "missing_sample": self.missing_sample or [],
        }
        if self.excluded_rows is not None:
            result["excluded_rows"] = self.excluded_rows
        if self.excluded_summary is not None:
            result["excluded_summary"] = self.excluded_summary
        return result


def upload_result(
    *,
    inserted_or_updated: int = 0,
    missing_users: int = 0,
    missing_sample: list[str] | None = None,
    excluded_rows: list[dict[str, object]] | None = None,
    excluded_summary: dict[str, int] | None = None,
) -> dict[str, object]:
    """
    기존 업로드 handler return dict 생성 helper.

    반환 key는 기존 프론트/뷰 계약이므로 변경 금지:
    - inserted_or_updated
    - missing_users
    - missing_sample
    신규 approval 제외 리포트용 key:
    - excluded_rows
    - excluded_summary
    """
    return UploadHandlerResult(
        inserted_or_updated=inserted_or_updated,
        missing_users=missing_users,
        missing_sample=missing_sample or [],
        excluded_rows=excluded_rows,
        excluded_summary=excluded_summary,
    ).as_dict()