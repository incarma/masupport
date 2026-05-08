# commission/views/api_rate_example_conversion.py
from __future__ import annotations

"""
예시표 환산률/수정률 정규화 데이터 조회 API.

역할:
- rate_example_home.html의 환산률/수정률 모달에서 테이블 조회용 JSON 제공
- 현재는 생명보험/ABL 정규화 결과 조회에 사용
"""

import logging

from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.decorators import grade_required
from commission.models import RateExample, RateExampleConversionRow
from commission.views.utils_json import _json_error, _json_ok

logger = logging.getLogger(__name__)


def _format_decimal(value) -> str:
    """
    Decimal 값을 과학적 표기법 없이 문자열로 변환한다.
    예: Decimal("2.7E+2") → "270"
    """
    if value is None:
        return ""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _format_dt(value) -> str:
    """마지막 업데이트 일시 표시용 포맷."""
    if not value:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")


@login_required
@grade_required("superuser", forbidden_template=None)
@require_GET
def rate_example_conversion_list(request):
    insurer_type = (request.GET.get("insurer_type") or "").strip()
    insurer = (request.GET.get("insurer") or "").strip()
    category = RateExample.CAT_CONV

    if insurer_type not in (RateExample.TYPE_LIFE, RateExample.TYPE_NONLIFE):
        return _json_error("손생구분 값이 올바르지 않습니다.", status=400)
    if not insurer:
        return _json_error("보험사를 선택해 주세요.", status=400)

    qs = (
        RateExampleConversionRow.objects
        .select_related("source_file", "source_file__uploaded_by")
        .filter(insurer_type=insurer_type, category=category, insurer=insurer)
        .order_by("coverage_type", "product_name", "plan_type", "pay_period", "id")
    )

    # ── 마지막 업데이트 정보 ─────────────────────────────────────
    # 같은 보험사/구분 데이터는 최신 업로드 파일 기준으로 교체되므로
    # source_file.created_at 최신값을 화면의 "마지막 업데이트"로 사용한다.
    latest_row = (
        qs.order_by("-source_file__created_at", "-source_file_id", "-id")
        .first()
    )
    latest_file = latest_row.source_file if latest_row else None
    latest_uploader = getattr(latest_file, "uploaded_by", None) if latest_file else None

    rows = [
        {
            "id": row.id,
            "insurer": row.insurer,
            "coverage_type": row.coverage_type,
            "strategy_flag": row.strategy_flag,
            "product_name": row.product_name,
            "plan_type": row.plan_type,
            "pay_period": row.pay_period,
            "year1": _format_decimal(row.year1),
            "year2": _format_decimal(row.year2),
            "year3": _format_decimal(row.year3),
            "year4": _format_decimal(row.year4),
            "source_sheet": row.source_sheet,
            "source_row_no": row.source_row_no,
        }
        for row in qs
    ]

    return _json_ok(
        "조회되었습니다.",
        data={
            "rows": rows,
            "count": len(rows),
            "last_updated_at": _format_dt(getattr(latest_file, "created_at", None)),
            "last_updated_by": getattr(latest_uploader, "name", "") or "",
            "source_file_name": getattr(latest_file, "original_name", "") or "",
        },
    )