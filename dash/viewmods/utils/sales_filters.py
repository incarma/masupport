# django_ma/dash/viewmods/utils/sales_filters.py
from __future__ import annotations

from django.db.models import Q, QuerySet

from dash.services.sales import clean_list  # noqa: F401  (re-export for backward compat)


def apply_head_scope_to_salesrecord_qs(qs: QuerySet, *, user) -> tuple[QuerySet, str]:
    """
    head 권한이면 본인 지점만 강제.
    return: (qs, forced_branch_or_empty)
    """
    if getattr(user, "grade", "") != "head":
        return qs, ""
    my_branch = (getattr(user, "branch", "") or "").strip()
    if not my_branch:
        return qs.none(), ""
    qs = qs.filter(Q(branch_snapshot=my_branch) | Q(user__branch=my_branch))
    return qs, my_branch


def apply_common_filters_to_salesrecord_qs(
    qs: QuerySet,
    *,
    part: str,
    branch: str,
    q: str,
) -> QuerySet:
    """
    part/branch/q 공통 필터 적용 (기존 views.py 로직 그대로)
    """
    if part:
        qs = qs.filter(Q(user__part=part) | Q(part_snapshot=part))
    if branch:
        qs = qs.filter(Q(user__branch=branch) | Q(branch_snapshot=branch))
    if q:
        qs = qs.filter(
            Q(policy_no__icontains=q)
            | Q(contractor__icontains=q)
            | Q(name_snapshot__icontains=q)
            | Q(emp_id_snapshot__icontains=q)
            | Q(user__id__icontains=q)
            | Q(user__name__icontains=q)
            | Q(vehicle_no__icontains=q)
        )
    return qs