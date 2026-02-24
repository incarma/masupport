# django_ma/commission/views/api_deposit_impl.py
from __future__ import annotations

from io import BytesIO
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from urllib.parse import quote

from django.conf import settings
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from accounts.models import CustomUser
from commission.models import DepositOther, DepositSummary, DepositSurety


# =============================================================================
# Basic Helpers
# =============================================================================

def _to_str(v: Any) -> str:
    return ("" if v is None else str(v)).strip()


def _fmt_date(d) -> str:
    try:
        return d.strftime("%Y-%m-%d") if d else "-"
    except Exception:
        return "-"


def _to_iso(d) -> str:
    try:
        return d.isoformat() if d else ""
    except Exception:
        return ""


def _decimal_str(v: Any, default: str = "0.00") -> str:
    if v is None:
        return default
    if isinstance(v, Decimal):
        return str(v)
    try:
        return str(Decimal(str(v)))
    except Exception:
        return default


def _int0(v: Any) -> int:
    if v is None:
        return 0
    try:
        # Decimal/str/float/int 모두 흡수
        return int(Decimal(str(v)))
    except Exception:
        try:
            return int(v)
        except Exception:
            return 0

def _dstr(v: Any, default: str = "0.00") -> str:
    # Decimal 계열은 문자열로 내려서 프론트에서 percent 포맷을 안정적으로 적용
    return _decimal_str(v, default=default)



def _json_err(message: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "message": message}, status=status)


# =============================================================================
# User Resolver
# =============================================================================

def _get_user_id_from_request(request) -> str:
    return _to_str(
        request.GET.get("user")
        or request.GET.get("id")
        or request.GET.get("emp_id")
        or request.GET.get("employee_id")
        or request.GET.get("regist")
        or request.GET.get("username")
        or ""
    )


def _find_user_by_any_id(user_id: str) -> Optional[CustomUser]:
    user_id = _to_str(user_id)
    if not user_id:
        return None

    base = CustomUser.objects.only(
        "id", "name", "part", "branch",
        "enter", "quit", "regist", "grade"
    )

    try:
        u = base.filter(Q(pk=user_id) | Q(id=user_id)).first()
        if u:
            return u
    except Exception:
        pass

    if hasattr(CustomUser, "emp_id"):
        u = base.filter(emp_id=user_id).first()
        if u:
            return u

    u = base.filter(regist=user_id).first()
    if u:
        return u

    if hasattr(CustomUser, "username"):
        u = base.filter(username=user_id).first()
        if u:
            return u

    return None


# =============================================================================
# Payload Builders
# =============================================================================

def _user_to_payload(u: CustomUser) -> Dict[str, Any]:
    return {
        "id": u.id,
        "name": u.name or "",
        "part": u.part or "",
        "branch": u.branch or "",
        "join_date_display": _fmt_date(u.enter),
        "retire_date_display": _fmt_date(u.quit),
        "enter": _to_iso(u.enter),
        "quit": _to_iso(u.quit),
    }


def _summary_to_payload(s: DepositSummary) -> Dict[str, Any]:
    # NOTE:
    # - 템플릿(data-bind)이 요구하는 키들을 최대한 그대로 내려준다.
    # - 모델에 필드가 없는 경우도 있을 수 있으므로 getattr로 방어한다.
    return {
        # --- 주요지표
        "final_payment": _int0(getattr(s, "final_payment", None)),
        "sales_total": _int0(getattr(s, "sales_total", None)),
        "refund_expected": _int0(getattr(s, "refund_expected", None)),
        "pay_expected": _int0(getattr(s, "pay_expected", None)),
        "maint_total": _dstr(getattr(s, "maint_total", None)),  # percent용 문자열(예: "86.90")

        "debt_total": _int0(getattr(s, "debt_total", None)),
        "surety_total": _int0(getattr(s, "surety_total", None)),
        "other_total": _int0(getattr(s, "other_total", None)),
        "required_debt": _int0(getattr(s, "required_debt", None)),
        "final_excess_amount": _int0(getattr(s, "final_excess_amount", None)),

        # --- 분급여부(템플릿: summary.div_1m~3m)
        "div_1m": getattr(s, "div_1m", "") or "",
        "div_2m": getattr(s, "div_2m", "") or "",
        "div_3m": getattr(s, "div_3m", "") or "",

        # --- 인정계속분(템플릿: inst_current/inst_prev)
        "inst_current": _int0(getattr(s, "inst_current", None)),
        "inst_prev": _int0(getattr(s, "inst_prev", None)),

        # --- 환수/지급(손생) (refund_ns/ls, pay_ns/ls)
        "refund_ns": _int0(getattr(s, "refund_ns", None)),
        "refund_ls": _int0(getattr(s, "refund_ls", None)),
        "pay_ns": _int0(getattr(s, "pay_ns", None)),
        "pay_ls": _int0(getattr(s, "pay_ls", None)),

        # --- 보증(O/X) 환수·지급 (surety_o_*, surety_x_*)
        "surety_o_refund_ns": _int0(getattr(s, "surety_o_refund_ns", None)),
        "surety_o_refund_ls": _int0(getattr(s, "surety_o_refund_ls", None)),
        "surety_o_refund_total": _int0(getattr(s, "surety_o_refund_total", None)),
        "surety_o_pay_ns": _int0(getattr(s, "surety_o_pay_ns", None)),
        "surety_o_pay_ls": _int0(getattr(s, "surety_o_pay_ls", None)),
        "surety_o_pay_total": _int0(getattr(s, "surety_o_pay_total", None)),

        "surety_x_refund_ns": _int0(getattr(s, "surety_x_refund_ns", None)),
        "surety_x_refund_ls": _int0(getattr(s, "surety_x_refund_ls", None)),
        "surety_x_refund_total": _int0(getattr(s, "surety_x_refund_total", None)),
        "surety_x_pay_ns": _int0(getattr(s, "surety_x_pay_ns", None)),
        "surety_x_pay_ls": _int0(getattr(s, "surety_x_pay_ls", None)),
        "surety_x_pay_total": _int0(getattr(s, "surety_x_pay_total", None)),

        # --- 3~12개월 총수수료(템플릿: comm_3m/6m/9m/12m)
        "comm_3m": _int0(getattr(s, "comm_3m", None)),
        "comm_6m": _int0(getattr(s, "comm_6m", None)),
        "comm_9m": _int0(getattr(s, "comm_9m", None)),
        "comm_12m": _int0(getattr(s, "comm_12m", None)),

        # --- 유지율/수금율 라운드/합계/응당(템플릿: ns_13_round 등)
        "ns_13_round": _dstr(getattr(s, "ns_13_round", None), default="0.00"),
        "ns_18_round": _dstr(getattr(s, "ns_18_round", None), default="0.00"),
        "ls_13_round": _dstr(getattr(s, "ls_13_round", None), default="0.00"),
        "ls_18_round": _dstr(getattr(s, "ls_18_round", None), default="0.00"),

        "ns_18_total": _dstr(getattr(s, "ns_18_total", None), default="0.00"),
        "ns_25_total": _dstr(getattr(s, "ns_25_total", None), default="0.00"),
        "ls_18_total": _dstr(getattr(s, "ls_18_total", None), default="0.00"),
        "ls_25_total": _dstr(getattr(s, "ls_25_total", None), default="0.00"),

        "ns_2_6_due": _dstr(getattr(s, "ns_2_6_due", None), default="0.00"),
        "ns_2_13_due": _dstr(getattr(s, "ns_2_13_due", None), default="0.00"),
        "ls_2_6_due": _dstr(getattr(s, "ls_2_6_due", None), default="0.00"),
        "ls_2_13_due": _dstr(getattr(s, "ls_2_13_due", None), default="0.00"),
    }


def _surety_to_payload(x: DepositSurety) -> Dict[str, Any]:
    return {
        "product_name": x.product_name or "",
        "policy_no": x.policy_no or "",
        "amount": x.amount or 0,
        "status": x.status or "",
        "start_date": _fmt_date(x.start_date),
        "end_date": _fmt_date(x.end_date),
    }


def _other_to_payload(x: DepositOther) -> Dict[str, Any]:
    return {
        "product_name": x.product_name or "",
        "product_type": x.product_type or "",
        "amount": x.amount or 0,
        "status": x.status or "",
        "bond_no": x.bond_no or "",
        "start_date": _fmt_date(x.start_date),
        "memo": x.memo or "",
    }


# =============================================================================
# 유지 상태 금액 합계 계산
# =============================================================================

def _calc_kept_amounts(user_pk: str) -> tuple[int, int]:

    surety_keep = (
        DepositSurety.objects
        .filter(user_id=user_pk, status="유지")
        .aggregate(total=Coalesce(Sum("amount"), 0))["total"]
    )

    other_keep = (
        DepositOther.objects
        .filter(user_id=user_pk, status="유지")
        .aggregate(total=Coalesce(Sum("amount"), 0))["total"]
    )

    return int(surety_keep or 0), int(other_keep or 0)


# =============================================================================
# Permission
# =============================================================================

def _can_view_target(request, target: CustomUser) -> bool:
    u = getattr(request, "user", None)
    if not u or not u.is_authenticated:
        return False

    grade = getattr(u, "grade", "")
    if grade in ("superuser", "main_admin", "head"):
        return True

    return str(u.pk) == str(target.pk)


def _require_view_permission(request, target):
    if _can_view_target(request, target):
        return None
    return _json_err("권한이 없습니다.", status=403)


# =============================================================================
# APIs
# =============================================================================

@require_GET
def api_user_detail(request):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        return _json_err("user 파라미터가 필요합니다.")

    u = _find_user_by_any_id(user_id)
    if not u:
        return _json_err("대상자를 찾지 못했습니다.", status=404)

    perm = _require_view_permission(request, u)
    if perm:
        return perm

    payload = _user_to_payload(u)
    return JsonResponse({"ok": True, "data": payload, "user": payload})


@require_GET
def api_deposit_summary(request):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        return _json_err("user 파라미터가 필요합니다.")

    u = _find_user_by_any_id(user_id)
    if not u:
        return JsonResponse({"ok": True, "rows": []})

    perm = _require_view_permission(request, u)
    if perm:
        return perm
    
    from django.db import connection
    print("[deposit_summary] DB:", connection.settings_dict.get("NAME"))
    print("[deposit_summary] user_id:", u.pk)
    print("[deposit_summary] summary_count:", DepositSummary.objects.count())

    s = DepositSummary.objects.filter(user_id=u.pk).first()
    if not s:
        return JsonResponse({"ok": True, "rows": []})
    
    from django.db import connection
    print("[deposit_summary] DB:", connection.settings_dict.get("NAME"))
    print("[deposit_summary] user_id:", u.pk)
    print("[deposit_summary] summary_count:", DepositSummary.objects.count())

    payload = _summary_to_payload(s)

    # ✅ 유지 합계 반영
    surety_keep, other_keep = _calc_kept_amounts(u.pk)
    # NOTE:
    # - surety_total / other_total 는 "원본 합계"로 유지(모델 값)
    # - 유지합계는 별도 키로 제공(프론트에서 표기 선택 가능)
    payload["surety_keep_total"] = int(surety_keep or 0)
    payload["other_keep_total"] = int(other_keep or 0)

    # 유지합계를 포함한 "유지 기준 채권합계"도 필요하면 같이 제공
    # (기존 debt_total 정의가 무엇인지 애매할 수 있어서 별도 제공)
    try:
        payload["debt_keep_total"] = int(payload.get("surety_keep_total", 0)) + int(payload.get("other_keep_total", 0))
    except Exception:
        payload["debt_keep_total"] = 0

    resp = JsonResponse({"ok": True, "rows": [payload], "_debug_view": "api_deposit_impl.api_deposit_summary"})
    resp["X-Deposit-View"] = "api_deposit_impl"
    return resp


@require_GET
def api_support_pdf(request):

    user_id = _get_user_id_from_request(request)
    if not user_id:
        return _json_err("user 파라미터가 필요합니다.")

    target = _find_user_by_any_id(user_id)
    if not target:
        return _json_err("대상자를 찾지 못했습니다.", status=404)

    perm = _require_view_permission(request, target)
    if perm:
        return perm

    summary = DepositSummary.objects.filter(user_id=target.pk).first()

    surety_keep, other_keep = _calc_kept_amounts(target.pk)

    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("지원신청서", styles["Title"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"성명: {target.name}", styles["Normal"]))
    story.append(Paragraph(f"보증합계(유지): {surety_keep:,}", styles["Normal"]))
    story.append(Paragraph(f"기타합계(유지): {other_keep:,}", styles["Normal"]))

    if summary:
        story.append(Paragraph(f"채권합계: {int(summary.debt_total or 0):,}", styles["Normal"]))

    doc.build(story)

    pdf_bytes = buf.getvalue()
    buf.close()

    filename = f"지원신청서_{target.id}.pdf"

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return resp


# =============================================================================
# APIs (Missing: surety / other list)
# =============================================================================

@require_GET
def api_deposit_surety_list(request):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        return _json_err("user 파라미터가 필요합니다.")

    u = _find_user_by_any_id(user_id)
    if not u:
        return JsonResponse({"ok": True, "rows": []})

    perm = _require_view_permission(request, u)
    if perm:
        return perm

    qs = (
        DepositSurety.objects
        .filter(user_id=u.pk)
        .order_by("-id")
    )
    rows = [_surety_to_payload(x) for x in qs]
    return JsonResponse({"ok": True, "rows": rows})


@require_GET
def api_deposit_other_list(request):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        return _json_err("user 파라미터가 필요합니다.")

    u = _find_user_by_any_id(user_id)
    if not u:
        return JsonResponse({"ok": True, "rows": []})

    perm = _require_view_permission(request, u)
    if perm:
        return perm

    qs = (
        DepositOther.objects
        .filter(user_id=u.pk)
        .order_by("-id")
    )
    rows = [_other_to_payload(x) for x in qs]
    return JsonResponse({"ok": True, "rows": rows})
