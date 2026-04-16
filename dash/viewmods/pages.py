# django_ma/dash/viewmods/pages.py
from __future__ import annotations

import calendar
from datetime import datetime

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Value, CharField, Count
from django.db.models.functions import Coalesce, NullIf
from django.shortcuts import render, redirect

from accounts.decorators import grade_required
from accounts.models import CustomUser
from dash.models import SalesRecord

from .utils import (
    clean_list,
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

    # -----------------------------
    # 3) base QS: 권한 + ym
    # -----------------------------
    qs_base = SalesRecord.objects.all()
    qs_base, forced_branch = apply_head_scope_to_salesrecord_qs(qs_base, user=request.user)
    if forced_branch:
        filter_branch = forced_branch

    qs_base = qs_base.filter(ym=ym)

    # -----------------------------
    # 4) 옵션/조회 공통 스코프(보험사/손생 적용 전)
    # -----------------------------
    qs_scope = apply_common_filters_to_salesrecord_qs(
        qs_base,
        part=filter_part,
        branch=filter_branch,
        q=filter_q,
    )

    # -----------------------------
    # 5) 손생 -> 보험사 맵(즉시 연동용): q 제외
    # -----------------------------
    qs_map_scope = qs_base
    if filter_part:
        qs_map_scope = qs_map_scope.filter(Q(user__part=filter_part) | Q(part_snapshot=filter_part))
    if filter_branch:
        qs_map_scope = qs_map_scope.filter(Q(user__branch=filter_branch) | Q(branch_snapshot=filter_branch))

    map_cache_key = f"dash:lifeinsmap:{ym}:{filter_part or '*'}:{filter_branch or '*'}"
    life_nl_insurer_map = cache.get(map_cache_key)
    if life_nl_insurer_map is None:
        life_nl_insurer_map = {}
        for ln in ["손보", "생보", "자동차"]:
            raw = list(
                qs_map_scope.filter(life_nl=ln)
                .exclude(insurer__isnull=True).exclude(insurer__exact="")
                .values_list("insurer", flat=True).distinct()
            )
            life_nl_insurer_map[ln] = clean_list(raw)
        cache.set(map_cache_key, life_nl_insurer_map, 60 * 30)

    # -----------------------------
    # 6) 손생 적용 후: qs_pre_insurer
    # -----------------------------
    qs_pre_insurer = qs_scope
    if filter_life_nl:
        qs_pre_insurer = qs_pre_insurer.filter(life_nl=filter_life_nl)

    # -----------------------------
    # 7) 보험사 옵션 + 캐시
    # -----------------------------
    insurer_options = []
    if filter_q:
        raw = list(
            qs_pre_insurer.exclude(insurer__isnull=True).exclude(insurer__exact="")
            .values_list("insurer", flat=True).distinct()
        )
        insurer_options = clean_list(raw)
    else:
        cache_key = f"dash:insurers:{ym}:{filter_part or '*'}:{filter_branch or '*'}:{filter_life_nl or '*'}"
        insurer_options = cache.get(cache_key)
        if insurer_options is None:
            raw = list(
                qs_pre_insurer.exclude(insurer__isnull=True).exclude(insurer__exact="")
                .values_list("insurer", flat=True).distinct()
            )
            insurer_options = clean_list(raw)
            cache.set(cache_key, insurer_options, 60 * 30)

    # -----------------------------
    # 8) 최종 조회 QS (보험사 필터)
    # -----------------------------
    qs_final = qs_pre_insurer
    if filter_insurer:
        qs_final = qs_final.filter(insurer=filter_insurer)
    qs_final = qs_final.select_related("user").order_by("-updated_at")

    # -----------------------------
    # 8-1) 차트 하단 branch TOP10 집계
    # - 현재 선택 조직 스코프(권한 + part/branch) 기준
    # - insurer 선택 시 동일하게 반영
    # - q 검색어는 "조직 산하 branch 랭킹" 의미와 어긋날 수 있어 제외
    # -----------------------------
    qs_rank_scope = qs_base
    if filter_part:
        qs_rank_scope = qs_rank_scope.filter(
            Q(user__part=filter_part) | Q(part_snapshot=filter_part)
        )
    if filter_branch:
        qs_rank_scope = qs_rank_scope.filter(
            Q(user__branch=filter_branch) | Q(branch_snapshot=filter_branch)
        )
    if filter_insurer:
        qs_rank_scope = qs_rank_scope.filter(insurer=filter_insurer)

    def _branch_top10(qs, category: str):
        if category == "long":
            qs = qs.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납")
        elif category == "car":
            qs = qs.filter(life_nl="자동차")
        elif category == "long_nonlife":
            qs = qs.filter(life_nl="손보").exclude(pay_method__icontains="일시납")
        elif category == "long_life":
            qs = qs.filter(life_nl="생보").exclude(pay_method__icontains="일시납")
        else:
            return []

        rows = (
            qs.annotate(
                channel_name=Coalesce(
                    "user__channel",
                    Value(""),
                    output_field=CharField(),
                ),
                part_name=Coalesce(
                    "user__part",
                    "part_snapshot",
                    output_field=CharField(),
                ),
                branch_name=Coalesce(
                    "user__branch",
                    "branch_snapshot",
                    output_field=CharField(),
                )
            )
            .exclude(channel_name__isnull=True)
            .exclude(channel_name__exact="")
            .exclude(part_name__isnull=True)
            .exclude(part_name__exact="")
            .exclude(branch_name__isnull=True)
            .exclude(branch_name__exact="")
            .values("channel_name", "part_name", "branch_name")
            .annotate(
                total_count=Count("policy_no"),
                total_amount=Coalesce(
                    Sum("receipt_amount"),
                    Value(0),
                )
            )
            .order_by("-total_amount", "channel_name", "part_name", "branch_name")[:10]
        )

        result = []
        for idx, row in enumerate(rows, start=1):
            result.append({
                "rank": idx,
                "channel_name": row["channel_name"],
                "part_name": row["part_name"],
                "branch_name": row["branch_name"],
                "total_count": int(row["total_count"] or 0),
                "total_amount": int(row["total_amount"] or 0),
            })
        return result
    
    def _advisor_top10(qs, category: str):
        if category == "long":
            qs = qs.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납")
        elif category == "car":
            qs = qs.filter(life_nl="자동차")
        elif category == "long_nonlife":
            qs = qs.filter(life_nl="손보").exclude(pay_method__icontains="일시납")
        elif category == "long_life":
            qs = qs.filter(life_nl="생보").exclude(pay_method__icontains="일시납")
        else:
            return []
        
        if advisor_branch:
            qs = qs.filter(
                Q(user__branch=advisor_branch) | Q(branch_snapshot=advisor_branch)
            )

        rows = (
            qs.annotate(
                advisor_name=Coalesce(
                    NullIf("user__name", Value("")),
                    NullIf("name_snapshot", Value("")),
                    output_field=CharField(),
                ),
                advisor_emp_id=Coalesce(
                    NullIf("user__id", Value("")),
                    NullIf("emp_id_snapshot", Value("")),
                    output_field=CharField(),
                ),
                branch_name=Coalesce(
                    NullIf("user__branch", Value("")),
                    NullIf("branch_snapshot", Value("")),
                    output_field=CharField(),
                ),
            )
            .exclude(advisor_name__isnull=True)
            .exclude(advisor_name__exact="")
            .exclude(advisor_emp_id__isnull=True)
            .exclude(advisor_emp_id__exact="")
            .exclude(branch_name__isnull=True)
            .exclude(branch_name__exact="")
            .values("branch_name", "advisor_name", "advisor_emp_id")
            .annotate(
                total_count=Count("policy_no"),
                total_amount=Coalesce(
                    Sum("receipt_amount"),
                    Value(0),
                )
            )
            .order_by("-total_amount", "branch_name", "advisor_name", "advisor_emp_id")[:10]
        )

        result = []
        for idx, row in enumerate(rows, start=1):
            result.append({
                "rank": idx,
                "branch_name": row["branch_name"],
                "advisor_name": row["advisor_name"],
                "advisor_emp_id": row["advisor_emp_id"],
                "total_count": int(row["total_count"] or 0),
                "total_amount": int(row["total_amount"] or 0),
            })
        return result
    
    def _insurer_top10(qs, category: str):
        if category == "long":
            qs = qs.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납")
        elif category == "car":
            qs = qs.filter(life_nl="자동차")
        elif category == "long_nonlife":
            qs = qs.filter(life_nl="손보").exclude(pay_method__icontains="일시납")
        elif category == "long_life":
            qs = qs.filter(life_nl="생보").exclude(pay_method__icontains="일시납")
        else:
            return []

        rows = (
            qs.annotate(
                insurer_name=NullIf("insurer", Value("")),
            )
            .exclude(insurer_name__isnull=True)
            .exclude(insurer_name__exact="")
            .values("insurer_name")
            .annotate(
                total_count=Count("policy_no"),
                total_amount=Coalesce(
                    Sum("receipt_amount"),
                    Value(0),
                ),
            )
            .order_by("-total_amount", "insurer_name")[:10]
        )

        result = []
        for idx, row in enumerate(rows, start=1):
            result.append({
                "rank": idx,
                "insurer_name": row["insurer_name"],
                "total_count": int(row["total_count"] or 0),
                "total_amount": int(row["total_amount"] or 0),
            })
        return result
    
    def _product_top10(qs, category: str):
        if category == "long":
            qs = qs.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납")
        elif category == "car":
            qs = qs.filter(life_nl="자동차")
        elif category == "long_nonlife":
            qs = qs.filter(life_nl="손보").exclude(pay_method__icontains="일시납")
        elif category == "long_life":
            qs = qs.filter(life_nl="생보").exclude(pay_method__icontains="일시납")
        else:
            return []

        rows = (
            qs.annotate(
                insurer_name=NullIf("insurer", Value("")),
                product_name_norm=Coalesce(
                    NullIf("product_name", Value("")),
                    Value("(상품명 없음)"),
                    output_field=CharField(),
                ),
            )
            .exclude(insurer_name__isnull=True)
            .exclude(insurer_name__exact="")
            .values("insurer_name", "product_name_norm")
            .annotate(
                total_count=Count("policy_no"),
                total_amount=Coalesce(
                    Sum("receipt_amount"),
                    Value(0),
                )
            )
            .order_by("-total_amount", "insurer_name", "product_name_norm")[:10]
        )

        result = []
        for idx, row in enumerate(rows, start=1):
            result.append({
                "rank": idx,
                "insurer_name": row["insurer_name"],
                "product_name": row["product_name_norm"],
                "total_count": int(row["total_count"] or 0),
                "total_amount": int(row["total_amount"] or 0),
            })
        return result

    branch_top10_long = _branch_top10(qs_rank_scope, "long")
    branch_top10_car = _branch_top10(qs_rank_scope, "car")
    branch_top10_nonlife = _branch_top10(qs_rank_scope, "long_nonlife")
    branch_top10_life = _branch_top10(qs_rank_scope, "long_life")

    advisor_top10_long = _advisor_top10(qs_rank_scope, "long")
    advisor_top10_car = _advisor_top10(qs_rank_scope, "car")
    advisor_top10_nonlife = _advisor_top10(qs_rank_scope, "long_nonlife")
    advisor_top10_life = _advisor_top10(qs_rank_scope, "long_life")

    insurer_top10_long = _insurer_top10(qs_rank_scope, "long")
    insurer_top10_car = _insurer_top10(qs_rank_scope, "car")
    insurer_top10_nonlife = _insurer_top10(qs_rank_scope, "long_nonlife")
    insurer_top10_life = _insurer_top10(qs_rank_scope, "long_life")

    product_top10_long = _product_top10(qs_rank_scope, "long")
    product_top10_car = _product_top10(qs_rank_scope, "car")
    product_top10_nonlife = _product_top10(qs_rank_scope, "long_nonlife")
    product_top10_life = _product_top10(qs_rank_scope, "long_life")

    # -----------------------------
    # 9) 그래프 데이터
    # -----------------------------
    chart_day_labels = month_day_labels(ym)
    prev_ym = prev_ym_str(ym)
    prev_year_ym = prev_year_ym_str(ym)

    qs_chart_long = qs_final.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납")
    chart_cumsum = build_cumsum_aligned(qs_chart_long, chart_day_labels)

    qs_chart_car = qs_final.filter(life_nl="자동차")
    car_chart_cumsum = build_cumsum_aligned(qs_chart_car, chart_day_labels)

    qs_chart_nonlife = qs_final.filter(life_nl="손보").exclude(pay_method__icontains="일시납")
    nonlife_chart_cumsum = build_cumsum_aligned(qs_chart_nonlife, chart_day_labels)

    qs_chart_life = qs_final.filter(life_nl="생보").exclude(pay_method__icontains="일시납")
    life_chart_cumsum = build_cumsum_aligned(qs_chart_life, chart_day_labels)

    y_max_value_nl_l = max(max(nonlife_chart_cumsum or [0]), max(life_chart_cumsum or [0]))
    nl_l_y_step, nl_l_y_max = nice_step_and_max(y_max_value_nl_l)

    # 전월 (동일 필터 적용)
    qs_prev_base = SalesRecord.objects.all()
    qs_prev_base, _ = apply_head_scope_to_salesrecord_qs(qs_prev_base, user=request.user)
    qs_prev_base = qs_prev_base.filter(ym=prev_ym)

    qs_prev_scope = apply_common_filters_to_salesrecord_qs(
        qs_prev_base,
        part=filter_part,
        branch=filter_branch,
        q=filter_q,
    )

    if filter_life_nl:
        qs_prev_scope = qs_prev_scope.filter(life_nl=filter_life_nl)
    if filter_insurer:
        qs_prev_scope = qs_prev_scope.filter(insurer=filter_insurer)

    qs_prev_long = qs_prev_scope.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납")
    prev_chart_cumsum = build_cumsum_prevmonth_aligned(qs_prev_long, chart_day_labels, prev_ym)

    qs_prev_car = qs_prev_scope.filter(life_nl="자동차")
    prev_car_chart_cumsum = build_cumsum_prevmonth_aligned(qs_prev_car, chart_day_labels, prev_ym)

    qs_prev_nonlife = qs_prev_scope.filter(life_nl="손보").exclude(pay_method__icontains="일시납")
    prev_nonlife_chart_cumsum = build_cumsum_prevmonth_aligned(qs_prev_nonlife, chart_day_labels, prev_ym)

    qs_prev_life = qs_prev_scope.filter(life_nl="생보").exclude(pay_method__icontains="일시납")
    prev_life_chart_cumsum = build_cumsum_prevmonth_aligned(qs_prev_life, chart_day_labels, prev_ym)

    # 전년도 동월
    qs_py_base = SalesRecord.objects.all()
    qs_py_base, _ = apply_head_scope_to_salesrecord_qs(qs_py_base, user=request.user)
    qs_py_base = qs_py_base.filter(ym=prev_year_ym)

    qs_py_scope = apply_common_filters_to_salesrecord_qs(
        qs_py_base,
        part=filter_part,
        branch=filter_branch,
        q=filter_q,
    )

    if filter_life_nl:
        qs_py_scope = qs_py_scope.filter(life_nl=filter_life_nl)
    if filter_insurer:
        qs_py_scope = qs_py_scope.filter(insurer=filter_insurer)

    qs_py_long = qs_py_scope.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납")
    py_chart_cumsum = build_cumsum_othermonth_aligned(qs_py_long, chart_day_labels, prev_year_ym)

    qs_py_car = qs_py_scope.filter(life_nl="자동차")
    py_car_chart_cumsum = build_cumsum_othermonth_aligned(qs_py_car, chart_day_labels, prev_year_ym)

    qs_py_nonlife = qs_py_scope.filter(life_nl="손보").exclude(pay_method__icontains="일시납")
    py_nonlife_chart_cumsum = build_cumsum_othermonth_aligned(qs_py_nonlife, chart_day_labels, prev_year_ym)

    qs_py_life = qs_py_scope.filter(life_nl="생보").exclude(pay_method__icontains="일시납")
    py_life_chart_cumsum = build_cumsum_othermonth_aligned(qs_py_life, chart_day_labels, prev_year_ym)

    # -----------------------------
    # 10) 부서/지점 옵션
    # -----------------------------
    sr_scope = qs_base  # ym + head 권한 적용된 qs

    user_part_vals = list(
        CustomUser.objects.exclude(part__isnull=True).exclude(part__exact="")
        .values_list("part", flat=True).distinct()
    )
    if request.user.grade == "head":
        my_branch = (request.user.branch or "").strip()
        if my_branch:
            user_part_vals = list(
                CustomUser.objects.filter(branch=my_branch)
                .exclude(part__isnull=True).exclude(part__exact="")
                .values_list("part", flat=True).distinct()
            )

    sr_part_snapshot_vals = list(
        sr_scope.exclude(part_snapshot__isnull=True).exclude(part_snapshot__exact="")
        .values_list("part_snapshot", flat=True).distinct()
    )
    sr_user_part_vals = list(
        sr_scope.exclude(user__part__isnull=True).exclude(user__part__exact="")
        .values_list("user__part", flat=True).distinct()
    )
    part_options = clean_list(user_part_vals + sr_part_snapshot_vals + sr_user_part_vals)

    user_branch_vals = list(
        CustomUser.objects.exclude(branch__isnull=True).exclude(branch__exact="")
        .values_list("branch", flat=True).distinct()
    )
    if request.user.grade == "head":
        my_branch = (request.user.branch or "").strip()
        user_branch_vals = [my_branch] if my_branch else []

    sr_branch_snapshot_vals = list(
        sr_scope.exclude(branch_snapshot__isnull=True).exclude(branch_snapshot__exact="")
        .values_list("branch_snapshot", flat=True).distinct()
    )
    sr_user_branch_vals = list(
        sr_scope.exclude(user__branch__isnull=True).exclude(user__branch__exact="")
        .values_list("user__branch", flat=True).distinct()
    )
    branch_options_all = clean_list(user_branch_vals + sr_branch_snapshot_vals + sr_user_branch_vals)

    part_branch_map: dict[str, list[str]] = {}
    for p in part_options:
        u_br = list(
            CustomUser.objects.filter(part=p)
            .exclude(branch__isnull=True).exclude(branch__exact="")
            .values_list("branch", flat=True).distinct()
        )
        if request.user.grade == "head":
            my_branch = (request.user.branch or "").strip()
            u_br = [my_branch] if my_branch else []

        sr_br_snap = list(
            sr_scope.filter(part_snapshot=p)
            .exclude(branch_snapshot__isnull=True).exclude(branch_snapshot__exact="")
            .values_list("branch_snapshot", flat=True).distinct()
        )
        sr_br_user = list(
            sr_scope.filter(user__part=p)
            .exclude(user__branch__isnull=True).exclude(user__branch__exact="")
            .values_list("user__branch", flat=True).distinct()
        )
        part_branch_map[p] = clean_list(u_br + sr_br_snap + sr_br_user)

    # -----------------------------
    # 11) pagination
    # -----------------------------
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
    return render(request, "dash/dash_retention.html")


@grade_required("superuser")
def dash_goals(request):
    return render(request, "dash/dash_goals.html")