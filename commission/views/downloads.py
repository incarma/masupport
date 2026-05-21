# django_ma/commission/views/downloads.py
from __future__ import annotations

"""
Downloads (Excel)

리팩토링 포인트(기능 변화 없음):
- rows -> xlsx -> HttpResponse 빌더를 views/_excel_export.py로 SSOT화
- Content-Disposition 한글 파일명 처리 로직은 utils_json._set_attachment_filename을 계속 사용
"""

from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.views.decorators.http import require_GET

from accounts.decorators import grade_required
from commission.upload_handlers.approval import APPROVAL_PENDING_MIN_ACTUAL_PAY
from ..models import ApprovalPending, EfficiencyPayExcess
from ._excel_export import rows_to_excel_response, xlsx_bytes_response
from .utils_json import _json_error


NO_DOWNLOAD_DATA_MESSAGE = "다운로드할 데이터가 없습니다."
NO_MATCHED_DATA_MESSAGE = "해당 조건의 데이터가 없습니다."


def _get_requested_ym(request) -> str:
    """GET ym 파라미터를 기존 정책 그대로 읽는다."""
    return (request.GET.get("ym") or "").strip()


def _filter_by_requested_or_latest_ym(qs, ym: str):
    """
    다운로드 공통 월도 필터.
    - ym이 있으면 해당 ym 필터
    - ym이 없으면 최신 ym fallback
    """
    if ym:
        return ym, qs.filter(ym=ym)

    latest = qs.order_by("-ym").values_list("ym", flat=True).first()
    if not latest:
        return "", None

    return latest, qs.filter(ym=latest)


def _format_updated_at(value) -> str:
    """엑셀 row의 updated_at 문자열 포맷을 기존과 동일하게 유지."""
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _excel_download_response(*, rows, sheet_name: str, filename: str):
    """
    공통 엑셀 다운로드 응답.

    기능 변화 없음:
    - rows가 비어 있으면 기존과 동일하게 404 JSON 반환
    - rows_to_excel_response() SSOT 유지
    """
    if not rows:
        return _json_error(NO_MATCHED_DATA_MESSAGE, status=404)

    return rows_to_excel_response(
        rows=rows,
        sheet_name=sheet_name,
        filename=filename,
    )


def _approval_pending_rows(qs):
    """수수료 미결현황 queryset을 기존 엑셀 row dict 구조로 변환."""
    return [
        {
            "ym": r.ym,
            "user_id": str(r.user_id),
            "emp_name": r.emp_name,
            "actual_pay": int(r.actual_pay or 0),
            "approval_flag": r.approval_flag,
            "updated_at": _format_updated_at(r.updated_at),
        }
        for r in qs.order_by("user_id")
    ]


def _efficiency_excess_rows(qs):
    """지점효율 지급 초과현황 queryset을 기존 엑셀 row dict 구조로 변환."""
    return [
        {
            "ym": r.ym,
            "user_id": str(r.user_id),
            "pay_amount_sum": int(r.pay_amount_sum or 0),
            "updated_at": _format_updated_at(r.updated_at),
        }
        for r in qs.order_by("user_id")
    ]


def _can_download_fail_payload(request, payload: dict) -> bool:
    """
    실패 엑셀 token 다운로드 권한.
    - 신규 token: owner_id가 있으면 업로드 실행자 본인만 허용
    - legacy token: owner_id가 없으면 superuser만 허용
    """
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return False

    grade = (getattr(user, "grade", "") or "").strip()
    if grade != "superuser" and not getattr(user, "is_superuser", False):
        return False

    owner_id = str((payload or {}).get("owner_id") or "").strip()
    if owner_id:
        return owner_id == str(getattr(user, "pk", "") or "")

    return True


@require_GET
@login_required
@grade_required("superuser")
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

    if not _can_download_fail_payload(request, payload):
        return _json_error("다운로드 권한이 없습니다.", status=403)

    content = payload.get("content")
    filename = payload.get("filename") or f"upload_fail_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    if not content:
        return _json_error("파일 데이터가 비어있습니다.", status=404)

    # 기존 동작 유지: cache에 저장된 bytes를 그대로 내려준다.
    return xlsx_bytes_response(content=content, filename=filename)


@require_GET
@login_required
@grade_required("superuser")
def download_approval_pending_excel(request):
    """
    수수료 미결현황 엑셀 다운로드
    - GET 파라미터: ym(YYYY-MM) optional
    - ym 없으면 최신 ym 기준
    """
    ym = _get_requested_ym(request)
    qs = (
        ApprovalPending.objects
        .filter(
            approval_flag="N",
            actual_pay__gte=APPROVAL_PENDING_MIN_ACTUAL_PAY,
        )
        .select_related("user")
    )
    ym, qs = _filter_by_requested_or_latest_ym(qs, ym)
    if qs is None:
        return _json_error(NO_DOWNLOAD_DATA_MESSAGE, status=404)

    return _excel_download_response(
        rows=_approval_pending_rows(qs),
        sheet_name="approval_pending",
        filename=f"approval_pending_{ym}.xlsx",
    )


@require_GET
@login_required
@grade_required("superuser")
def download_efficiency_excess_excel(request):
    """
    지점효율 지급 초과현황 엑셀 다운로드
    - GET 파라미터: ym(YYYY-MM) optional
    - ym 없으면 최신 ym 기준
    """
    ym = _get_requested_ym(request)
    qs = EfficiencyPayExcess.objects.all().select_related("user")
    ym, qs = _filter_by_requested_or_latest_ym(qs, ym)
    if qs is None:
        return _json_error(NO_DOWNLOAD_DATA_MESSAGE, status=404)

    return _excel_download_response(
        rows=_efficiency_excess_rows(qs),
        sheet_name="efficiency_excess",
        filename=f"efficiency_excess_{ym}.xlsx",
    )