# django_ma/dash/viewmods/api_retention_upload.py
from __future__ import annotations

import logging

import pandas as pd
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from audit.constants import ACTION
from audit.services import log_action
from dash.models import RetentionUploadLog
from dash.services.retention import (
    _detect_life_nl,
    bulk_upsert_retention_records,
    parse_retention_excel,
    rebuild_retention_agg,
)
from dash.viewmods.utils.json import json_err

logger = logging.getLogger(__name__)


@grade_required("superuser")
@require_POST
def upload_retention_excel(request):
    f = request.FILES.get("excel_file")
    if not f:
        return json_err("엑셀 파일(excel_file)이 없습니다.", 400)

    # life_nl: 파일명 힌트 → 자동감지 fallback
    life_nl_hint = request.POST.get("life_nl", "").strip()  # 생보/손보

    try:
        df = pd.read_excel(f, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
    except Exception as e:
        logger.exception("retention upload read_excel failed")
        return json_err(f"엑셀 읽기 실패: {e}", 400)

    # 손생 감지
    if life_nl_hint in ("생보", "손보"):
        life_nl = life_nl_hint
    else:
        life_nl = _detect_life_nl(df)

    # 파싱
    records, errors = parse_retention_excel(df, life_nl)
    if errors and not records:
        return json_err(f"파싱 실패: {errors[0]}", 400)

    # 저장
    upserted, skipped = bulk_upsert_retention_records(records)

    # ym 집합 추출 → 집계 rebuild
    yms = {r["ym"] for r in records}
    for ym in yms:
        try:
            rebuild_retention_agg(ym, life_nl)
        except Exception:
            logger.exception("retention agg rebuild failed ym=%s", ym)

    # 업로드 로그 (ym+life_nl 단위, 가장 많은 ym 기준)
    main_ym = max(yms, key=lambda x: sum(1 for r in records if r["ym"] == x)) if yms else ""
    if main_ym:
        RetentionUploadLog.objects.update_or_create(
            ym=main_ym,
            life_nl=life_nl,
            defaults={
                "file_name":   f.name,
                "row_count":   len(df),
                "upserted":    upserted,
                "skipped":     skipped,
                "uploaded_by": request.user,
            },
        )

    log_action(
        request,
        ACTION.RETENTION_EXCEL_UPLOAD,
        obj=None, object_type="RetentionRecord", object_id=None,
        meta={"life_nl": life_nl, "yms": sorted(yms), "upserted": upserted},
        success=True,
    )

    return JsonResponse({
        "ok": True,
        "message": f"업로드 완료 ({life_nl})",
        "summary": {
            "life_nl":    life_nl,
            "yms":        sorted(yms),
            "rows_in_file": len(df),
            "upserted":   upserted,
            "skipped":    skipped,
            "parse_errors": errors[:3],
        },
    })