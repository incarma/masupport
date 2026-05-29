# django_ma/dash/viewmods/api_forecast.py
from __future__ import annotations

import calendar
import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts.decorators import grade_required
from dash.services import forecast as forecast_svc
from dash.task_runtime import build_scope_forecast_now, CATEGORIES
from dash.task_runtime import _build_aggs_for_scope

from .constants import FORECAST_MODEL_VER
from .utils.json import json_err

logger = logging.getLogger(__name__)


def _bootstrap_requested_scope_if_missing(ym: str, asof_day: int, scope: str, scope_key: str) -> None:
    agg_exists = forecast_svc.check_agg_exists(ym, scope, scope_key, CATEGORIES)
    forecast_exists = forecast_svc.check_forecast_exists(
        ym, asof_day, scope, scope_key, CATEGORIES, FORECAST_MODEL_VER
    )

    if agg_exists and forecast_exists:
        return

    lock_key = f"dash:api_forecast:bootstrap:{ym}:{scope}:{scope_key}:{asof_day}"
    if not cache.add(lock_key, "1", 60):
        return

    try:
        logger.info(
            "[dash.api_forecast] bootstrap ym=%s asof=%s scope=%s/%s agg_exists=%s forecast_exists=%s",
            ym, asof_day, scope, scope_key, agg_exists, forecast_exists
        )
        # ✅ SIGSEGV 방지: 학습(LightGBM)은 동기로 실행하지 않음
        # 집계만 동기로 생성하고, 예측은 기존 모델 파일이 있을 때만 실행
        if not agg_exists:
            _build_aggs_for_scope(ym, scope, scope_key)

        # ✅ 모델 파일이 있는 카테고리에 대해서만 직접 예측 생성
        # _build_forecast_for_scope()는 내부에서 학습을 시도하므로 사용 금지
        # 대신 load_models → predict → upsert_forecast 흐름을 직접 구성
        if not forecast_exists:
            from dash.ml.forecast import load_models, predict_month_total, upsert_forecast
            from dash.task_runtime import _build_features, MODEL_VER

            for cat in CATEGORIES:
                models = load_models(scope, scope_key, cat)
                if not models:
                    # 모델 없음 → 학습 시도 없이 skip (SIGSEGV 방지)
                    continue
                try:
                    features = _build_features(scope, scope_key, cat, ym, asof_day)
                    p10, p50, p90 = predict_month_total(models, features)
                    upsert_forecast(
                        ym=ym,
                        asof_day=asof_day,
                        scope_type=scope,
                        scope_key=scope_key,
                        category=cat,
                        model_ver=MODEL_VER,
                        pred_total_p10=p10,
                        pred_total_p50=p50,
                        pred_total_p90=p90,
                    )
                except Exception:
                    logger.exception(
                        "[dash.api_forecast] bootstrap predict failed "
                        "ym=%s scope=%s/%s cat=%s",
                        ym, scope, scope_key, cat,
                    )

    except Exception:
        logger.exception(
            "[dash.api_forecast] bootstrap failed ym=%s asof=%s scope=%s/%s",
            ym, asof_day, scope, scope_key
        )
    finally:
        cache.delete(lock_key)


@grade_required("superuser", "head")
@require_GET
def dash_forecast_api(request):

    # 캐시/프록시 혼선 방지(개발/운영 모두 안전)
    # - 예측은 자주 바뀔 수 있으니 기본은 no-store 권장

    ym = (request.GET.get("ym") or "").strip()
    if not ym:
        return json_err("ym is required")

    try:
        y, m = map(int, ym.split("-"))
        last_day = calendar.monthrange(y, m)[1]
    except (ValueError, TypeError):
        return json_err("invalid ym")

    try:
        asof_day = int(request.GET.get("asof_day") or 1)
    except (ValueError, TypeError):
        asof_day = 1
    asof_day = max(1, min(asof_day, last_day))

    scope = (request.GET.get("scope") or "all").strip()
    if scope not in ("all", "part", "branch"):
        scope = "all"

    scope_key = "*"
    if scope == "part":
        scope_key = (request.GET.get("part") or "").strip()
    elif scope == "branch":
        scope_key = (request.GET.get("branch") or "").strip()

    # head 권한: branch 강제(기존 dash_sales 정책 유지)
    if request.user.grade == "head":
        my_branch = (request.user.branch or "").strip()
        if not my_branch:
            return JsonResponse({"ok": True, "data": None, "message": "no branch"}, status=200)
        scope = "branch"
        scope_key = my_branch

    _bootstrap_requested_scope_if_missing(ym, asof_day, scope, scope_key)

    labels = list(range(1, last_day + 1))

    payload = {
        "schema": "multi-category-v1",
        "meta": {
            "model_ver": FORECAST_MODEL_VER,
            "requested_asof_day": asof_day,
        },
        "ym": ym,
        "scope": scope,
        "scope_key": scope_key,
        "labels": labels,
        "series": {
            cat: forecast_svc.get_category_payload(
                ym, scope, scope_key, cat, asof_day, labels, FORECAST_MODEL_VER
            )
            for cat in ("long", "car", "long_nonlife", "long_life")
        },
    }
    # ✅ 호환용 alias (프론트가 categories로 접근해도 되게)
    payload["categories"] = payload["series"]
    resp = JsonResponse({"ok": True, "data": payload}, status=200)
    resp["Cache-Control"] = "no-store"
    return resp
