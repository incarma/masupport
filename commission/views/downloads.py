# django_ma/commission/views/downloads.py
from __future__ import annotations

"""
Downloads (Excel)

리팩토링 포인트(기능 변화 없음):
- rows -> xlsx -> HttpResponse 빌더를 views/_excel_export.py로 SSOT화
- Content-Disposition 한글 파일명 처리 로직은 utils_json._set_attachment_filename을 계속 사용
"""

from datetime import datetime

from django.core.cache import cache
from django.views.decorators.http import require_GET

from ..models import ApprovalPending, EfficiencyPayExcess
from ._excel_export import rows_to_excel_response
from .utils_json import _json_error


@require_GET
def download_upload_fail_excel(request):
    """
    업로드 실패 목록 엑셀 다운로드 (token 기반)
      예) /commission/download/upload-fail/?token=xxxx
    """
    token = (request.GET.get("token") or "").strip()
    if not token:
        return _json_error("token이 필요합니다.", status=400)

    key = f"commission:upload_fail:{token}"
    payload = cache.get(key)
    if not payload:
        return _json_error("만료되었거나 존재하지 않는 token입니다.", status=404)

    content = payload.get("content")
    filename = payload.get("filename") or f"upload_fail_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    if not content:
        return _json_error("파일 데이터가 비어있습니다.", status=404)

    # 기존 동작 유지: cache에 저장된 bytes를 그대로 내려준다.
    from ._excel_export import xlsx_bytes_response
    return xlsx_bytes_response(content=content, filename=filename)


@require_GET
def download_approval_pending_excel(request):
    """
    수수료 미결현황 엑셀 다운로드
    - GET 파라미터: ym(YYYY-MM) optional
    - ym 없으면 최신 ym 기준
    """
    ym = (request.GET.get("ym") or "").strip()

    qs = ApprovalPending.objects.all().select_related("user")
    if ym:
        qs = qs.filter(ym=ym)
    else:
        latest = qs.order_by("-ym").values_list("ym", flat=True).first()
        if not latest:
            return _json_error("다운로드할 데이터가 없습니다.", status=404)
        ym = latest
        qs = qs.filter(ym=ym)

    rows = [
        {
            "ym": r.ym,
            "user_id": str(r.user_id),
            "emp_name": r.emp_name,
            "actual_pay": int(r.actual_pay or 0),
            "approval_flag": r.approval_flag,
            "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S") if r.updated_at else "",
        }
        for r in qs.order_by("user_id")
    ]
    if not rows:
        return _json_error("해당 조건의 데이터가 없습니다.", status=404)

    return rows_to_excel_response(
        rows=rows,
        sheet_name="approval_pending",
        filename=f"approval_pending_{ym}.xlsx",
    )


@require_GET
def download_efficiency_excess_excel(request):
    """
    지점효율 지급 초과현황 엑셀 다운로드
    - GET 파라미터: ym(YYYY-MM) optional
    - ym 없으면 최신 ym 기준
    """
    ym = (request.GET.get("ym") or "").strip()

    qs = EfficiencyPayExcess.objects.all().select_related("user")
    if ym:
        qs = qs.filter(ym=ym)
    else:
        latest = qs.order_by("-ym").values_list("ym", flat=True).first()
        if not latest:
            return _json_error("다운로드할 데이터가 없습니다.", status=404)
        ym = latest
        qs = qs.filter(ym=ym)

    rows = [
        {
            "ym": r.ym,
            "user_id": str(r.user_id),
            "pay_amount_sum": int(r.pay_amount_sum or 0),
            "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S") if r.updated_at else "",
        }
        for r in qs.order_by("user_id")
    ]
    if not rows:
        return _json_error("해당 조건의 데이터가 없습니다.", status=404)

    return rows_to_excel_response(
        rows=rows,
        sheet_name="efficiency_excess",
        filename=f"efficiency_excess_{ym}.xlsx",
    )