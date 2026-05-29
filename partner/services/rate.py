# partner/services/rate.py
from __future__ import annotations

from typing import List, Tuple

from accounts.models import CustomUser
from partner.models import RateChange, RateTable
from partner.views.utils import (
    can_use_target_in_branch,
    find_table_rate,
    get_level_team_filter_user_ids,
    to_str,
)
from django.db.models import Q


def get_rate_queryset(user, *, month: str, branch: str):
    """RateChange 조회 쿼리셋 (권한 스코프 적용)."""
    qs = RateChange.objects.filter(month=month).select_related("requester", "target")
    if user.grade == "superuser":
        if branch:
            qs = qs.filter(branch__iexact=branch)
    else:
        qs = qs.filter(branch__iexact=branch)
    if user.grade == "leader":
        allowed_ids = get_level_team_filter_user_ids(user)
        team_q = Q(requester_id__in=allowed_ids) if allowed_ids else Q()
        qs = qs.filter(Q(requester_id=user.id) | team_q)
    return qs.order_by("-id")


def get_target_rate_info(target: CustomUser) -> Tuple[str, str, str, str]:
    """대상자의 현재 요율표 정보 조회. (before_ftable, before_frate, before_ltable, before_lrate) 반환."""
    rt = RateTable.objects.filter(user=target).first()
    before_ftable = rt.non_life_table if rt else ""
    before_ltable = rt.life_table if rt else ""
    before_frate = find_table_rate(target.branch, before_ftable)
    before_lrate = find_table_rate(target.branch, before_ltable)
    return before_ftable, before_frate, before_ltable, before_lrate


def create_rate_rows(
    user, rows: list, *, month: str, part: str, branch: str
) -> Tuple[int, List[str]]:
    """RateChange rows 생성.
    권한 범위 밖 대상자 포함 시 PermissionError.
    Returns (saved_count, target_ids).
    """
    saved = 0
    target_ids: List[str] = []

    for r in rows:
        target_id = to_str(r.get("target_id") or "")
        if not target_id:
            continue
        target = CustomUser.objects.filter(id=target_id).first()
        if not target:
            continue
        if not can_use_target_in_branch(user, target, branch):
            raise PermissionError("권한 범위 밖의 대상자가 포함되어 있습니다.")

        before_ftable, before_frate, before_ltable, before_lrate = get_target_rate_info(target)

        after_ftable = to_str(r.get("after_ftable") or "")
        after_ltable = to_str(r.get("after_ltable") or "")
        after_frate = find_table_rate(target.branch, after_ftable)
        after_lrate = find_table_rate(target.branch, after_ltable)
        memo = to_str(r.get("memo") or "")

        RateChange.objects.create(
            requester=user,
            target=target,
            part=part,
            branch=branch,
            month=month,
            before_ftable=before_ftable,
            before_frate=before_frate,
            before_ltable=before_ltable,
            before_lrate=before_lrate,
            after_ftable=after_ftable,
            after_frate=after_frate,
            after_ltable=after_ltable,
            after_lrate=after_lrate,
            memo=memo,
        )
        saved += 1
        target_ids.append(str(target.id))

    return saved, target_ids
