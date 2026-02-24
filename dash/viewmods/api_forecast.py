# django_ma/dash/viewmods/api_forecast.py
from __future__ import annotations

import calendar

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts.decorators import grade_required
from dash.models import SalesDailyAgg, SalesForecast, SalesForecastDaily

from .constants import FORECAST_MODEL_VER


@grade_required("superuser", "head")
@require_GET
def dash_forecast_api(request):

    # 캐시/프록시 혼선 방지(개발/운영 모두 안전)
    # - 예측은 자주 바뀔 수 있으니 기본은 no-store 권장

    ym = (request.GET.get("ym") or "").strip()
    if not ym:
        return JsonResponse({"ok": False, "message": "ym is required"}, status=400)

    try:
        y, m = map(int, ym.split("-"))
        last_day = calendar.monthrange(y, m)[1]
    except Exception:
        return JsonResponse({"ok": False, "message": "invalid ym"}, status=400)

    try:
        asof_day = int(request.GET.get("asof_day") or 1)
    except Exception:
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

    labels = list(range(1, last_day + 1))

    def build_category_payload(category: str):
        # 실제 누적선
        rows = SalesDailyAgg.objects.filter(
            ym=ym, scope_type=scope, scope_key=scope_key, category=category
        ).values("day", "cumsum")
        actual_map = {r["day"]: int(r["cumsum"] or 0) for r in rows}
        actual_cumsum = [actual_map.get(d, 0) for d in labels]

        # ✅ 예측(가장 최신 생성본 1개): asof_day 정확일치가 아니라 "asof_day <= 요청 asof_day" 중 최신
        fc = (
            SalesForecast.objects.filter(
                ym=ym,
                scope_type=scope,
                scope_key=scope_key,
                category=category,
                model_ver=FORECAST_MODEL_VER,
                asof_day__lte=asof_day,
            )
            .order_by("-asof_day", "-created_at")
            .first()
        )

        if not fc:
            return {
                "category": category,
                "asof_day": asof_day,
                "actual_cumsum": actual_cumsum,
                "pred": None,
            }

        days = SalesForecastDaily.objects.filter(forecast=fc).values(
            "day", "pred_cumsum_p10", "pred_cumsum_p50", "pred_cumsum_p90"
        )
        pred_map = {r["day"]: r for r in days}

        def series(key):
            out = []
            for d in labels:
                v = (pred_map.get(d) or {}).get(key)
                out.append(None if v is None else int(v))
            return out

        return {
            "category": category,
            "asof_day": int(fc.asof_day),
            "generated_at": fc.created_at.isoformat(),
            "actual_cumsum": actual_cumsum,
            "pred": {
                "p10": series("pred_cumsum_p10"),
                "p50": series("pred_cumsum_p50"),
                "p90": series("pred_cumsum_p90"),
                "totals": {
                    "p10": fc.pred_total_p10,
                    "p50": fc.pred_total_p50,
                    "p90": fc.pred_total_p90,
                },
                "actual_to_date": fc.actual_to_date,
            },
        }

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
            "long": build_category_payload("long"),
            "car": build_category_payload("car"),
            "long_nonlife": build_category_payload("long_nonlife"),
            "long_life": build_category_payload("long_life"),
        },
    }
    # ✅ 호환용 alias (프론트가 categories로 접근해도 되게)
    payload["categories"] = payload["series"]
    resp = JsonResponse({"ok": True, "data": payload}, status=200)
    resp["Cache-Control"] = "no-store"
    return resp