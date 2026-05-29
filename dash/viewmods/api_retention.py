# django_ma/dash/viewmods/api_retention.py
from __future__ import annotations

import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts.decorators import grade_required
from dash.services.retention import get_retention_api_payload

from .utils.json import json_err

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 30  # 30분


@grade_required("superuser", "head")
@require_GET
def retention_api(request):
    """
    GET /dash/api/retention/
    params:
      ym        : YYYY-MM (필수)
      life_nl   : 생보/손보/'' (기본='')
      scope_type: all/part/branch (기본=all)
      scope_key : 소속명/파트너명 (scope_type≠all 시 필수)
      q         : 보험사/상품명/설계사명 검색어

    response schema:
    {
      ok: true,
      data: {
        ym, life_nl, scope_type, scope_key,
        rounds: [2,3,4,7,...],
        summary: { round: { total_amount, paid_amount, total_count, paid_count, rate } },
        trend:   { labels: [...], by_round: { 2: [...], 7: [...] } },
        by_insurer: [{ insurer, rounds: {2: rate, 7: rate}, total_count }],
        by_planner: [{ emp_id, name, part, branch, rounds: {...}, total_count }]
      }
    }
    """
    ym = (request.GET.get("ym") or "").strip()
    if not ym:
        return json_err("ym 필수")

    life_nl    = (request.GET.get("life_nl") or "").strip()
    scope_type = (request.GET.get("scope_type") or "all").strip()
    scope_key  = (request.GET.get("scope_key") or "").strip()
    q          = (request.GET.get("q") or "").strip()

    if scope_type not in ("all", "part", "branch"):
        scope_type = "all"

    # head 권한: branch 강제
    if request.user.grade == "head":
        my_branch = (request.user.branch or "").strip()
        if not my_branch:
            return JsonResponse({"ok": True, "data": None, "message": "no branch"})
        scope_type = "branch"
        scope_key  = my_branch

    cache_key = f"dash:retention:api:{ym}:{life_nl}:{scope_type}:{scope_key}:{q}"
    cached = cache.get(cache_key)
    if cached:
        resp = JsonResponse({"ok": True, "data": cached})
        resp["Cache-Control"] = "no-store"
        return resp

    payload = get_retention_api_payload(ym, life_nl, scope_type, scope_key, q)

    cache.set(cache_key, payload, CACHE_TTL)
    resp = JsonResponse({"ok": True, "data": payload})
    resp["Cache-Control"] = "no-store"
    return resp
