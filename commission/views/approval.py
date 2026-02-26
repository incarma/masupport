# django_ma/commission/views/approval.py
from __future__ import annotations

import re

from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from commission.upload_handlers import _handle_upload_commission_approval, _handle_upload_efficiency_pay_excess
from commission.upload_utils import _read_excel_raw_matrix

from ..models import ApprovalExcelUploadLog, ApprovalPending, EfficiencyPayExcess
from .utils_fail_excel import store_fail_rows_as_excel
from .utils_json import _json_error, _json_ok

# =============================================================================
# YM helpers
# =============================================================================


def _pad2(n: int) -> str:
    return f"{n:02d}"


def _split_ym(ym: str) -> tuple[str, str]:
    """
    Accept ym formats:
      - 'YYYY-MM'  (e.g. 2026-02)
      - 'YYYYMM'   (e.g. 202602)
    Return (year, month) as strings or raise ValueError.
    """
    s = (ym or "").strip()
    if not s:
        raise ValueError("연/월을 선택해주세요.")

    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m:
        return m.group(1), m.group(2)

    m = re.fullmatch(r"(\d{4})(\d{2})", s)
    if m:
        return m.group(1), m.group(2)

    raise ValueError("연/월 형식이 올바르지 않습니다. (예: 2026-02)")


def _validate_ym(year: str, month: str) -> str:
    if not (year or "").isdigit():
        raise ValueError("연도를 선택해주세요.")
    if not (month or "").isdigit():
        raise ValueError("월을 선택해주세요.")

    y = int(year)
    m = int(month)
    if m < 1 or m > 12:
        raise ValueError("월은 1~12 범위여야 합니다.")

    return f"{y}-{_pad2(m)}"


def _resolve_ym(year: str, month: str, ym_param: str) -> tuple[str, str, str]:
    """
    프론트는 보통 ym(YYYY-MM)만 보내므로:
      1) year/month가 있으면 그대로 사용
      2) 없으면 ym_param에서 분해하여 보완
    Return (ym, year, month)
    """
    if year and month:
        ym = _validate_ym(year, month)
        return ym, year, month

    y, m = _split_ym(ym_param)
    year = year or y
    month = month or m
    ym = _validate_ym(year, month)
    return ym, year, month


# =============================================================================
# Common upload SSOT (approval/efficiency)
# =============================================================================


def _common_upload(*, request, ym: str, part: str, kind: str, file_path: str, original_name: str) -> tuple[int, int, dict]:
    """
    approval/efficiency 공통 업로드 SSOT

    Steps:
      1) raw matrix로 row_count 산정
      2) 기존 데이터(ym + part scope) 삭제
      3) handler 실행
      4) ApprovalExcelUploadLog update_or_create
    """
    df_raw = _read_excel_raw_matrix(file_path, original_name=original_name, skiprows=0, header_none=True)
    row_count = int(len(df_raw.index)) if df_raw is not None else 0

    # -------------------------------------------------------------------------
    # 1) delete old rows (ym + part scope)
    # -------------------------------------------------------------------------
    if kind == "approval":
        del_qs = ApprovalPending.objects.filter(ym=ym)
        if part:
            del_qs = del_qs.filter(user__part=part)
        del_qs.delete()

        # ---------------------------------------------------------------------
        # 2) handler
        # ---------------------------------------------------------------------
        result = _handle_upload_commission_approval(
            file_path=file_path,
            original_name=original_name,
            ym=ym,
            part=part,
        )
        inserted = int(result.get("inserted_or_updated") or 0)

    elif kind == "efficiency":
        del_qs = EfficiencyPayExcess.objects.filter(ym=ym)
        if part:
            del_qs = del_qs.filter(user__part=part)
        del_qs.delete()

        result = _handle_upload_efficiency_pay_excess(
            file_path=file_path,
            original_name=original_name,
            ym=ym,
            part=part,
        )
        inserted = int(result.get("inserted_or_updated") or 0)

    else:
        raise ValueError("구분(kind)을 선택해주세요. (efficiency/approval)")

    # -------------------------------------------------------------------------
    # 3) upload log
    # -------------------------------------------------------------------------
    ApprovalExcelUploadLog.objects.update_or_create(
        ym=ym,
        part=part,
        kind=kind,
        defaults={
            "uploaded_by": request.user,
            "row_count": row_count,
            "file_name": (original_name or "")[:255],
        },
    )

    return row_count, inserted, result


def _build_fail_token(*, ym: str, part: str, kind: str, result: dict) -> tuple[str, list]:
    missing_sample = result.get("missing_sample", []) or []
    if not missing_sample:
        return "", []

    rows = [{"user_id": uid, "reason": "사용자 미존재 또는 part 스코프 제외"} for uid in missing_sample]
    token = store_fail_rows_as_excel(
        rows=rows,
        filename=f"upload_fail_{ym}_{part or 'ALL'}_{kind}.xlsx",
    )
    return token, missing_sample


def _safe_delete(fs: FileSystemStorage, saved_name: str) -> None:
    try:
        fs.delete(saved_name)
    except Exception:
        pass


# =============================================================================
# API
# =============================================================================


@csrf_exempt
@require_POST
@grade_required("superuser")
def approval_upload_excel(request):
    ym_param = (request.POST.get("ym") or request.GET.get("ym") or "").strip()
    year = (request.POST.get("year") or request.GET.get("year") or "").strip()
    month = (request.POST.get("month") or request.GET.get("month") or "").strip()
    part = (request.POST.get("part") or request.GET.get("part") or "").strip()
    kind = (request.POST.get("kind") or request.GET.get("kind") or "").strip()
    excel_file = request.FILES.get("excel_file")

    try:
        ym, year, month = _resolve_ym(year, month, ym_param)
    except ValueError as ve:
        return _json_error(str(ve), status=400)

    if kind not in ("efficiency", "approval"):
        return _json_error("구분(kind)을 선택해주세요. (efficiency/approval)", status=400)
    if not excel_file:
        return _json_error("엑셀 파일이 전달되지 않았습니다.", status=400)

    fs = FileSystemStorage()
    saved_name = fs.save(excel_file.name, excel_file)
    file_path = fs.path(saved_name)

    try:
        with transaction.atomic():
            row_count, inserted, result = _common_upload(
                request=request,
                ym=ym,
                part=part,
                kind=kind,
                file_path=file_path,
                original_name=excel_file.name,
            )

        fail_token, missing_sample = _build_fail_token(ym=ym, part=part, kind=kind, result=result)

        return _json_ok(
            "✅ 업로드가 완료되었습니다.",
            ym=ym,
            part=part,
            kind=kind,
            row_count=row_count,
            file_name=excel_file.name,
            inserted=inserted,
            missing_users=int(result.get("missing_users") or 0),
            missing_sample=missing_sample,
            fail_token=fail_token,
            fail_download_url=(f"/commission/download/upload-fail/?token={fail_token}" if fail_token else ""),
        )

    except ValueError as ve:
        return _json_error(str(ve), status=400)
    except Exception as e:
        return _json_error(f"⚠️ 업로드 실패: {e}", status=500)
    finally:
        _safe_delete(fs, saved_name)