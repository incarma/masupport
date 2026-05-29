# partner/services/structure.py
from __future__ import annotations

from accounts.models import CustomUser
from partner.models import PartnerChangeLog, StructureChange
from partner.views.utils import (
    build_affiliation_display,
    can_use_target_in_branch,
    leader_requester_scope_q,
    to_str,
)

_DELETE_PRIVILEGED_GRADES = ("superuser", "head")


def get_structure_queryset(user, *, month: str, branch: str):
    """StructureChange 조회 쿼리셋 (권한 스코프 적용)."""
    qs = (
        StructureChange.objects.filter(month=month)
        .select_related("requester", "target")
    )
    if user.grade == "superuser":
        if branch:
            qs = qs.filter(branch__iexact=branch)
    else:
        qs = qs.filter(branch__iexact=branch)
    if user.grade == "leader":
        qs = qs.filter(leader_requester_scope_q(user))
    return qs.order_by("-id")


def create_structure_rows(user, rows: list, *, month: str, part: str, branch: str) -> int:
    """StructureChange rows 생성. 권한 범위 밖 대상자 포함 시 PermissionError."""
    created_count = 0
    for row in rows:
        target_id = to_str(row.get("target_id"))
        if not target_id:
            continue
        target = CustomUser.objects.filter(id=target_id).first()
        if not target:
            continue
        if not can_use_target_in_branch(user, target, branch):
            raise PermissionError("권한 범위 밖의 대상자가 포함되어 있습니다.")
        StructureChange.objects.create(
            requester=user,
            target=target,
            part=part,
            branch=branch,
            month=month,
            target_branch=build_affiliation_display(target),
            chg_branch=to_str(row.get("chg_branch") or "-") or "-",
            or_flag=bool(row.get("or_flag", False)),
            rank=to_str(row.get("tg_rank") or row.get("rank") or "-") or "-",
            chg_rank=to_str(row.get("chg_rank") or "-") or "-",
            memo=to_str(row.get("memo")),
        )
        created_count += 1

    PartnerChangeLog.objects.create(
        user=user,
        action="save",
        detail=f"{created_count}건 저장 (structure / 월:{month} / 부서:{part} / 지점:{branch})",
    )
    return created_count


def can_delete_structure_change(user, record: StructureChange) -> bool:
    if getattr(user, "grade", None) in _DELETE_PRIVILEGED_GRADES:
        return True
    return to_str(getattr(record, "requester_id", "")) == to_str(getattr(user, "id", ""))


def delete_structure_change(record: StructureChange, user) -> int:
    """단건 삭제. 권한 없으면 PermissionError. 삭제된 ID 반환."""
    if not can_delete_structure_change(user, record):
        raise PermissionError("삭제 권한이 없습니다.")
    deleted_id = record.id
    record.delete()
    PartnerChangeLog.objects.create(
        user=user,
        action="delete",
        detail=f"StructureChange #{deleted_id} 삭제",
    )
    return deleted_id
