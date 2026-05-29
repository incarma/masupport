# partner/services/efficiency.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from partner.models import (
    EfficiencyChange,
    EfficiencyConfirmAttachment,
    EfficiencyConfirmGroup,
    PartnerChangeLog,
)
from partner.views.utils import (
    build_requester_affiliation_chain,
    get_level_team_filter_user_ids,
)


def get_efficiency_queryset(user, *, month: str, branch: str):
    """EfficiencyChange 조회 쿼리셋 (권한 스코프 적용)."""
    qs = (
        EfficiencyChange.objects.filter(month=month)
        .select_related("requester", "confirm_group")
        .order_by("-id")
    )
    if user.grade == "superuser":
        if branch:
            qs = qs.filter(branch__iexact=branch)
    else:
        qs = qs.filter(branch__iexact=branch)
    if user.grade == "leader":
        allowed_ids = get_level_team_filter_user_ids(user)
        qs = qs.filter(requester_id__in=allowed_ids) if allowed_ids else qs.filter(requester_id=user.id)
    return qs


def get_efficiency_groups_qs(user, *, month: str, branch: str):
    """EfficiencyConfirmGroup 쿼리셋 (권한 스코프 적용, annotated)."""
    gqs = EfficiencyConfirmGroup.objects.filter(month=month).prefetch_related("attachments")
    if user.grade == "superuser":
        if branch:
            gqs = gqs.filter(branch__iexact=branch)
        else:
            return EfficiencyConfirmGroup.objects.none()
    else:
        gqs = gqs.filter(branch__iexact=branch)
    if user.grade == "leader":
        allowed_ids = get_level_team_filter_user_ids(user)
        gqs = gqs.filter(uploader_id__in=allowed_ids) if allowed_ids else gqs.filter(uploader_id=user.id)
    return gqs.annotate(
        row_count=Count("efficiency_rows", distinct=True),
        total_amount=Sum("efficiency_rows__amount"),
    ).order_by("-id")


def create_efficiency_rows(
    user,
    rows: list,
    group: EfficiencyConfirmGroup,
    latest_att: Optional[EfficiencyConfirmAttachment],
    *,
    month: str,
    part: str,
    branch: str,
) -> Tuple[List[EfficiencyChange], int]:
    """EfficiencyChange rows bulk 생성. Returns (saved_objs, skipped)."""
    objs: List[EfficiencyChange] = []
    skipped = 0

    for row in rows:
        if not isinstance(row, dict):
            skipped += 1
            continue

        category = (row.get("category") or "").strip()
        content = (row.get("content") or "").strip()

        try:
            amount = int(row.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0

        if not category or not content or amount <= 0:
            skipped += 1
            continue

        objs.append(
            EfficiencyChange(
                requester=user,
                part=part,
                branch=branch,
                month=month,
                category=category,
                amount=amount,
                ded_id=str(row.get("ded_id") or "").strip(),
                ded_name=(row.get("ded_name") or "").strip(),
                pay_id=str(row.get("pay_id") or "").strip(),
                pay_name=(row.get("pay_name") or "").strip(),
                content=content,
                memo=(row.get("memo") or content[:200]).strip(),
                confirm_group=group,
                confirm_attachment=latest_att,
            )
        )

    if objs:
        EfficiencyChange.objects.bulk_create(objs, batch_size=500)

        PartnerChangeLog.objects.create(
            user=user,
            action="save",
            detail=(
                f"{len(objs)}건 저장 (efficiency / 월:{month} / 부서:{part} / 지점:{branch} "
                f"/ group:{group.confirm_group_id} / skipped:{skipped})"
            ),
        )

    return objs, skipped


def update_group_title(group: EfficiencyConfirmGroup, user) -> None:
    """그룹 title을 오늘날짜 + 소속 체인으로 갱신한다."""
    save_date = timezone.localdate(timezone.now()).strftime("%Y-%m-%d")
    aff = build_requester_affiliation_chain(user)
    new_title = f"{save_date} / {aff}"
    if (group.title or "").strip() != new_title:
        group.title = new_title
        group.save(update_fields=["title"])


def _generate_confirm_group_id(*, uploader_id: str) -> str:
    now = timezone.localtime(timezone.now())
    prefix = now.strftime("%Y%m%d%H%M")
    base = f"{prefix}_{uploader_id}_"
    same_minute_qs = EfficiencyConfirmGroup.objects.select_for_update().filter(
        confirm_group_id__startswith=base
    )
    cnt = same_minute_qs.count()
    seq = min(cnt + 1, 99)
    return f"{base}{seq:02d}"


def get_or_create_confirm_group(
    user,
    incoming_group_id: str,
    *,
    part: str,
    branch: str,
    month: str,
) -> Tuple[EfficiencyConfirmGroup, bool]:
    """기존 그룹 조회 또는 신규 생성. ValueError로 검증 실패 전달.
    Returns (group, group_created).
    """
    if incoming_group_id:
        group = (
            EfficiencyConfirmGroup.objects.select_for_update()
            .filter(confirm_group_id=incoming_group_id)
            .first()
        )
        if not group:
            raise ValueError("confirm_group_id에 해당하는 그룹을 찾을 수 없습니다.")
        if (group.month or "") != month:
            raise ValueError("그룹 월도와 업로드 월도가 다릅니다.")
        if user.grade != "superuser":
            if (group.branch or "") != branch:
                raise ValueError("그룹 지점과 업로드 지점이 다릅니다.")
        else:
            if branch and (group.branch or "") != branch:
                raise ValueError("그룹 지점과 업로드 지점이 다릅니다.")
        return group, False
    else:
        new_group_id = _generate_confirm_group_id(uploader_id=str(getattr(user, "id", "") or ""))
        group = EfficiencyConfirmGroup.objects.create(
            confirm_group_id=new_group_id,
            uploader=user,
            part=part,
            branch=branch,
            month=month,
            title="",
            note="",
        )
        return group, True


def create_confirm_attachment(
    group: EfficiencyConfirmGroup,
    user,
    file,
    *,
    part: str,
    branch: str,
    month: str,
) -> EfficiencyConfirmAttachment:
    """EfficiencyConfirmAttachment 생성."""
    att = EfficiencyConfirmAttachment.objects.create(
        group=group,
        uploader=user,
        part=part,
        branch=branch,
        month=month,
        file=file,
        original_name=file.name or "",
    )
    PartnerChangeLog.objects.create(
        user=user,
        action="confirm_upload",
        detail=(
            f"[efficiency] confirm_group_id={group.confirm_group_id} attachment_id={att.id} "
            f"month={month} branch={branch}"
        ),
    )
    return att


def delete_efficiency_row(obj: EfficiencyChange, user) -> None:
    """EfficiencyChange 단건 삭제 + 변경 로그."""
    obj.delete()
    PartnerChangeLog.objects.create(
        user=user,
        action="delete_row",
        detail=f"efficiency row delete id={obj.pk}",
    )


def delete_efficiency_group(group: EfficiencyConfirmGroup, user) -> List[str]:
    """EfficiencyConfirmGroup + 연관 rows/attachments 삭제.
    삭제할 파일명 목록을 반환 (on_commit 파일 삭제용).
    """
    confirm_group_id = group.confirm_group_id
    branch = group.branch
    files_to_delete = [att.file.name for att in group.attachments.all() if att.file]

    EfficiencyChange.objects.filter(confirm_group=group).delete()
    group.attachments.all().delete()
    group.delete()

    PartnerChangeLog.objects.create(
        user=user,
        action="delete_group",
        detail=f"efficiency group delete confirm_group_id={confirm_group_id}",
    )

    return files_to_delete
