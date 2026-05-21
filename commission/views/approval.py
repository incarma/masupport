# django_ma/commission/views/approval.py
from __future__ import annotations

"""
Approval/Efficiency Excel Upload API (superuser only)

리팩토링 포인트(기능 변화 없음):
- YM 파싱/검증 로직을 views/_ym.py로 SSOT화
- 업로드 임시파일 저장/삭제를 views/_files.py로 SSOT화
- 공통 업로드(삭제→핸들러→로그 upsert) 흐름은 그대로 유지
"""

from django.conf import settings
from django.db import transaction
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from board.services.rate_limit import check_rate_limit, rate_limited_json
from commission.upload_handlers import (
    _handle_upload_commission_approval,
    _handle_upload_efficiency_pay_excess,
)
from commission.upload_utils import _read_excel_raw_matrix

from audit.services import log_action
from audit.constants import ACTION

from ..models import ApprovalExcelUploadLog, ApprovalPending, EfficiencyPayExcess
from ._files import save_temp_upload, safe_delete
from ._ym import resolve_ym
from .utils_fail_excel import store_fail_rows_as_excel
from .utils_json import _json_error, _json_ok

import logging


logger = logging.getLogger(__name__)


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

    if kind == "approval":
        del_qs = ApprovalPending.objects.filter(ym=ym)
        if part:
            del_qs = del_qs.filter(user__part=part)
        del_qs.delete()

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


@require_POST
@grade_required("superuser")
def approval_upload_excel(request):
    """
    수수료결재/지점효율 업로드 엔드포인트(공용)

    입력 파라미터(호환 유지):
    - 1) year/month 방식(레거시)
    - 2) ym(YYYY-MM 또는 YYYYMM) 방식(현행 프론트)
    """
    rl = check_rate_limit(
        request,
        scope="commission:approval",
        rule=getattr(settings, "COMMISSION_APPROVAL_RATE_LIMIT", "10/60"),
    )
    if not rl.allowed:
        return rate_limited_json(rl)

    ym_param = (request.POST.get("ym") or request.GET.get("ym") or "").strip()
    year = (request.POST.get("year") or request.GET.get("year") or "").strip()
    month = (request.POST.get("month") or request.GET.get("month") or "").strip()

    part = (request.POST.get("part") or request.GET.get("part") or "").strip()
    kind = (request.POST.get("kind") or request.GET.get("kind") or "").strip()
    excel_file = request.FILES.get("excel_file")

    try:
        resolved = resolve_ym(ym_param=ym_param, year=year, month=month)
        ym = resolved.ym
    except ValueError as ve:
        # ✅ AuditLog (failure: bad request)
        try:
            log_action(
                request,
                ACTION.COMMISSION_EXCEL_UPLOAD,
                meta={"ym": ym_param, "year": year, "month": month, "part": part, "kind": kind, "error": str(ve)},
                success=False,
            )
        except Exception:
            logger.exception("[commission.approval] audit failed: resolve_ym")
        return _json_error(str(ve), status=400)

    if kind not in ("efficiency", "approval"):
        try:
            log_action(
                request,
                ACTION.COMMISSION_EXCEL_UPLOAD,
                meta={"ym": ym, "part": part, "kind": kind, "error": "invalid kind"},
                success=False,
            )
        except Exception:
            logger.exception("[commission.approval] audit failed: invalid kind")
        return _json_error("구분(kind)을 선택해주세요. (efficiency/approval)", status=400)
    if not excel_file:
        try:
            log_action(
                request,
                ACTION.COMMISSION_EXCEL_UPLOAD,
                meta={"ym": ym, "part": part, "kind": kind, "error": "missing excel_file"},
                success=False,
            )
        except Exception:
            logger.exception("[commission.approval] audit failed: missing excel_file")
        return _json_error("엑셀 파일이 전달되지 않았습니다.", status=400)

    temp = save_temp_upload(excel_file)

    try:
        with transaction.atomic():
            row_count, inserted, result = _common_upload(
                request=request,
                ym=ym,
                part=part,
                kind=kind,
                file_path=temp.file_path,
                original_name=temp.original_name,
            )

        missing_sample = result.get("missing_sample", []) or []
        excluded_rows = result.get("excluded_rows", []) or []
        excluded_summary = result.get("excluded_summary", {}) or {}
        fail_token = ""
        if excluded_rows:
            fail_token = store_fail_rows_as_excel(
                rows=excluded_rows,
                filename=f"upload_excluded_{ym}_{part or 'ALL'}_{kind}.xlsx",
                owner_id=str(getattr(request.user, "pk", "") or ""),
            )

        # ✅ AuditLog (success)
        try:
            log_action(
                request,
                ACTION.COMMISSION_EXCEL_UPLOAD,
                meta={
                    "ym": ym,
                    "part": part,
                    "kind": kind,
                    "row_count": row_count,
                    "inserted": inserted,
                    "missing_users": int(result.get("missing_users") or 0),
                    "missing_sample": (missing_sample[:30] if isinstance(missing_sample, list) else []),
                    "excluded_summary": excluded_summary,
                    "fail_token": fail_token or "",
                    "file_name": temp.original_name,
                },
                success=True,
            )
        except Exception:
            logger.exception("[commission.approval] audit failed: upload success")

        return _json_ok(
            "✅ 업로드가 완료되었습니다.",
            ym=ym,
            part=part,
            kind=kind,
            row_count=row_count,
            file_name=temp.original_name,
            inserted=inserted,
            missing_users=int(result.get("missing_users") or 0),
            missing_sample=missing_sample,
            excluded_count=len(excluded_rows),
            excluded_summary=excluded_summary,
            fail_token=fail_token,
            fail_download_url=(f"/commission/download/upload-fail/?token={fail_token}" if fail_token else ""),
        )

    except ValueError as ve:
        # ✅ AuditLog (failure)
        try:
            log_action(
                request,
                ACTION.COMMISSION_EXCEL_UPLOAD,
                meta={"ym": ym, "part": part, "kind": kind, "file_name": temp.original_name, "error": str(ve)},
                success=False,
            )
        except Exception:
            logger.exception("[commission.approval] audit failed: value error")
        return _json_error(str(ve), status=400)

    except Exception as e:
        # ✅ AuditLog (failure)
        try:
            log_action(
                request,
                ACTION.COMMISSION_EXCEL_UPLOAD,
                meta={"ym": ym, "part": part, "kind": kind, "file_name": temp.original_name, "error": str(e)},
                success=False,
            )
        except Exception:
            logger.exception("[commission.approval] audit failed: upload exception")
        return _json_error(f"⚠️ 업로드 실패: {e}", status=500)

    finally:
        safe_delete(temp)