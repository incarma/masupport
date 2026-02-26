# django_ma/commission/views/api_deposit_impl.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts.models import CustomUser
from commission.models import DepositOther, DepositSummary, DepositSurety

# =============================================================================
# 0) Common helpers
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
    """Decimal/float/int/str → 화면 표시 안전을 위해 문자열로 통일."""
    if v is None:
        return default
    if isinstance(v, Decimal):
        return str(v)
    try:
        return str(Decimal(str(v)))
    except Exception:
        return default


def _int0(v: Any) -> int:
    """None/Decimal/float/int/str → int 안전 변환."""
    if v is None:
        return 0
    try:
        return int(Decimal(str(v)))
    except Exception:
        try:
            return int(v)
        except Exception:
            return 0


def _json_err(message: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "message": message}, status=status)


# =============================================================================
# 1) Request → target user resolver
# =============================================================================


def _get_user_id_from_request(request) -> str:
    """레거시/호환을 위해 다양한 키를 허용."""
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
    """
    - 기본은 CustomUser.pk(id=사번)
    - 레거시 필드(emp_id/regist/username)도 방어적으로 탐색
    - 조회 필드는 only()로 최소화(성능/보안)
    """
    user_id = _to_str(user_id)
    if not user_id:
        return None

    base = CustomUser.objects.only("id", "name", "part", "branch", "enter", "quit", "regist", "grade")

    # 1) pk/id
    u = base.filter(Q(pk=user_id) | Q(id=user_id)).first()
    if u:
        return u

    # 2) optional legacy ids
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
# 2) Permission
# =============================================================================


def _can_view_target(request, target: CustomUser) -> bool:
    """Deposit(채권현황)은 개인정보/정산정보 성격 → 열람 권한 제한."""
    u = getattr(request, "user", None)
    if not u or not u.is_authenticated:
        return False

    grade = getattr(u, "grade", "")
    if grade in ("superuser", "main_admin", "head"):
        return True

    # 본인만
    return str(u.pk) == str(target.pk)


def _require_view_permission(request, target: CustomUser) -> Optional[JsonResponse]:
    if _can_view_target(request, target):
        return None
    return _json_err("권한이 없습니다.", status=403)


def _resolve_target_or_err(request) -> Tuple[Optional[CustomUser], Optional[JsonResponse], str]:
    """
    공통 흐름:
      1) user 파라미터 파싱
      2) 대상자 조회
      3) 권한 체크(403)
    """
    user_id = _get_user_id_from_request(request)
    if not user_id:
        return None, _json_err("user 파라미터가 필요합니다."), ""

    target = _find_user_by_any_id(user_id)
    if not target:
        return None, _json_err("대상자를 찾지 못했습니다.", status=404), user_id

    perm = _require_view_permission(request, target)
    if perm:
        return None, perm, user_id

    return target, None, user_id


# =============================================================================
# 3) Payload builders
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
    """
    템플릿(data-bind)이 요구하는 키들을 그대로 내려준다.
    모델 필드가 없을 수 있어 getattr 방어.
    """
    g = lambda k, default=None: getattr(s, k, default)

    return {
        # --- 주요지표
        "final_payment": _int0(g("final_payment")),
        "sales_total": _int0(g("sales_total")),
        "refund_expected": _int0(g("refund_expected")),
        "pay_expected": _int0(g("pay_expected")),
        "maint_total": _decimal_str(g("maint_total"), default="0.00"),

        "debt_total": _int0(g("debt_total")),
        "surety_total": _int0(g("surety_total")),
        "other_total": _int0(g("other_total")),
        "required_debt": _int0(g("required_debt")),
        "final_excess_amount": _int0(g("final_excess_amount")),

        # --- 분급여부
        "div_1m": g("div_1m", "") or "",
        "div_2m": g("div_2m", "") or "",
        "div_3m": g("div_3m", "") or "",

        # --- 인정계속분
        "inst_current": _int0(g("inst_current")),
        "inst_prev": _int0(g("inst_prev")),

        # --- 환수/지급(손생)
        "refund_ns": _int0(g("refund_ns")),
        "refund_ls": _int0(g("refund_ls")),
        "pay_ns": _int0(g("pay_ns")),
        "pay_ls": _int0(g("pay_ls")),

        # --- 보증(O/X)
        "surety_o_refund_ns": _int0(g("surety_o_refund_ns")),
        "surety_o_refund_ls": _int0(g("surety_o_refund_ls")),
        "surety_o_refund_total": _int0(g("surety_o_refund_total")),
        "surety_o_pay_ns": _int0(g("surety_o_pay_ns")),
        "surety_o_pay_ls": _int0(g("surety_o_pay_ls")),
        "surety_o_pay_total": _int0(g("surety_o_pay_total")),

        "surety_x_refund_ns": _int0(g("surety_x_refund_ns")),
        "surety_x_refund_ls": _int0(g("surety_x_refund_ls")),
        "surety_x_refund_total": _int0(g("surety_x_refund_total")),
        "surety_x_pay_ns": _int0(g("surety_x_pay_ns")),
        "surety_x_pay_ls": _int0(g("surety_x_pay_ls")),
        "surety_x_pay_total": _int0(g("surety_x_pay_total")),

        # --- 3~12개월 총수수료
        "comm_3m": _int0(g("comm_3m")),
        "comm_6m": _int0(g("comm_6m")),
        "comm_9m": _int0(g("comm_9m")),
        "comm_12m": _int0(g("comm_12m")),

        # --- 유지율/수금율(문자열)
        "ns_13_round": _decimal_str(g("ns_13_round"), default="0.00"),
        "ns_18_round": _decimal_str(g("ns_18_round"), default="0.00"),
        "ls_13_round": _decimal_str(g("ls_13_round"), default="0.00"),
        "ls_18_round": _decimal_str(g("ls_18_round"), default="0.00"),

        "ns_18_total": _decimal_str(g("ns_18_total"), default="0.00"),
        "ns_25_total": _decimal_str(g("ns_25_total"), default="0.00"),
        "ls_18_total": _decimal_str(g("ls_18_total"), default="0.00"),
        "ls_25_total": _decimal_str(g("ls_25_total"), default="0.00"),

        "ns_2_6_due": _decimal_str(g("ns_2_6_due"), default="0.00"),
        "ns_2_13_due": _decimal_str(g("ns_2_13_due"), default="0.00"),
        "ls_2_6_due": _decimal_str(g("ls_2_6_due"), default="0.00"),
        "ls_2_13_due": _decimal_str(g("ls_2_13_due"), default="0.00"),
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
# 4) Business rules: filtered totals
# =============================================================================


def _calc_filtered_totals(user_pk: str) -> Tuple[int, int]:
    """
    요구사항 기준 합계:
    - 보증합계: DepositSurety / 상품명 'GA개인' 포함 + 상태 '유지' 합계
    - 기타합계: DepositOther  / 보증내용 '수수료' 포함 + 상태 ('유지','유지인') 합계
    """
    surety_total = (
        DepositSurety.objects.filter(user_id=user_pk, product_name__icontains="GA개인", status="유지")
        .aggregate(total=Coalesce(Sum("amount"), 0))["total"]
    )
    other_total = (
        DepositOther.objects.filter(user_id=user_pk, product_type__icontains="수수료", status__in=["유지인", "유지"])
        .aggregate(total=Coalesce(Sum("amount"), 0))["total"]
    )
    return int(surety_total or 0), int(other_total or 0)


def _calc_keep_totals_all(user_pk: str) -> Tuple[int, int]:
    """(호환/표기용) 상태='유지' 전체 합계."""
    surety_keep_all = (
        DepositSurety.objects.filter(user_id=user_pk, status="유지")
        .aggregate(total=Coalesce(Sum("amount"), 0))["total"]
    )
    other_keep_all = (
        DepositOther.objects.filter(user_id=user_pk, status="유지")
        .aggregate(total=Coalesce(Sum("amount"), 0))["total"]
    )
    return int(surety_keep_all or 0), int(other_keep_all or 0)


# =============================================================================
# 5) APIs
# =============================================================================


@require_GET
def api_user_detail(request):
    target, err, _ = _resolve_target_or_err(request)
    if err:
        return err

    payload = _user_to_payload(target)
    # legacy: data + user 둘 다 내려줌(기존 유지)
    return JsonResponse({"ok": True, "data": payload, "user": payload})


@require_GET
def api_deposit_summary(request):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        return _json_err("user 파라미터가 필요합니다.")

    target = _find_user_by_any_id(user_id)
    if not target:
        # 기존 동작 유지: 대상자 없으면 ok+rows:[]
        return JsonResponse({"ok": True, "rows": []})

    perm = _require_view_permission(request, target)
    if perm:
        return perm

    s = DepositSummary.objects.filter(user_id=target.pk).first()
    if not s:
        return JsonResponse({"ok": True, "rows": []})

    payload = _summary_to_payload(s)

    # 요구사항 기준 합계로 교체 (템플릿/JS 수정 최소화를 위해 여기서 덮어씀)
    surety_filtered, other_filtered = _calc_filtered_totals(target.pk)

    # 원본 보존(검증/표기용)
    payload["surety_total_all"] = int(payload.get("surety_total", 0) or 0)
    payload["other_total_all"] = int(payload.get("other_total", 0) or 0)

    payload["surety_total"] = int(surety_filtered or 0)
    payload["other_total"] = int(other_filtered or 0)

    # 유지 전체 합계도 함께 제공(필요 시 화면 표기/디버그용)
    surety_keep_all, other_keep_all = _calc_keep_totals_all(target.pk)
    payload["surety_keep_total"] = int(surety_keep_all or 0)
    payload["other_keep_total"] = int(other_keep_all or 0)
    payload["debt_keep_total"] = int(payload["surety_keep_total"]) + int(payload["other_keep_total"])

    return JsonResponse({"ok": True, "rows": [payload]})


@require_GET
def api_deposit_surety_list(request):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        return _json_err("user 파라미터가 필요합니다.")

    target = _find_user_by_any_id(user_id)
    if not target:
        return JsonResponse({"ok": True, "rows": []})

    perm = _require_view_permission(request, target)
    if perm:
        return perm

    qs = DepositSurety.objects.filter(user_id=target.pk).order_by("-id")
    return JsonResponse({"ok": True, "rows": [_surety_to_payload(x) for x in qs]})


@require_GET
def api_deposit_other_list(request):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        return _json_err("user 파라미터가 필요합니다.")

    target = _find_user_by_any_id(user_id)
    if not target:
        return JsonResponse({"ok": True, "rows": []})

    perm = _require_view_permission(request, target)
    if perm:
        return perm

    qs = DepositOther.objects.filter(user_id=target.pk).order_by("-id")
    return JsonResponse({"ok": True, "rows": [_other_to_payload(x) for x in qs]})