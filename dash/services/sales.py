# django_ma/dash/services/sales.py
from __future__ import annotations

import logging

from django.core.cache import cache
from django.db.models import Q, Sum, Value, CharField, Count
from django.db.models.functions import Coalesce, NullIf

from accounts.models import CustomUser

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 30  # 30분

_VALID_CATEGORIES = frozenset({"long", "car", "long_nonlife", "long_life"})


def clean_list(vals) -> list[str]:
    """중복 제거 + 정렬된 문자열 목록. 빈 값·'nan' 제외."""
    return sorted({
        str(v).strip() for v in vals
        if str(v).strip() and str(v).strip().lower() != "nan"
    })


def build_user_map(emp_ids: set[str]) -> dict[str, "CustomUser"]:
    """사번 집합 → {사번: CustomUser} 맵. 단건 N+1 방지용 선행 조회."""
    if not emp_ids:
        return {}
    return {str(u.id): u for u in CustomUser.objects.filter(id__in=emp_ids)}


def get_life_nl_insurer_map(qs_map_scope, ym: str, part: str, branch: str) -> dict[str, list[str]]:
    """손생별 보험사 목록 맵 (캐시 30분 적용)."""
    cache_key = f"dash:lifeinsmap:{ym}:{part or '*'}:{branch or '*'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = {}
    for ln in ["손보", "생보", "자동차"]:
        raw = list(
            qs_map_scope.filter(life_nl=ln)
            .exclude(insurer__isnull=True).exclude(insurer__exact="")
            .values_list("insurer", flat=True).distinct()
        )
        result[ln] = clean_list(raw)
    cache.set(cache_key, result, CACHE_TTL)
    return result


def get_insurer_options(
    qs_pre_insurer,
    ym: str,
    part: str,
    branch: str,
    life_nl: str,
    q: str,
) -> list[str]:
    """보험사 옵션 목록 (q 있을 때는 캐시 스킵)."""
    if q:
        raw = list(
            qs_pre_insurer
            .exclude(insurer__isnull=True).exclude(insurer__exact="")
            .values_list("insurer", flat=True).distinct()
        )
        return clean_list(raw)
    cache_key = f"dash:insurers:{ym}:{part or '*'}:{branch or '*'}:{life_nl or '*'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    raw = list(
        qs_pre_insurer
        .exclude(insurer__isnull=True).exclude(insurer__exact="")
        .values_list("insurer", flat=True).distinct()
    )
    result = clean_list(raw)
    cache.set(cache_key, result, CACHE_TTL)
    return result


def get_dropdown_options(
    user, qs_base
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """
    부서/지점 드롭다운 옵션과 part→branch 맵 반환.
    returns: (part_options, branch_options_all, part_branch_map)
    """
    is_head = getattr(user, "grade", "") == "head"
    my_branch = (getattr(user, "branch", "") or "").strip()

    # part options
    if is_head and my_branch:
        user_part_vals = list(
            CustomUser.objects.filter(branch=my_branch)
            .exclude(part__isnull=True).exclude(part__exact="")
            .values_list("part", flat=True).distinct()
        )
    else:
        user_part_vals = list(
            CustomUser.objects.exclude(part__isnull=True).exclude(part__exact="")
            .values_list("part", flat=True).distinct()
        )

    sr_part_snapshot_vals = list(
        qs_base.exclude(part_snapshot__isnull=True).exclude(part_snapshot__exact="")
        .values_list("part_snapshot", flat=True).distinct()
    )
    sr_user_part_vals = list(
        qs_base.exclude(user__part__isnull=True).exclude(user__part__exact="")
        .values_list("user__part", flat=True).distinct()
    )
    part_options = clean_list(user_part_vals + sr_part_snapshot_vals + sr_user_part_vals)

    # branch options
    if is_head:
        user_branch_vals = [my_branch] if my_branch else []
    else:
        user_branch_vals = list(
            CustomUser.objects.exclude(branch__isnull=True).exclude(branch__exact="")
            .values_list("branch", flat=True).distinct()
        )

    sr_branch_snapshot_vals = list(
        qs_base.exclude(branch_snapshot__isnull=True).exclude(branch_snapshot__exact="")
        .values_list("branch_snapshot", flat=True).distinct()
    )
    sr_user_branch_vals = list(
        qs_base.exclude(user__branch__isnull=True).exclude(user__branch__exact="")
        .values_list("user__branch", flat=True).distinct()
    )
    branch_options_all = clean_list(
        user_branch_vals + sr_branch_snapshot_vals + sr_user_branch_vals
    )

    # part → branch 맵
    part_branch_map: dict[str, list[str]] = {}
    for p in part_options:
        if is_head:
            u_br = [my_branch] if my_branch else []
        else:
            u_br = list(
                CustomUser.objects.filter(part=p)
                .exclude(branch__isnull=True).exclude(branch__exact="")
                .values_list("branch", flat=True).distinct()
            )
        sr_br_snap = list(
            qs_base.filter(part_snapshot=p)
            .exclude(branch_snapshot__isnull=True).exclude(branch_snapshot__exact="")
            .values_list("branch_snapshot", flat=True).distinct()
        )
        sr_br_user = list(
            qs_base.filter(user__part=p)
            .exclude(user__branch__isnull=True).exclude(user__branch__exact="")
            .values_list("user__branch", flat=True).distinct()
        )
        part_branch_map[p] = clean_list(u_br + sr_br_snap + sr_br_user)

    return part_options, branch_options_all, part_branch_map


def _apply_category_filter(qs, category: str):
    if category == "long":
        return qs.exclude(life_nl="자동차").exclude(pay_method__icontains="일시납")
    if category == "car":
        return qs.filter(life_nl="자동차")
    if category == "long_nonlife":
        return qs.filter(life_nl="손보").exclude(pay_method__icontains="일시납")
    if category == "long_life":
        return qs.filter(life_nl="생보").exclude(pay_method__icontains="일시납")
    return qs.none()


def get_branch_top10(qs, category: str) -> list[dict]:
    if category not in _VALID_CATEGORIES:
        return []
    qs = _apply_category_filter(qs, category)
    rows = (
        qs.annotate(
            channel_name=Coalesce("user__channel", Value(""), output_field=CharField()),
            part_name=Coalesce("user__part", "part_snapshot", output_field=CharField()),
            branch_name=Coalesce("user__branch", "branch_snapshot", output_field=CharField()),
        )
        .exclude(channel_name__isnull=True).exclude(channel_name__exact="")
        .exclude(part_name__isnull=True).exclude(part_name__exact="")
        .exclude(branch_name__isnull=True).exclude(branch_name__exact="")
        .values("channel_name", "part_name", "branch_name")
        .annotate(
            total_count=Count("policy_no"),
            total_amount=Coalesce(Sum("receipt_amount"), Value(0)),
        )
        .order_by("-total_amount", "channel_name", "part_name", "branch_name")[:10]
    )
    return [
        {
            "rank": idx,
            "channel_name": row["channel_name"],
            "part_name": row["part_name"],
            "branch_name": row["branch_name"],
            "total_count": int(row["total_count"] or 0),
            "total_amount": int(row["total_amount"] or 0),
        }
        for idx, row in enumerate(rows, start=1)
    ]


def get_advisor_top10(qs, category: str, advisor_branch: str = "") -> list[dict]:
    if category not in _VALID_CATEGORIES:
        return []
    qs = _apply_category_filter(qs, category)
    if advisor_branch:
        qs = qs.filter(Q(user__branch=advisor_branch) | Q(branch_snapshot=advisor_branch))
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
        .exclude(advisor_name__isnull=True).exclude(advisor_name__exact="")
        .exclude(advisor_emp_id__isnull=True).exclude(advisor_emp_id__exact="")
        .exclude(branch_name__isnull=True).exclude(branch_name__exact="")
        .values("branch_name", "advisor_name", "advisor_emp_id")
        .annotate(
            total_count=Count("policy_no"),
            total_amount=Coalesce(Sum("receipt_amount"), Value(0)),
        )
        .order_by("-total_amount", "branch_name", "advisor_name", "advisor_emp_id")[:10]
    )
    return [
        {
            "rank": idx,
            "branch_name": row["branch_name"],
            "advisor_name": row["advisor_name"],
            "advisor_emp_id": row["advisor_emp_id"],
            "total_count": int(row["total_count"] or 0),
            "total_amount": int(row["total_amount"] or 0),
        }
        for idx, row in enumerate(rows, start=1)
    ]


def get_insurer_top10(qs, category: str) -> list[dict]:
    if category not in _VALID_CATEGORIES:
        return []
    qs = _apply_category_filter(qs, category)
    rows = (
        qs.annotate(insurer_name=NullIf("insurer", Value("")))
        .exclude(insurer_name__isnull=True).exclude(insurer_name__exact="")
        .values("insurer_name")
        .annotate(
            total_count=Count("policy_no"),
            total_amount=Coalesce(Sum("receipt_amount"), Value(0)),
        )
        .order_by("-total_amount", "insurer_name")[:10]
    )
    return [
        {
            "rank": idx,
            "insurer_name": row["insurer_name"],
            "total_count": int(row["total_count"] or 0),
            "total_amount": int(row["total_amount"] or 0),
        }
        for idx, row in enumerate(rows, start=1)
    ]


def get_product_top10(qs, category: str) -> list[dict]:
    if category not in _VALID_CATEGORIES:
        return []
    qs = _apply_category_filter(qs, category)
    rows = (
        qs.annotate(
            insurer_name=NullIf("insurer", Value("")),
            product_name_norm=Coalesce(
                NullIf("product_name", Value("")),
                Value("(상품명 없음)"),
                output_field=CharField(),
            ),
        )
        .exclude(insurer_name__isnull=True).exclude(insurer_name__exact="")
        .values("insurer_name", "product_name_norm")
        .annotate(
            total_count=Count("policy_no"),
            total_amount=Coalesce(Sum("receipt_amount"), Value(0)),
        )
        .order_by("-total_amount", "insurer_name", "product_name_norm")[:10]
    )
    return [
        {
            "rank": idx,
            "insurer_name": row["insurer_name"],
            "product_name": row["product_name_norm"],
            "total_count": int(row["total_count"] or 0),
            "total_amount": int(row["total_amount"] or 0),
        }
        for idx, row in enumerate(rows, start=1)
    ]


def get_recent_upload_logs(count: int = 4) -> list[dict]:
    """최근 유지율 업로드 로그. 마이그레이션 미실행 시 빈 목록 반환."""
    try:
        from dash.models import RetentionUploadLog
        return list(
            RetentionUploadLog.objects.order_by("-uploaded_at")[:count]
            .values("ym", "life_nl", "file_name", "row_count", "uploaded_at")
        )
    except Exception:
        return []
