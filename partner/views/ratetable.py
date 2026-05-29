# partner/views/ratetable.py
# ------------------------------------------------------------
# ✅ RateTable (요율현황) API (FINAL REFACTOR)
# - userlist/json
# - excel download
# - excel upload  ✅ (Sheet: 업로드/Sheet1/첫시트 + 사번없으면 C열 + 손해보험/생명보험 매핑)
# - user detail
# - template excel
# ------------------------------------------------------------

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd
from django.core.files.storage import default_storage
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import grade_required
from accounts.models import CustomUser
from audit.constants import ACTION
from audit.services import log_action
from partner.models import RateTable, SubAdminTemp

from .responses import json_err, json_ok
from .utils import (
    can_access_branch,
    excel_response,
    find_table_rate,
    normalize_emp_id,
    safe_tmp_name,
    to_str,
)


# =============================================================================
# Excel Upload Helpers (SSOT)
# =============================================================================

SHEET_PRIORITIES = ("업로드", "Sheet1")  # ✅ user request
EMP_COL_C_INDEX = 2  # ✅ user request: C열(3번째 열)
COL_NONLIFE = "손해보험"  # ✅ user request: 손해보험 → 손보테이블(non_life_table)
COL_LIFE = "생명보험"    # ✅ user request: 생명보험 → 생보테이블(life_table)

EMP_COL_CANDIDATES = ("사번", "사원번호", "ID", "id", "사원ID")


ALLOWED_RATE_TABLE_GRADES = ("superuser", "head", "leader")
logger = logging.getLogger(__name__)


def _pick_sheet_name(xls: pd.ExcelFile) -> str:
    sheets = list(getattr(xls, "sheet_names", []) or [])
    for name in SHEET_PRIORITIES:
        if name in sheets:
            return name
    return sheets[0] if sheets else "Sheet1"


def _detect_header_row(df_raw: pd.DataFrame, max_scan: int = 8) -> int:
    """
    헤더 자동 탐지:
    첫 N행 중에서 손해보험/생명보험/사번 등 키워드가 가장 많이 포함된 행을 헤더로 판단
    """
    targets = {COL_NONLIFE, COL_LIFE, "사번", "사원번호", "성명", "이름"}
    best_i, best_score = 0, -1
    scan = min(max_scan, len(df_raw))
    for i in range(scan):
        row = df_raw.iloc[i].tolist()
        row_str = [to_str(v) for v in row if v is not None]
        score = sum(1 for t in targets if any(t in s for s in row_str))
        if score > best_score:
            best_score = score
            best_i = i
    return best_i


def _resolve_emp_col(df: pd.DataFrame) -> Optional[str]:
    """
    사번 컬럼 결정:
    1) '사번' 등 명시 컬럼 우선
    2) 없으면 무조건 C열(3번째 열)
    """
    for name in EMP_COL_CANDIDATES:
        if name in df.columns:
            return name
    if len(df.columns) >= EMP_COL_C_INDEX + 1:
        return df.columns[EMP_COL_C_INDEX]
    return None


# =============================================================================
# APIs
# =============================================================================

@require_GET
@login_required
@grade_required(*ALLOWED_RATE_TABLE_GRADES, forbidden_template=None)
def ajax_rate_userlist(request):
    """
    JS(/static/js/partner/manage_table.js)에서 기대하는 JSON:
    { data: [{branch, team_a, team_b, team_c, name, id, non_life_table, life_table}, ...] }
    """
    branch = to_str(request.GET.get("branch"))
    if not branch:
        return JsonResponse({"data": []})
    if not can_access_branch(request.user, branch):
        return json_err("다른 지점 데이터에는 접근할 수 없습니다.", status=403, extra={"data": []})

    users = (
        CustomUser.objects
        .filter(branch=branch, is_active=True)
        # 1️⃣ name이 null/빈값 제외
        .exclude(Q(name__isnull=True) | Q(name__exact=""))
        # 2️⃣ name에 '*' 포함 제외
        .exclude(name__contains="*")
        .values("id", "name", "branch")
        .order_by("name")
    )
    user_ids = [u["id"] for u in users]

    team_map = {
        t.user_id: {"team_a": t.team_a, "team_b": t.team_b, "team_c": t.team_c}
        for t in SubAdminTemp.objects.filter(user_id__in=user_ids)
    }
    rate_map = {
        r.user_id: {"non_life_table": r.non_life_table or "", "life_table": r.life_table or ""}
        for r in RateTable.objects.filter(user_id__in=user_ids)
    }

    data = []
    for u in users:
        team_info = team_map.get(u["id"], {})
        rate_info = rate_map.get(u["id"], {})
        data.append(
            {
                "id": u["id"],
                "name": u["name"],
                "branch": u["branch"],
                "team_a": team_info.get("team_a", ""),
                "team_b": team_info.get("team_b", ""),
                "team_c": team_info.get("team_c", ""),
                "non_life_table": rate_info.get("non_life_table", ""),
                "life_table": rate_info.get("life_table", ""),
            }
        )

    return JsonResponse({"data": data})


@require_GET
@login_required
@grade_required(*ALLOWED_RATE_TABLE_GRADES, forbidden_template=None)
def ajax_rate_userlist_excel(request):
    """
    요율현황 엑셀 다운로드
    - 접근제어: superuser 아니면 본인지점만
    """
    branch = to_str(request.GET.get("branch"))
    if not branch:
        return JsonResponse({"error": "지점을 선택해주세요."}, status=400)

    if not can_access_branch(request.user, branch):
        return JsonResponse({"error": "다른 지점 데이터에는 접근할 수 없습니다."}, status=403)

    users = list(
        CustomUser.objects.filter(branch=branch, is_active=True)
        .values("id", "name", "branch")
        .order_by("name")
    )
    user_ids = [u["id"] for u in users]

    team_map = {
        t.user_id: {"team_a": t.team_a, "team_b": t.team_b, "team_c": t.team_c}
        for t in SubAdminTemp.objects.filter(user_id__in=user_ids)
    }
    rate_map = {
        r.user_id: {"non_life_table": r.non_life_table or "", "life_table": r.life_table or ""}
        for r in RateTable.objects.filter(user_id__in=user_ids)
    }

    data = []
    for u in users:
        team_info = team_map.get(u["id"], {})
        rate_info = rate_map.get(u["id"], {})
        data.append(
            {
                "지점": u["branch"],
                "팀A": team_info.get("team_a", ""),
                "팀B": team_info.get("team_b", ""),
                "팀C": team_info.get("team_c", ""),
                "성명": u["name"],
                "사번": u["id"],
                "손보테이블": rate_info.get("non_life_table", ""),
                "생보테이블": rate_info.get("life_table", ""),
            }
        )

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="요율현황")

    filename = f"요율현황_{branch}_{datetime.now():%Y%m%d}.xlsx"
    return excel_response(output.getvalue(), filename)


@require_POST
@login_required
@grade_required(*ALLOWED_RATE_TABLE_GRADES, forbidden_template=None)
@transaction.atomic
def ajax_rate_userlist_upload(request):
    """
    ✅ 업로드 요구사항 반영 (FINAL)
    1) 시트명: '업로드'가 없으면 'Sheet1' 시트도 허용(그것도 없으면 첫 시트)
    2) '사번' 컬럼이 없어도 C열(3번째 열)을 사번으로 인식
    3) '손해보험' → RateTable.non_life_table, '생명보험' → RateTable.life_table 매핑
    + 접근제어: superuser 아니면 본인지점만 업로드 가능 (branch param 기준)
    """
    excel_file = request.FILES.get("excel_file")
    branch = to_str(request.POST.get("branch"))

    if not excel_file:
        return json_err("엑셀 파일이 없습니다.", status=400)
    if not branch:
        return json_err("branch가 없습니다.", status=400)

    # 권한: superuser 아니면 본인지점만
    if not can_access_branch(request.user, branch):
        return json_err("다른 지점 데이터에는 업로드할 수 없습니다.", status=403)

    file_path = None
    try:
        file_path = default_storage.save(f"tmp/{safe_tmp_name(excel_file.name)}", excel_file)
        file_path_full = default_storage.path(file_path)

        # 1) 시트 선택(업로드/Sheet1/첫시트)
        xls = pd.ExcelFile(file_path_full)
        sheet = _pick_sheet_name(xls)

        # 2) 헤더 자동탐지 (raw -> header row -> 실제 df)
        df_raw = pd.read_excel(xls, sheet_name=sheet, header=None, dtype=str)
        header_row = _detect_header_row(df_raw)
        df = pd.read_excel(xls, sheet_name=sheet, header=header_row, dtype=str).fillna("")

        # 컬럼 문자열 정리
        df.columns = [to_str(c) for c in df.columns]

        # 3) 사번 컬럼 결정(명시 없으면 C열)
        emp_col = _resolve_emp_col(df)
        if not emp_col:
            return json_err("사번 컬럼을 찾을 수 없습니다. (명시 컬럼 없으면 C열이 필요)", status=400)

        # 4) 보험 컬럼 존재 확인 (손해보험/생명보험)
        if COL_NONLIFE not in df.columns:
            return json_err(f"'{COL_NONLIFE}' 컬럼이 없습니다.", status=400)
        if COL_LIFE not in df.columns:
            return json_err(f"'{COL_LIFE}' 컬럼이 없습니다.", status=400)

        # 5) row → 업데이트 목록 구성
        updates: list[Tuple[str, str, str]] = []
        for _, row in df.iterrows():
            emp_id = normalize_emp_id(row.get(emp_col))
            if not emp_id:
                continue

            nonlife = to_str(row.get(COL_NONLIFE))
            life = to_str(row.get(COL_LIFE))

            # 둘다 비면 스킵(원치 않는 빈값 덮어쓰기 방지)
            if not nonlife and not life:
                continue

            updates.append((emp_id, nonlife, life))

        if not updates:
            return json_err("업데이트할 데이터가 없습니다.", status=400)

        # 6) CustomUser 매칭 (branch 스코프)
        emp_ids = [u[0] for u in updates]
        qs = CustomUser.objects.filter(branch=branch, is_active=True, id__in=emp_ids)
        users_map = {str(u.id): u for u in qs}

        updated_count = 0
        skipped_count = 0

        for emp_id, nonlife, life in updates:
            target_user = users_map.get(str(emp_id))
            if not target_user:
                skipped_count += 1
                continue

            defaults = {}
            if nonlife:
                defaults["non_life_table"] = nonlife
            if life:
                defaults["life_table"] = life

            RateTable.objects.update_or_create(user=target_user, defaults=defaults)
            updated_count += 1

        try:
            log_action(
                request,
                getattr(ACTION, "PARTNER_RATE_UPLOAD", "partner.rate.upload"),
                object_type="RateTable",
                object_id=branch,
                meta={
                    "branch": branch,
                    "file_name": safe_tmp_name(excel_file.name),
                    "sheet": sheet,
                    "updated_count": updated_count,
                    "skipped_count": skipped_count,
                },
                success=True,
            )
        except Exception:
            logger.exception("[partner.ratetable_upload] audit log failed")

        return json_ok(
            {"message": f"업로드 완료 ({updated_count}건 업데이트 / {skipped_count}건 스킵됨, sheet={sheet})"}
        )

    except Exception:
        logger.exception("[partner.ratetable_upload] failed branch=%s user=%s", branch, getattr(request.user, "id", ""))
        return json_err("업로드 중 오류가 발생했습니다.", status=500)

    finally:
        if file_path:
            try:
                default_storage.delete(file_path)
            except Exception:
                logger.exception("[partner.ratetable_upload] temp file delete failed file_path=%s", file_path)


@require_GET
@login_required
@grade_required(*ALLOWED_RATE_TABLE_GRADES, forbidden_template=None)
def ajax_rate_user_detail(request):
    """
    대상자 요율 상세 + find_table_rate 적용
    """
    user_id = to_str(request.GET.get("user_id"))
    if not user_id:
        return json_err("user_id가 없습니다.", status=400)

    try:
        target = CustomUser.objects.get(id=user_id)
        if not can_access_branch(request.user, to_str(target.branch)):
            return json_err("대상자 조회 권한이 없습니다.", status=403)

        rate_info = RateTable.objects.filter(user=target).first()
        non_life_table = rate_info.non_life_table if rate_info else ""
        life_table = rate_info.life_table if rate_info else ""

        non_life_rate = find_table_rate(target.branch, non_life_table)
        life_rate = find_table_rate(target.branch, life_table)

        return json_ok(
            {
                "data": {
                    "target_name": target.name,
                    "target_id": target.id,
                    "non_life_table": non_life_table,
                    "life_table": life_table,
                    "non_life_rate": non_life_rate,
                    "life_rate": life_rate,
                    "branch": target.branch or "",
                }
            }
        )

    except CustomUser.DoesNotExist:
        return json_err("대상자를 찾을 수 없습니다.", status=404)

    except Exception:
        logger.exception("[partner.ratetable] ajax_rate_user_detail failed")
        return json_err("요율 조회 중 오류가 발생했습니다.", status=500)


@require_GET
@login_required
@grade_required(*ALLOWED_RATE_TABLE_GRADES, forbidden_template=None)
def ajax_rate_userlist_template_excel(request):
    """
    ✅ 업로드 양식 엑셀 (FINAL)
    - '업로드' 시트 제공하되, 시스템은 'Sheet1'도 허용하므로 안내에 반영
    - 컬럼: 손해보험 / 생명보험
    - 사번 컬럼이 없어도 C열을 사번으로 인식하므로 가이드에 반영
    """
    try:
        branch = to_str(request.GET.get("branch"))
        if branch and not can_access_branch(request.user, branch):
            return json_err("다른 지점 양식은 다운로드할 수 없습니다.", status=403)

        # 실제 업로드 권장 양식(명시 사번 포함 버전)
        df = pd.DataFrame(columns=["사번", COL_NONLIFE, COL_LIFE])

        guide = pd.DataFrame(
            [
                ["시트명은 '업로드' 권장이나 'Sheet1'도 업로드 가능합니다.", "", ""],
                ["'사번' 컬럼이 없더라도 C열(3번째 열)을 사번으로 인식합니다.", "", ""],
                [f"보험 컬럼명은 정확히: {COL_NONLIFE} / {COL_LIFE}", "", ""],
                ["사번은 CustomUser.id와 매칭됩니다. (지점 스코프 적용)", "", ""],
            ],
            columns=["안내", " ", "  "],
        )

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="업로드")
            guide.to_excel(writer, index=False, sheet_name="안내")

            ws = writer.book["업로드"]
            ws.column_dimensions["A"].width = 14
            ws.column_dimensions["B"].width = 20
            ws.column_dimensions["C"].width = 20

        filename = f"요율현황_업로드양식_{branch+'_' if branch else ''}{datetime.now():%Y%m%d}.xlsx"
        return excel_response(output.getvalue(), filename)

    except Exception:
        logger.exception("[partner.ratetable] ajax_rate_userlist_template_excel failed")
        return json_err("양식 생성 중 오류가 발생했습니다.", status=500)
