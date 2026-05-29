# django_ma/dash/viewmods/pages.py
from __future__ import annotations

from datetime import datetime

from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.utils import timezone

from accounts.decorators import grade_required
from dash.models import SalesRecord
from dash.services import sales as sales_svc

from .utils import (
    apply_head_scope_to_salesrecord_qs,
    apply_common_filters_to_salesrecord_qs,
    month_day_labels,
    build_cumsum_aligned,
    build_cumsum_prevmonth_aligned,
    build_cumsum_othermonth_aligned,
    nice_step_and_max,
    prev_ym_str,
    prev_year_ym_str,
)


@grade_required("superuser", "head")
def redirect_to_sales(request):
    return redirect("dash:dash_sales")


@grade_required("superuser", "head")
def dash_sales(request):
    now = datetime.now()
    default_year = str(now.year)
    default_month = f"{now.month:02d}"

    year = (request.GET.get("year") or default_year).strip()
    month = (request.GET.get("month") or default_month).strip().zfill(2)
    ym = f"{year}-{month}"

    year_options = [str(y) for y in range(now.year - 5, now.year + 2)]
    month_options = [f"{m:02d}" for m in range(1, 13)]

    filter_part = (request.GET.get("part") or "").strip()
    filter_branch = (request.GET.get("branch") or "").strip()
    filter_life_nl = (request.GET.get("life_nl") or "").strip()
    filter_insurer = (request.GET.get("insurer") or "").strip()
    filter_q = (request.GET.get("q") or "").strip()
    advisor_branch = (request.GET.get("advisor_branch") or "").strip()
    page = request.GET.get("page", "1")

    try:
        page_size = int(request.GET.get("page_size") or 50)
    except ValueError:
        page_size = 50
    if page_size not in (50, 100, 250, 500):
        page_size = 50

    # ── 기준 QS: 권한 + ym ───────────────────────────────────
    qs_base = SalesRecord.objects.all()
    qs_base, forced_branch = apply_head_scope_to_salesrecord_qs(qs_base, user=request.user)
    if forced_branch:
        filter_branch = forced_branch

    qs_base = qs_base.filter(ym=ym)

    # ── 공통 스코프 (보험사 필터 적용 전) ─────────────────────
    qs_scope = apply_common_filters_to_salesrecord_qs(
        qs_base,
        part=filter_part,
        branch=filter_branch,
        q=filter_q,
    )

    # ── 손생 → 보험사 맵 (q 제외 스코프) ────────────────────
    qs_map_scope = apply_common_filters_to_salesrecord_qs(
        qs_base, part=filter_part, branch=filter_branch, q="",
    )
    life_nl_insurer_map = sales_svc.get_life_nl_insurer_map(
        qs_map_scope, ym, filter_part, filter_branch
    )

    # ── 손생 필터 적용 ────────────────────────────────────────
    qs_pre_insurer = qs_scope
    if filter_life_nl:
        qs_pre_insurer = qs_pre_insurer.filter(life_nl=filter_life_nl)

    # ── 보험사 옵션 ───────────────────────────────────────────
    insurer_options = sales_svc.get_insurer_options(
        qs_pre_insurer, ym, filter_part, filter_branch, filter_life_nl, filter_q
    )

    # ── 최종 QS (보험사 필터) ─────────────────────────────────
    qs_final = qs_pre_insurer
    if filter_insurer:
        qs_final = qs_final.filter(insurer=filter_insurer)
    qs_final = qs_final.select_related("user").order_by("-updated_at")

    # ── 랭킹용 QS (q 제외, insurer 포함) ─────────────────────
    qs_rank_scope = apply_common_filters_to_salesrecord_qs(
        qs_base, part=filter_part, branch=filter_branch, q="",
    )
    if filter_insurer:
        qs_rank_scope = qs_rank_scope.filter(insurer=filter_insurer)

    branch_top10_long     = sales_svc.get_branch_top10(qs_rank_scope, "long")
    branch_top10_car      = sales_svc.get_branch_top10(qs_rank_scope, "car")
    branch_top10_nonlife  = sales_svc.get_branch_top10(qs_rank_scope, "long_nonlife")
    branch_top10_life     = sales_svc.get_branch_top10(qs_rank_scope, "long_life")

    advisor_top10_long    = sales_svc.get_advisor_top10(qs_rank_scope, "long", advisor_branch)
    advisor_top10_car     = sales_svc.get_advisor_top10(qs_rank_scope, "car", advisor_branch)
    advisor_top10_nonlife = sales_svc.get_advisor_top10(qs_rank_scope, "long_nonlife", advisor_branch)
    advisor_top10_life    = sales_svc.get_advisor_top10(qs_rank_scope, "long_life", advisor_branch)

    insurer_top10_long    = sales_svc.get_insurer_top10(qs_rank_scope, "long")
    insurer_top10_car     = sales_svc.get_insurer_top10(qs_rank_scope, "car")
    insurer_top10_nonlife = sales_svc.get_insurer_top10(qs_rank_scope, "long_nonlife")
    insurer_top10_life    = sales_svc.get_insurer_top10(qs_rank_scope, "long_life")

    product_top10_long    = sales_svc.get_product_top10(qs_rank_scope, "long")
    product_top10_car     = sales_svc.get_product_top10(qs_rank_scope, "car")
    product_top10_nonlife = sales_svc.get_product_top10(qs_rank_scope, "long_nonlife")
    product_top10_life    = sales_svc.get_product_top10(qs_rank_scope, "long_life")

    # ── 차트 데이터 ───────────────────────────────────────────
    chart_day_labels = month_day_labels(ym)
    prev_ym = prev_ym_str(ym)
    prev_year_ym = prev_year_ym_str(ym)

    qs_chart_long    = qs_final.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납")
    qs_chart_car     = qs_final.filter(life_nl="자동차")
    qs_chart_nonlife = qs_final.filter(life_nl="손보").exclude(pay_method__icontains="일시납")
    qs_chart_life    = qs_final.filter(life_nl="생보").exclude(pay_method__icontains="일시납")

    chart_cumsum         = build_cumsum_aligned(qs_chart_long, chart_day_labels)
    car_chart_cumsum     = build_cumsum_aligned(qs_chart_car, chart_day_labels)
    nonlife_chart_cumsum = build_cumsum_aligned(qs_chart_nonlife, chart_day_labels)
    life_chart_cumsum    = build_cumsum_aligned(qs_chart_life, chart_day_labels)

    y_max_value_nl_l = max(max(nonlife_chart_cumsum or [0]), max(life_chart_cumsum or [0]))
    nl_l_y_step, nl_l_y_max = nice_step_and_max(y_max_value_nl_l)

    # 전월
    qs_prev_base = SalesRecord.objects.all()
    qs_prev_base, _ = apply_head_scope_to_salesrecord_qs(qs_prev_base, user=request.user)
    qs_prev_base = qs_prev_base.filter(ym=prev_ym)

    qs_prev_scope = apply_common_filters_to_salesrecord_qs(
        qs_prev_base, part=filter_part, branch=filter_branch, q=filter_q,
    )
    if filter_life_nl:
        qs_prev_scope = qs_prev_scope.filter(life_nl=filter_life_nl)
    if filter_insurer:
        qs_prev_scope = qs_prev_scope.filter(insurer=filter_insurer)

    prev_chart_cumsum        = build_cumsum_prevmonth_aligned(
        qs_prev_scope.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납"),
        chart_day_labels, prev_ym,
    )
    prev_car_chart_cumsum    = build_cumsum_prevmonth_aligned(
        qs_prev_scope.filter(life_nl="자동차"), chart_day_labels, prev_ym,
    )
    prev_nonlife_chart_cumsum = build_cumsum_prevmonth_aligned(
        qs_prev_scope.filter(life_nl="손보").exclude(pay_method__icontains="일시납"),
        chart_day_labels, prev_ym,
    )
    prev_life_chart_cumsum   = build_cumsum_prevmonth_aligned(
        qs_prev_scope.filter(life_nl="생보").exclude(pay_method__icontains="일시납"),
        chart_day_labels, prev_ym,
    )

    # 전년 동월
    qs_py_base = SalesRecord.objects.all()
    qs_py_base, _ = apply_head_scope_to_salesrecord_qs(qs_py_base, user=request.user)
    qs_py_base = qs_py_base.filter(ym=prev_year_ym)

    qs_py_scope = apply_common_filters_to_salesrecord_qs(
        qs_py_base, part=filter_part, branch=filter_branch, q=filter_q,
    )
    if filter_life_nl:
        qs_py_scope = qs_py_scope.filter(life_nl=filter_life_nl)
    if filter_insurer:
        qs_py_scope = qs_py_scope.filter(insurer=filter_insurer)

    py_chart_cumsum        = build_cumsum_othermonth_aligned(
        qs_py_scope.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납"),
        chart_day_labels, prev_year_ym,
    )
    py_car_chart_cumsum    = build_cumsum_othermonth_aligned(
        qs_py_scope.filter(life_nl="자동차"), chart_day_labels, prev_year_ym,
    )
    py_nonlife_chart_cumsum = build_cumsum_othermonth_aligned(
        qs_py_scope.filter(life_nl="손보").exclude(pay_method__icontains="일시납"),
        chart_day_labels, prev_year_ym,
    )
    py_life_chart_cumsum   = build_cumsum_othermonth_aligned(
        qs_py_scope.filter(life_nl="생보").exclude(pay_method__icontains="일시납"),
        chart_day_labels, prev_year_ym,
    )

    # ── 드롭다운 옵션 ─────────────────────────────────────────
    part_options, branch_options_all, part_branch_map = sales_svc.get_dropdown_options(
        request.user, qs_base
    )

    # ── 페이지네이션 ──────────────────────────────────────────
    paginator = Paginator(qs_final, page_size)
    page_obj = paginator.get_page(page)

    current_page = page_obj.number
    total_pages = paginator.num_pages
    block_size = 10
    start_page = ((current_page - 1) // block_size) * block_size + 1
    end_page = min(start_page + block_size - 1, total_pages)

    context = {
        "filter_year": year,
        "filter_month": month,
        "filter_ym": ym,

        "filter_part": filter_part,
        "filter_branch": filter_branch,
        "filter_life_nl": filter_life_nl,
        "filter_insurer": filter_insurer,
        "filter_q": filter_q,
        "advisor_branch": advisor_branch,

        "year_options": year_options,
        "month_options": month_options,

        "part_options": part_options,
        "branch_options_all": branch_options_all,
        "part_branch_map": part_branch_map,

        "life_nl_insurer_map": life_nl_insurer_map,
        "insurer_options": insurer_options,

        "page_size": page_size,
        "total_count": qs_final.count(),
        "page_obj": page_obj,
        "start_page": start_page,
        "end_page": end_page,
        "total_pages": total_pages,

        "chart_day_labels": chart_day_labels,

        "chart_cumsum": chart_cumsum,
        "car_chart_cumsum": car_chart_cumsum,
        "nonlife_chart_cumsum": nonlife_chart_cumsum,
        "life_chart_cumsum": life_chart_cumsum,

        "nl_l_y_step": nl_l_y_step,
        "nl_l_y_max": nl_l_y_max,

        "prev_ym": prev_ym,
        "prev_chart_cumsum": prev_chart_cumsum,
        "prev_car_chart_cumsum": prev_car_chart_cumsum,
        "prev_nonlife_chart_cumsum": prev_nonlife_chart_cumsum,
        "prev_life_chart_cumsum": prev_life_chart_cumsum,

        "prev_year_ym": prev_year_ym,
        "py_chart_cumsum": py_chart_cumsum,
        "py_car_chart_cumsum": py_car_chart_cumsum,
        "py_nonlife_chart_cumsum": py_nonlife_chart_cumsum,
        "py_life_chart_cumsum": py_life_chart_cumsum,

        "branch_top10_long": branch_top10_long,
        "branch_top10_car": branch_top10_car,
        "branch_top10_nonlife": branch_top10_nonlife,
        "branch_top10_life": branch_top10_life,

        "advisor_top10_long": advisor_top10_long,
        "advisor_top10_car": advisor_top10_car,
        "advisor_top10_nonlife": advisor_top10_nonlife,
        "advisor_top10_life": advisor_top10_life,

        "insurer_top10_long": insurer_top10_long,
        "insurer_top10_car": insurer_top10_car,
        "insurer_top10_nonlife": insurer_top10_nonlife,
        "insurer_top10_life": insurer_top10_life,

        "product_top10_long": product_top10_long,
        "product_top10_car": product_top10_car,
        "product_top10_nonlife": product_top10_nonlife,
        "product_top10_life": product_top10_life,
    }
    return render(request, "dash/dash_sales.html", context)


@grade_required("superuser", "head")
def dash_recruit(request):
    return render(request, "dash/dash_recruit.html")


@grade_required("superuser", "head")
def dash_retention(request):
    now = timezone.localtime()
    upload_logs = sales_svc.get_recent_upload_logs(count=4)
    context = {
        "initial_year": now.year,
        "initial_month": now.month,
        "initial_scope_type": "all",
        "initial_scope_key": "",
        "STATIC_VERSION": str(int(now.timestamp())),
        "upload_logs": upload_logs,
    }
    return render(request, "dash/dash_retention.html", context)


@grade_required("superuser")
def dash_goals(request):
    return render(request, "dash/dash_goals.html")
