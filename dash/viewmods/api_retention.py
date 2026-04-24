# django_ma/dash/viewmods/api_retention.py
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts.decorators import grade_required
from dash.models import RetentionAgg, RetentionRecord

logger = logging.getLogger(__name__)

# 캐시 TTL
CACHE_TTL = 60 * 30  # 30분


def _float_rate(rate) -> float | None:
    if rate is None:
        return None
    try:
        return float(rate)
    except Exception:
        return None


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
        rounds: [2,3,4,7,...],          // 존재하는 회차 목록
        summary: {                       // 전체 KPI
          round: { total_amount, paid_amount, total_count, paid_count, rate }
        },
        trend: {                         // 최근 6개월 추이
          labels: ["YYYY-MM",...],
          by_round: { 2: [rate,...], 7: [rate,...] }
        },
        by_insurer: [                    // 보험사별 (회차별 rate)
          { insurer, rounds: {2: rate, 7: rate}, total_count }
        ],
        by_planner: [                    // 설계사별 상위 20
          { emp_id, name, part, branch,
            rounds: {2: rate, 7: rate}, total_count }
        ]
      }
    }
    """
    ym = (request.GET.get("ym") or "").strip()
    if not ym:
        return JsonResponse({"ok": False, "message": "ym 필수"}, status=400)

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

    # ── 집계 데이터 쿼리 ────────────────────────────────
    agg_qs = RetentionAgg.objects.filter(
        ym=ym,
        scope_type=scope_type,
        scope_key=scope_key if scope_type != "all" else "*",
    )
    if life_nl:
        agg_qs = agg_qs.filter(life_nl=life_nl)

    # 존재하는 회차 목록
    rounds = sorted(agg_qs.filter(insurer="").values_list("round_no", flat=True).distinct())

    # summary (insurer="" = 전체)
    summary = {}
    for rnd in rounds:
        row = agg_qs.filter(round_no=rnd, insurer="").first()
        if row:
            summary[rnd] = {
                "total_amount": row.total_amount,
                "paid_amount":  row.paid_amount,
                "total_count":  row.total_count,
                "paid_count":   row.paid_count,
                "rate":         _float_rate(row.rate),
            }

    # trend (최근 6개월)
    y_int, m_int = map(int, ym.split("-"))
    trend_labels = []
    for i in range(5, -1, -1):
        mm = m_int - i
        yy = y_int
        while mm <= 0:
            mm += 12; yy -= 1
        trend_labels.append(f"{yy:04d}-{mm:02d}")

    trend_by_round: dict[int, list] = {rnd: [] for rnd in rounds}
    for label in trend_labels:
        for rnd in rounds:
            t_agg = RetentionAgg.objects.filter(
                ym=label,
                life_nl=life_nl or "",
                round_no=rnd,
                scope_type=scope_type,
                scope_key=scope_key if scope_type != "all" else "*",
                insurer="",
            ).first()
            trend_by_round[rnd].append(_float_rate(t_agg.rate) if t_agg else None)

    # by_insurer
    insurers = sorted(
        agg_qs.filter(insurer="").exclude(insurer="")
        .values_list("insurer", flat=True).distinct()
    )
    # 보험사별 집계는 insurer≠"" 행에서
    insurer_rows_qs = agg_qs.exclude(insurer="")
    if q:
        insurer_rows_qs = insurer_rows_qs.filter(insurer__icontains=q)

    insurer_map: dict[str, dict] = {}
    for row in insurer_rows_qs:
        key = row.insurer
        if key not in insurer_map:
            insurer_map[key] = {"insurer": key, "rounds": {}, "total_count": 0}
        insurer_map[key]["rounds"][row.round_no] = _float_rate(row.rate)
        insurer_map[key]["total_count"] = max(insurer_map[key]["total_count"], row.total_count)

    by_insurer = sorted(insurer_map.values(), key=lambda x: -x["total_count"])[:20]

    # by_planner — RetentionRecord 직접 집계 (집계 테이블에 설계사 차원 없음)
    from django.db.models import Sum, Q as DQ, Count
    from django.db.models.functions import Coalesce
    from django.db.models import Value, CharField

    rec_qs = RetentionRecord.objects.filter(ym=ym)
    if life_nl:
        rec_qs = rec_qs.filter(life_nl=life_nl)

    # scope 필터
    from dash.services.retention import _scope_filter_retention
    rec_qs = rec_qs.filter(_scope_filter_retention(scope_type, scope_key if scope_type != "all" else "*"))

    if q:
        rec_qs = rec_qs.filter(
            DQ(name_snapshot__icontains=q)
            | DQ(emp_id_snapshot__icontains=q)
            | DQ(insurer__icontains=q)
            | DQ(product_name__icontains=q)
        )

    planner_map: dict[str, dict] = {}
    for rnd in rounds:
        qs_rnd = rec_qs.filter(round_no=rnd)
        rows = (
            qs_rnd
            .values("emp_id_snapshot", "name_snapshot", "part_snapshot", "branch_snapshot")
            .annotate(
                total=Sum("recruit_amount"),
                paid=Sum("recruit_amount", filter=DQ(status__in=["정상", "유예"])),
                cnt=Count("policy_no"),
            )
            .order_by("-total")[:20]
        )
        for row in rows:
            key = row["emp_id_snapshot"] or row["name_snapshot"] or ""
            if not key:
                continue
            if key not in planner_map:
                planner_map[key] = {
                    "emp_id":  row["emp_id_snapshot"],
                    "name":    row["name_snapshot"],
                    "part":    row["part_snapshot"],
                    "branch":  row["branch_snapshot"],
                    "rounds":  {},
                    "total_count": 0,
                }
            total = row["total"] or 0
            paid  = row["paid"]  or 0
            rate  = round(paid / total * 100, 2) if total > 0 else None
            planner_map[key]["rounds"][rnd]    = rate
            planner_map[key]["total_count"] += row["cnt"] or 0

    by_planner = sorted(planner_map.values(), key=lambda x: -x["total_count"])[:20]

    payload = {
        "ym": ym, "life_nl": life_nl,
        "scope_type": scope_type, "scope_key": scope_key,
        "rounds": rounds,
        "summary": summary,
        "trend": {"labels": trend_labels, "by_round": {str(k): v for k, v in trend_by_round.items()}},
        "by_insurer": by_insurer,
        "by_planner": by_planner,
    }

    cache.set(cache_key, payload, CACHE_TTL)
    resp = JsonResponse({"ok": True, "data": payload})
    resp["Cache-Control"] = "no-store"
    return resp