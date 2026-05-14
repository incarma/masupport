# commission/views/api_rate_example_pay.py
from __future__ import annotations

"""
예시표 지급률 정규화 데이터 조회 API.

파일 위치:
    commission/views/api_rate_example_pay.py

역할:
- rate_example_home.html 의 지급률 확인 모달에서 전체 보험사×상품군 JSON 제공
- insurer_type=life 고정 (현재 생보만 지원)
- superuser 전용

보안/운영 원칙:
- @grade_required("superuser") 고정 — 변경 금지
- 파일 URL 직접 노출 없음 (조회 전용 API)
- select_related로 N+1 방지
"""

import logging

from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import grade_required
from commission.models import RateExample
from commission.views.utils_json import _json_ok

logger = logging.getLogger(__name__)


# ── 포맷 헬퍼 ─────────────────────────────────────────────────────────────────

def _fmt(value) -> str:
    """
    Decimal 수치 → 문자열 변환.
    None  → ""
    소수점 뒤 불필요한 0 제거 (예: 222.5900 → "222.59")
    0.0000 → "0"
    """
    if value is None:
        return ""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _format_dt(value) -> str:
    """DateTimeField → "YYYY-MM-DD HH:MM" 문자열. None이면 ""."""
    if not value:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")


# ── 지급률 전체 조회 API ──────────────────────────────────────────────────────

@login_required
@grade_required("superuser", forbidden_template=None)
@require_GET
def rate_example_pay_list(request):
    """
    지급률 정규화 데이터 전체 조회.

    Query params: 없음 (insurer_type=life 고정)

    응답 구조:
    {
      "ok": true,
      "data": {
        "rows": [
          {
            "insurer": "ABL",
            "tier": "5천만↑",
            "coverage_type": "종신/CI",
            "col_a": "222.59",   // 초회
            "col_b": "0",        // 1차년
            "col_c": "47.92",    // 13회
            "col_d": "47.92",    // 2차년구간
            "col_e": "95.86",    // 3차년구간
            "col_f": "95.86"     // 4차년구간 (없으면 "")
          }, ...
        ],
        "count": 240,
        "last_updated_at": "2026-05-11 14:30",
        "last_updated_by": "홍길동",
        "source_file_name": "지급률.xlsx"
      }
    }
    """

    from commission.models import RateExamplePayRow  # noqa: PLC0415

    insurer_type = (request.GET.get("insurer_type") or RateExample.TYPE_LIFE).strip()
    if insurer_type == "nonlife":
        insurer_type = RateExample.TYPE_FIRE
    if insurer_type not in {RateExample.TYPE_LIFE, RateExample.TYPE_FIRE}:
        insurer_type = RateExample.TYPE_LIFE

    # N+1 방지: source_file → uploaded_by 한 번에 fetch
    qs = (
        RateExamplePayRow.objects
        .select_related("source_file", "source_file__uploaded_by")
        .filter(insurer_type=insurer_type, category="pay")
        .order_by("insurer", "tier", "source_row_no")
    )

    # ── 마지막 업로드 정보 (가장 최근 파일 기준) ─────────────────────────────
    latest_row = (
        qs.order_by("-source_file__created_at", "-source_file_id", "-id")
        .first()
    )
    latest_file     = latest_row.source_file if latest_row else None
    latest_uploader = getattr(latest_file, "uploaded_by", None) if latest_file else None

    # ── rows 직렬화 ──────────────────────────────────────────────────────────
    rows = [
        {
            "insurer":       row.insurer,
            "tier":          row.tier,
            "coverage_type": row.coverage_type,
            "col_first": _fmt(row.col_first),
            "col_yr1":   _fmt(row.col_yr1),
            "col_m13":   _fmt(row.col_m13),
            "col_yr2":   _fmt(row.col_yr2),
            "col_yr3":   _fmt(row.col_yr3),
            "col_m36":   _fmt(row.col_m36),   # None이면 "" — JS에서 "-" 렌더
            "col_m37":   _fmt(row.col_m37),   # None이면 "" — JS에서 "-" 렌더
            "col_yr4":   _fmt(row.col_yr4),   # None이면 "" — JS에서 "-" 렌더
        }
        for row in qs
    ]

    return _json_ok(
        "조회되었습니다.",
        data={
            "rows":             rows,
            "count":            len(rows),
            "last_updated_at":  _format_dt(getattr(latest_file, "created_at", None)),
            "last_updated_by":  getattr(latest_uploader, "name", "") or "",
            "source_file_name": getattr(latest_file, "original_name", "") or "",
        },
    )


# ── 지급률 정규화 데이터 전체 초기화 ────────────────────────────────────────
@login_required
@grade_required("superuser", forbidden_template=None)
@require_POST
def rate_example_pay_reset(request):
    """
    지급률 정규화 데이터(RateExamplePayRow) 전체 삭제.
    지급률은 전사 단일 파일이므로 보험사 단위가 아닌 전체 삭제.
    """
    from commission.models import RateExamplePayRow  # noqa: PLC0415

    insurer_type = (request.POST.get("insurer_type") or RateExample.TYPE_LIFE).strip()
    if insurer_type == "nonlife":
        insurer_type = RateExample.TYPE_FIRE
    if insurer_type not in {RateExample.TYPE_LIFE, RateExample.TYPE_FIRE}:
        insurer_type = RateExample.TYPE_LIFE

    deleted_count, _ = RateExamplePayRow.objects.filter(
        insurer_type=insurer_type,
        category="pay",
    ).delete()

    try:
        from audit.constants import ACTION  # noqa: PLC0415
        from audit.services import log_action  # noqa: PLC0415
        log_action(
            request,
            ACTION.COMMISSION_RATE_EXAMPLE_DELETE,   # 가장 근접한 기존 ACTION 재사용
            meta={
                "action_detail": "pay_reset",
                "insurer_type": insurer_type,
                "deleted_count": deleted_count,
            },
            success=True,
        )
    except Exception:
        logger.exception("rate_example pay_reset audit log failed")

    return _json_ok(
        f"지급률 데이터 {deleted_count}건을 삭제했습니다.",
        data={"deleted_count": deleted_count},
    )