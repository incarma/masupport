# django_ma/partner/views/grades.py
# ------------------------------------------------------------
# ✅ Permission Management (manage_grades + excel upload + datatables api + level update)
# - leader 명단 새로고침 시 유지
# - leader인데 SubAdminTemp 없는 경우 자동 생성
# - signals/승격/강등 상황에서도 팀/직급 덮어쓰기 최소화
# - excel 업로드: 팀/직급만 최신 반영, level/grade는 불필요한 덮어쓰기 금지
# - DataTables 검색: SubAdminTemp 검색도 "현재 범위 사용자"로 제한
# ------------------------------------------------------------

from __future__ import annotations

import logging
from urllib.parse import urlencode

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from accounts.models import CustomUser
from audit.constants import ACTION
from audit.services import log_action
from partner.models import SubAdminTemp
from partner.services import grades as svc

from .constants import BRANCH_PARTS
from .utils import find_part_by_branch, to_str


logger = logging.getLogger(__name__)

MIDDLE_GRADES = ("leader",)
LEVELS = ["-", "A레벨", "B레벨", "C레벨"]


def _build_redirect_url(base_name: str, params: dict) -> str:
    base = reverse(base_name)
    clean = {k: to_str(v) for k, v in (params or {}).items() if to_str(v)}
    return f"{base}?{urlencode(clean)}" if clean else base


@login_required
@grade_required("superuser", "head")
def manage_grades(request):
    user = request.user
    parts = sorted(list(BRANCH_PARTS.keys()))

    selected_channel = to_str(request.GET.get("channel"))
    selected_part = to_str(request.GET.get("part"))
    selected_branch = to_str(request.GET.get("branch"))

    leader_base_qs = CustomUser.objects.filter(grade__in=MIDDLE_GRADES, status="재직")

    if user.grade == "superuser":
        if selected_channel and selected_part and selected_branch:
            leader_qs = leader_base_qs.filter(
                channel=selected_channel,
                part=selected_part,
                branch=selected_branch,
            )
            svc.ensure_subadmin_temp_for_users(leader_qs)

            subadmin_qs = (
                SubAdminTemp.objects.select_related("user")
                .filter(user__in=leader_qs)
                .order_by("name", "user__id")
            )

            users_all = CustomUser.objects.filter(
                channel=selected_channel,
                part=selected_part,
                branch=selected_branch,
                status="재직",
            ).order_by("name", "id")
        else:
            subadmin_qs = SubAdminTemp.objects.none()
            users_all = CustomUser.objects.none()
    else:
        selected_branch = to_str(user.branch)
        selected_part = find_part_by_branch(selected_branch) or to_str(user.part)

        leader_qs = leader_base_qs.filter(branch=selected_branch)
        svc.ensure_subadmin_temp_for_users(leader_qs)

        subadmin_qs = (
            SubAdminTemp.objects.select_related("user")
            .filter(user__in=leader_qs)
            .order_by("name", "user__id")
        )

        users_all = CustomUser.objects.filter(branch=selected_branch, status="재직").order_by("name", "id")

    empty_message_subadmin = "" if subadmin_qs.exists() else "표시할 중간관리자가 없습니다."

    return render(
        request,
        "partner/manage_grades.html",
        {
            "parts": parts,
            "selected_channel": selected_channel or None,
            "selected_part": selected_part or None,
            "selected_branch": selected_branch or None,
            "users_subadmin": subadmin_qs,
            "users_all": users_all,
            "empty_message_subadmin": empty_message_subadmin,
            "levels": LEVELS,
        },
    )


@transaction.atomic
@login_required
@grade_required("superuser", "head")
def upload_grades_excel(request):
    """
    ✅ 권한관리 엑셀 업로드:
    - 목적: 팀/직급 최신 반영
    - 정책:
      - team_a/b/c, position은 업로드 값으로 반영
      - level은 기존값 유지(없으면 "-")
      - grade는 기존값 유지(비어있으면 CustomUser.grade로 채움)
      - name/part/branch는 CustomUser 기준으로 동기화
    """
    redirect_channel = to_str(request.GET.get("channel"))
    redirect_part = to_str(request.GET.get("part"))
    redirect_branch = to_str(request.GET.get("branch"))

    def _redirect():
        return redirect(
            _build_redirect_url(
                "partner:manage_grades",
                {"channel": redirect_channel, "part": redirect_part, "branch": redirect_branch},
            )
        )

    if not (request.method == "POST" and request.FILES.get("excel_file")):
        messages.warning(request, "엑셀 파일을 선택하세요.")
        return _redirect()

    file = request.FILES["excel_file"]

    try:
        df = pd.read_excel(file, sheet_name="업로드").fillna("")
        required_cols = ["사번", "팀A", "팀B", "팀C", "직급", "성명"]
        for col in required_cols:
            if col not in df.columns:
                messages.error(request, f"엑셀에 '{col}' 컬럼이 없습니다.")
                return _redirect()

        for col in ["부서", "지점", "등급", "레벨"]:
            if col in df.columns:
                df = df.drop(columns=[col])

        created, updated = svc.process_grades_excel(df, request.user)

        try:
            log_action(
                request,
                ACTION.PARTNER_GRADES_UPLOAD,
                meta={
                    "created": created,
                    "updated": updated,
                    "file_name": getattr(file, "name", ""),
                    "branch": redirect_branch,
                },
                success=True,
            )
        except Exception:
            logger.exception("[partner.grades] audit failed: upload_grades_excel")

        messages.success(request, f"업로드 완료: 신규 {created}건, 수정 {updated}건 반영")

    except Exception as e:
        logger.exception("[partner.grades] upload_grades_excel failed")
        messages.error(request, f"엑셀 처리 중 오류 발생: {e}")

    return _redirect()


@login_required
@grade_required("superuser", "head")
def ajax_users_data(request):
    """✅ DataTables server-side API (범위 제한 + SubAdminTemp 검색 범위 제한)"""
    user = request.user

    try:
        draw = int(request.GET.get("draw", "1") or "1")
    except ValueError:
        draw = 1

    try:
        start = max(int(request.GET.get("start", 0)), 0)
    except ValueError:
        start = 0

    try:
        length = int(request.GET.get("length", 10))
        if length <= 0:
            length = 10
    except ValueError:
        length = 10

    search = to_str(request.GET.get("search[value]", ""))
    selected_part = to_str(request.GET.get("part", ""))
    selected_branch = to_str(request.GET.get("branch", ""))
    selected_channel = to_str(request.GET.get("channel", ""))

    try:
        if user.grade == "superuser":
            if not selected_part or not selected_branch:
                return JsonResponse({"draw": draw, "data": [], "recordsTotal": 0, "recordsFiltered": 0}, status=200)

            base_qs = CustomUser.objects.filter(part=selected_part, branch=selected_branch, status="재직")
            if selected_channel:
                base_qs = base_qs.filter(channel=selected_channel)
        else:
            fixed_branch = to_str(user.branch)
            if not fixed_branch:
                return JsonResponse({"draw": draw, "data": [], "recordsTotal": 0, "recordsFiltered": 0}, status=200)

            base_qs = CustomUser.objects.filter(branch=fixed_branch, status="재직")

            if not selected_part:
                selected_part = find_part_by_branch(fixed_branch) or to_str(user.part)

        records_total = base_qs.count()
        qs = base_qs

        if search:
            ids_from_custom = list(
                qs.filter(
                    Q(name__icontains=search)
                    | Q(id__icontains=search)
                    | Q(branch__icontains=search)
                    | Q(part__icontains=search)
                ).values_list("id", flat=True)
            )

            base_ids = list(qs.values_list("id", flat=True))
            ids_from_subadmin = list(
                SubAdminTemp.objects.filter(user_id__in=base_ids).filter(
                    Q(team_a__icontains=search)
                    | Q(team_b__icontains=search)
                    | Q(team_c__icontains=search)
                    | Q(position__icontains=search)
                ).values_list("user_id", flat=True)
            )

            combined_ids = set(ids_from_custom) | set(ids_from_subadmin)
            qs = qs.filter(id__in=combined_ids)

        records_filtered = qs.count()

        qs = qs.order_by("name", "id")
        page_qs = qs.only("id", "name", "branch", "part")[start : start + length]
        page_ids = [u.id for u in page_qs]

        subadmin_map = {
            str(sa.user_id): {
                "name": to_str(sa.name),
                "position": to_str(sa.position) or "-",
                "team_a": to_str(sa.team_a) or "-",
                "team_b": to_str(sa.team_b) or "-",
                "team_c": to_str(sa.team_c) or "-",
                "level": to_str(sa.level) or "-",
                "grade": to_str(sa.grade) or "",
            }
            for sa in SubAdminTemp.objects.filter(user_id__in=page_ids)
        }

        data = []
        for u in page_qs:
            sa = subadmin_map.get(str(u.id), {})
            display_name = to_str(u.name) or sa.get("name") or "-"
            data.append(
                {
                    "part": to_str(u.part) or "-",
                    "branch": to_str(u.branch) or "-",
                    "name": display_name,
                    "user_id": u.id,
                    "position": sa.get("position", "-"),
                    "team_a": sa.get("team_a", "-"),
                    "team_b": sa.get("team_b", "-"),
                    "team_c": sa.get("team_c", "-"),
                    "level": sa.get("level", "-"),
                    "grade": sa.get("grade", "") or to_str(getattr(u, "grade", "")),
                }
            )

        return JsonResponse(
            {"draw": draw, "data": data, "recordsTotal": records_total, "recordsFiltered": records_filtered},
            status=200,
        )

    except Exception as e:
        logger.exception("[partner.grades] ajax_users_data failed")
        return JsonResponse(
            {"draw": draw, "data": [], "recordsTotal": 0, "recordsFiltered": 0, "error": str(e)},
            status=200,
        )


@require_POST
@login_required
@grade_required("superuser", "head")
def ajax_update_level(request):
    user_id = to_str(request.POST.get("user_id"))
    level = to_str(request.POST.get("level"))

    if level not in LEVELS:
        return JsonResponse({"success": False, "error": "Invalid level"}, status=400)

    try:
        sa = SubAdminTemp.objects.get(user_id=user_id)
        sa.level = level
        sa.save(update_fields=["level"])
        return JsonResponse({"success": True})
    except SubAdminTemp.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found"}, status=404)
