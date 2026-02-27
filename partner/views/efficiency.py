# django_ma/partner/views/efficiency.py
# ------------------------------------------------------------
# ✅ Efficiency(지점효율) API
# - fetch: grouped=1 지원 (groups + rows)
# - save: confirm_group 연결 + title 업데이트
# - delete_row/delete_group
# - confirm_upload/groups API
# ------------------------------------------------------------

import traceback
from typing import Any, Dict, List, Optional

from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, Sum
from django.http import FileResponse, Http404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import grade_required
from accounts.models import CustomUser
from partner.models import (
    EfficiencyChange,
    EfficiencyConfirmAttachment,
    EfficiencyConfirmGroup,
    PartnerChangeLog,
)

from audit.services import log_action
from audit.constants import ACTION

from .responses import json_err, json_ok, parse_json_body
from .utils import (
    build_affiliation_display,
    build_requester_affiliation_chain,
    get_level_team_filter_user_ids,
    normalize_month,
    resolve_branch_for_query,
    resolve_branch_for_write,
    resolve_part_for_write,
)

# ------------------------------------------------------------
# ✅ confirm_group_id 생성(업로드 성공 시점)
# 형식: YYYYMMDDHHMM_사번_순번(2자리)
# ------------------------------------------------------------
def _generate_confirm_group_id(*, uploader_id: str) -> str:
    now = timezone.localtime(timezone.now())
    prefix = now.strftime("%Y%m%d%H%M")  # 분 단위
    base = f"{prefix}_{uploader_id}_"

    same_minute_qs = EfficiencyConfirmGroup.objects.select_for_update().filter(confirm_group_id__startswith=base)
    cnt = same_minute_qs.count()
    seq = min(cnt + 1, 99)  # 현실적으로 99 초과는 거의 없다고 가정
    return f"{base}{seq:02d}"


# ------------------------------------------------------------
# ✅ 지점효율 확인서 양식 다운로드
# ------------------------------------------------------------
@login_required
def efficiency_confirm_template_download(request):
    rel_path = "excel/양식_지점효율확인서.xlsx"
    abs_path = finders.find(rel_path)
    if not abs_path:
        raise Http404("양식 파일을 찾을 수 없습니다.")
    try:
        f = open(abs_path, "rb")
    except OSError:
        raise Http404("양식 파일을 열 수 없습니다.")
    return FileResponse(
        f,
        as_attachment=True,
        filename="양식_지점효율확인서.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ------------------------------------------------------------
# 그룹 payload 빌더
# ------------------------------------------------------------
def _build_efficiency_groups_payload(*, month: str, branch: str, user: CustomUser) -> List[Dict[str, Any]]:
    """
    ✅ Accordion 렌더링용 그룹 구조
    - group_key: confirm_group_id(문자열)
    - group_pk: DB PK(숫자)
    - ✅ 권한별 조회범위 적용:
      superuser: 선택 branch 전체
      head: 자기 branch 전체
      leader(A/B/C): 자기 팀 범위(uploader 기준)
    """
    gqs = EfficiencyConfirmGroup.objects.filter(month=month)

    # ✅ branch scope
    if user.grade == "superuser":
        if branch:
            gqs = gqs.filter(branch__iexact=branch)
        else:
            # superuser가 branch 없이 호출하면 빈 리스트로 (프론트 정책과 동일)
            return []
    else:
        gqs = gqs.filter(branch__iexact=branch)

    # ✅ leader: 팀 범위(uploader 기준)
    if user.grade == "leader":
        allowed_ids = get_level_team_filter_user_ids(user)  # 같은 branch + 같은 level team의 user_id들
        if allowed_ids:
            gqs = gqs.filter(uploader_id__in=allowed_ids)
        else:
            # 레벨/팀 미설정이면 누수 방지: 본인 업로드만
            gqs = gqs.filter(uploader_id=user.id)

    gqs = gqs.annotate(
        row_count=Count("efficiency_rows", distinct=True),
        total_amount=Sum("efficiency_rows__amount"),
    ).order_by("-id")

    groups: List[Dict[str, Any]] = []
    for g in gqs:
        atts = []
        for a in g.attachments.all().order_by("-id"):
            atts.append(
                {
                    "id": a.id,
                    "file_name": a.original_name or (a.file.name.split("/")[-1] if a.file else ""),
                    "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
                    "file": a.file.url if getattr(a, "file", None) and hasattr(a.file, "url") else "",
                }
            )

        cg_id = (g.confirm_group_id or "").strip()
        groups.append(
            {
                "confirm_group_id": cg_id,
                "group_key": cg_id,
                "id": g.id,
                "group_pk": g.id,
                "month": g.month,
                "part": g.part,
                "branch": g.branch,
                "title": g.title or "",
                "note": g.note or "",
                "created_at": g.created_at.strftime("%Y-%m-%d %H:%M") if g.created_at else "",
                "row_count": int(getattr(g, "row_count", 0) or 0),
                "total_amount": int(getattr(g, "total_amount", 0) or 0),
                "attachments": atts,
            }
        )
    return groups


@require_GET
@login_required
@grade_required("superuser", "head", "leader")
def efficiency_fetch(request):
    """
    ✅ rows 응답 유지
    ✅ grouped=1이면 groups(Accordion) 같이 내려줌
    ✅ group_key(confirm_group_id) + group_pk 제공(프론트 매칭)
    """
    try:
        user = request.user
        month = normalize_month(request.GET.get("month") or "")
        branch_param = (request.GET.get("branch") or "").strip()
        branch = resolve_branch_for_query(user, branch_param)

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

        # ✅ leader: 팀 범위(requester 기준)
        if user.grade == "leader":
            allowed_ids = get_level_team_filter_user_ids(user)
            if allowed_ids:
                qs = qs.filter(requester_id__in=allowed_ids)
            else:
                # 레벨/팀 미설정이면 누수 방지: 본인 작성만
                qs = qs.filter(requester_id=user.id)

        rows = []
        for ec in qs:
            amount_val = int(ec.amount or 0)
            tax_val = int(round(amount_val * 0.033)) if amount_val > 0 else 0

            cg = ec.confirm_group
            cg_id = (getattr(cg, "confirm_group_id", "") or "").strip() if cg else ""
            cg_pk = getattr(cg, "id", None) if cg else None

            rows.append(
                {
                    "id": ec.id,
                    "requester_name": getattr(ec.requester, "name", "") if ec.requester else "",
                    "requester_id": getattr(ec.requester, "id", "") if ec.requester else "",
                    "requester_branch": build_affiliation_display(ec.requester) if ec.requester else "",
                    "category": ec.category or "",
                    "amount": amount_val,
                    "tax": tax_val,
                    "ded_name": ec.ded_name or "",
                    "ded_id": ec.ded_id or "",
                    "pay_name": ec.pay_name or "",
                    "pay_id": ec.pay_id or "",
                    "content": ec.content or "",
                    "memo": ec.memo or "",
                    "request_date": ec.created_at.strftime("%Y-%m-%d") if ec.created_at else "",
                    "process_date": ec.process_date.strftime("%Y-%m-%d") if ec.process_date else "",
                    "confirm_group_id": cg_id,
                    "group_key": cg_id,
                    "confirm_group_pk": cg_pk,
                    "group_pk": cg_pk,
                }
            )

        payload: Dict[str, Any] = {"kind": "efficiency", "rows": rows}

        if (request.GET.get("grouped") or "").strip() == "1":
            payload["groups"] = _build_efficiency_groups_payload(month=month, branch=branch, user=user)

        return json_ok(payload)

    except Exception as e:
        traceback.print_exc()
        return json_err(str(e), status=500, extra={"rows": [], "groups": []})


@require_POST
@login_required
@grade_required("superuser", "head", "leader")
@transaction.atomic
def efficiency_save(request):
    """
    ✅ Efficiency 저장
    - payload.confirm_group_id 필수
    - EfficiencyChange.confirm_group 연결
    - 저장 시 group.title을 "YYYY-MM-DD / 지점 팀A 팀B 팀C" 로 업데이트
    """
    try:
        payload = parse_json_body(request)
        items = payload.get("rows", [])
        if not isinstance(items, list):
            return json_err("rows 형식이 올바르지 않습니다.", status=400)

        month = normalize_month(payload.get("month") or "")
        if not month:
            return json_err("month(YYYY-MM)가 없습니다.", status=400)

        user = request.user
        part = resolve_part_for_write(user, payload.get("part") or "")
        branch = resolve_branch_for_write(user, payload.get("branch") or "")

        if getattr(user, "grade", "") == "superuser" and not (branch or "").strip():
            return json_err("superuser는 branch가 필요합니다.", status=400)

        confirm_group_id = (payload.get("confirm_group_id") or "").strip()
        if not confirm_group_id:
            return json_err("confirm_group_id가 없습니다. 확인서 업로드 후 저장하세요.", status=400)

        group = (
            EfficiencyConfirmGroup.objects.select_for_update()
            .filter(confirm_group_id=confirm_group_id)
            .first()
        )
        if not group:
            return json_err("confirm_group_id에 해당하는 그룹을 찾을 수 없습니다.", status=404)

        if (group.month or "").strip() != month:
            return json_err("그룹 월도와 저장 월도가 다릅니다.", status=400)

        req_branch = (branch or "").strip()
        group_branch = (group.branch or "").strip()

        if user.grade == "superuser":
            if req_branch and group_branch != req_branch:
                return json_err("그룹 지점과 저장 지점이 다릅니다.", status=400)
        else:
            if group_branch != req_branch:
                return json_err("그룹 지점과 저장 지점이 다릅니다.", status=400)

        # ✅ 그룹 title 업데이트
        save_date = timezone.localdate(timezone.now()).strftime("%Y-%m-%d")
        aff = build_requester_affiliation_chain(user)
        new_title = f"{save_date} / {aff}"
        if (group.title or "").strip() != new_title:
            group.title = new_title
            group.save(update_fields=["title"])

        latest_att = group.attachments.order_by("-id").first()

        objs: List[EfficiencyChange] = []
        skipped = 0

        for row in items:
            if not isinstance(row, dict):
                skipped += 1
                continue

            category = (row.get("category") or "").strip()
            content = (row.get("content") or "").strip()

            try:
                amount = int(row.get("amount", 0))
            except Exception:
                amount = 0

            if not category or not content or amount <= 0:
                skipped += 1
                continue

            ded_id = str(row.get("ded_id") or "").strip()
            ded_name = (row.get("ded_name") or "").strip()
            pay_id = str(row.get("pay_id") or "").strip()
            pay_name = (row.get("pay_name") or "").strip()
            memo = (row.get("memo") or content[:200]).strip()

            objs.append(
                EfficiencyChange(
                    requester=user,
                    part=part,
                    branch=branch,
                    month=month,
                    category=category,
                    amount=amount,
                    ded_id=ded_id,
                    ded_name=ded_name,
                    pay_id=pay_id,
                    pay_name=pay_name,
                    content=content,
                    memo=memo,
                    confirm_group=group,
                    confirm_attachment=latest_att,  # 필요 없으면 모델/프론트에서 제거 가능
                )
            )

        if not objs:
            return json_err("저장할 유효 데이터가 없습니다. (구분/금액/내용 확인)", status=400)

        EfficiencyChange.objects.bulk_create(objs, batch_size=500)

        PartnerChangeLog.objects.create(
            user=user,
            action="save",
            detail=(
                f"{len(objs)}건 저장 (efficiency / 월:{month} / 부서:{part} / 지점:{branch} "
                f"/ group:{group.confirm_group_id} / skipped:{skipped})"
            ),
        )

        return json_ok(
            {
                "saved_count": len(objs),
                "skipped": skipped,
                "confirm_group_id": group.confirm_group_id,
                "group_title": group.title or "",
            }
        )

    except Exception as e:
        traceback.print_exc()
        return json_err(str(e), status=400)


@require_POST
@login_required
@grade_required("superuser", "head")
@transaction.atomic
def efficiency_delete_row(request):
    """✅ 그룹 내부 행(단건) 삭제"""
    try:
        payload = parse_json_body(request)
        row_id = payload.get("id")
        if not row_id:
            return json_err("id가 없습니다.", status=400)

        obj = EfficiencyChange.objects.select_for_update().filter(id=row_id).first()
        if not obj:
            return json_err("삭제 대상이 없습니다.", status=404)

        user = request.user
        if user.grade != "superuser":
            if (obj.branch or "") != (getattr(user, "branch", "") or ""):
                return json_err("권한이 없습니다.", status=403)

        obj.delete()

        PartnerChangeLog.objects.create(
            user=user,
            action="delete_row",
            detail=f"efficiency row delete id={row_id}",
        )
        return json_ok()

    except Exception as e:
        traceback.print_exc()
        return json_err(str(e), status=400)


@require_POST
@login_required
@grade_required("superuser", "head")
@transaction.atomic
def efficiency_delete_group(request):
    """
    ✅ 그룹 삭제(실제 파일 포함)
    - group_id: confirm_group_id(문자열) 또는 group pk(숫자) 허용
    """
    payload = parse_json_body(request)
    group_id = str(payload.get("group_id") or "").strip()
    if not group_id:
        return json_err("group_id가 없습니다.", status=400)

    group = EfficiencyConfirmGroup.objects.select_for_update().filter(confirm_group_id=group_id).first()
    if group is None and group_id.isdigit():
        group = EfficiencyConfirmGroup.objects.select_for_update().filter(pk=int(group_id)).first()

    if group is None:
        return json_err("그룹을 찾을 수 없습니다.", status=404)

    if request.user.grade == "head":
        rec_branch = (group.branch or "").strip()
        my_branch = (request.user.branch or "").strip()
        if rec_branch and my_branch and rec_branch != my_branch:
            return json_err("다른 지점 그룹은 삭제할 수 없습니다.", status=403)

    try:
        EfficiencyChange.objects.filter(confirm_group=group).delete()

        for att in group.attachments.all():
            if att.file:
                att.file.delete(save=False)
            att.delete()

        group.delete()

        PartnerChangeLog.objects.create(
            user=request.user,
            action="delete_group",
            detail=f"efficiency group delete confirm_group_id={group.confirm_group_id}",
        )
        return json_ok()

    except Exception as e:
        traceback.print_exc()
        return json_err(f"삭제 중 오류: {e}", status=500)


@require_POST
@login_required
@grade_required("superuser", "head", "leader")
@transaction.atomic
def efficiency_confirm_upload(request):
    """
    ✅ 확인서 업로드
    - confirm_group_id가 없으면 업로드 시점에 그룹 생성
    - 있으면 동일 그룹에 첨부 누적
    """
    f = request.FILES.get("file")
    if not f:
        return json_err("파일이 없습니다.", status=400)

    allowed = (".pdf", ".png", ".jpg", ".jpeg", ".heic", ".xlsx", ".xls")
    name_lower = (f.name or "").lower()
    if allowed and not any(name_lower.endswith(ext) for ext in allowed):
        return json_err("허용되지 않는 파일 형식입니다.", status=400)

    payload_part = (request.POST.get("part") or "").strip()
    payload_branch = (request.POST.get("branch") or "").strip()
    payload_month = normalize_month(request.POST.get("month") or "")
    incoming_group_id = (request.POST.get("confirm_group_id") or "").strip()

    user = request.user
    part = resolve_part_for_write(user, payload_part)
    branch = resolve_branch_for_write(user, payload_branch)

    if not payload_month:
        return json_err("month(YYYY-MM)가 없습니다.", status=400)
    if user.grade == "superuser" and not branch:
        return json_err("superuser는 branch가 필요합니다.", status=400)

    group: Optional[EfficiencyConfirmGroup] = None
    group_created = False

    if incoming_group_id:
        group = EfficiencyConfirmGroup.objects.select_for_update().filter(confirm_group_id=incoming_group_id).first()
        if not group:
            return json_err("confirm_group_id에 해당하는 그룹을 찾을 수 없습니다.", status=404)

        if (group.month or "") != payload_month:
            return json_err("그룹 월도와 업로드 월도가 다릅니다.", status=400)

        if user.grade != "superuser":
            if (group.branch or "") != branch:
                return json_err("그룹 지점과 업로드 지점이 다릅니다.", status=400)
        else:
            if branch and (group.branch or "") != branch:
                return json_err("그룹 지점과 업로드 지점이 다릅니다.", status=400)

    else:
        new_group_id = _generate_confirm_group_id(uploader_id=str(getattr(user, "id", "") or ""))
        group = EfficiencyConfirmGroup.objects.create(
            confirm_group_id=new_group_id,
            uploader=user,
            part=part,
            branch=branch,
            month=payload_month,
            title="",
            note="",
        )
        group_created = True

    att = EfficiencyConfirmAttachment.objects.create(
        group=group,
        uploader=user,
        part=part,
        branch=branch,
        month=payload_month,
        file=f,
        original_name=f.name or "",
    )

    # ✅ AuditLog: Efficiency Confirm 업로드(감사 핵심)
    try:
        log_action(
            request,
            ACTION.EFFICIENCY_CONFIRM_UPLOAD,
            obj=att,
            meta={
                "month": payload_month,
                "part": part,
                "branch": branch,
                "confirm_group_id": getattr(group, "confirm_group_id", ""),
                "group_created": bool(group_created),
                "attachment_id": getattr(att, "id", None),
                "file_name": (att.original_name or ""),
                "size": getattr(getattr(att, "file", None), "size", None),
            },
            success=True,
        )
    except Exception:
        pass

    PartnerChangeLog.objects.create(
        user=user,
        action="confirm_upload",
        detail=(
            f"[efficiency] confirm_group_id={group.confirm_group_id} attachment_id={att.id} "
            f"month={payload_month} branch={branch}"
        ),
    )

    return json_ok(
        {
            "confirm_group_id": group.confirm_group_id,
            "attachment_id": att.id,
            "file_name": att.original_name or (att.file.name.split("/")[-1] if att.file else ""),
            "group_created_at": group.created_at.strftime("%Y-%m-%d %H:%M") if group.created_at else "",
        }
    )


@require_GET
@login_required
@grade_required("superuser", "head", "leader")
def efficiency_confirm_groups(request):
    """✅ Accordion 전용 그룹 목록 API"""
    try:
        user = request.user
        month = normalize_month(request.GET.get("month") or "")
        branch_param = (request.GET.get("branch") or "").strip()
        branch = resolve_branch_for_query(user, branch_param)

        if not month:
            return json_err("month(YYYY-MM)가 없습니다.", status=400)

        if user.grade == "superuser" and not branch:
            return json_ok({"groups": []})

        groups = _build_efficiency_groups_payload(month=month, branch=branch, user=user)
        return json_ok({"groups": groups})
    except Exception as e:
        traceback.print_exc()
        return json_err(str(e), status=500, extra={"groups": []})
