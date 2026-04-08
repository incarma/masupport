# board/views/collateral.py
"""
담보평가 뷰 (board 앱)
- GET  /board/collateral/           : 계산기 페이지 + 이력
- POST /board/collateral/calc/      : AJAX 계산 + 저장
- POST /board/collateral/<id>/delete/: AJAX 삭제 (superuser / head)
"""
import json
import logging

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.shortcuts import render

from audit.services import log_action
from board.constants import AUDIT_ACTION_COLLATERAL_EVAL, COLLATERAL_RATE_MAP
from board.services.collateral import (
    delete_collateral_eval,
    get_eval_history,
    save_collateral_eval,
)
from django.http import JsonResponse

logger = logging.getLogger("board")


# ── 로컬 JSON 응답 헬퍼 ────────────────────────────────────────────
# commission/views/utils_json.py 와 동일 포맷 유지
# board → commission 앱 간 직접 import는 의존성 위반이므로 로컬 정의
def _json_ok(message=None, **extra):
    payload = {"ok": True}
    if message:
        payload["message"] = message
    payload.update(extra)
    return JsonResponse(payload)


def _json_error(message, status=400, **extra):
    payload = {"ok": False, "message": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)


# ── 페이지 뷰 ─────────────────────────────────────────────────────

@login_required
@require_GET
def collateral_page(request):
    """담보평가 계산기 페이지 + 이력"""
    history  = get_eval_history(request.user)
    can_delete = getattr(request.user, "grade", "") in ("superuser", "head")
    return render(request, "board/collateral.html", {
        "history":    history,
        "rate_map":   COLLATERAL_RATE_MAP,
        "can_delete": can_delete,
    })


# ── AJAX: 계산 + 저장 ─────────────────────────────────────────────

@login_required
@require_POST
def collateral_calc(request):
    """
    AJAX: 담보평가 계산 + 이력 저장
    요청 JSON: { property_type, kb_price, prior_debt, address, memo,
                 target_user_id (optional) }
    """
    try:
        body = json.loads(request.body)
    except Exception:
        return _json_error("요청 형식이 올바르지 않습니다.")

    property_type   = str(body.get("property_type", "")).strip()
    address         = str(body.get("address", "")).strip()
    memo            = str(body.get("memo", "")).strip()
    target_user_id  = body.get("target_user_id") or None

    try:
        kb_price   = int(str(body.get("kb_price",   0)).replace(",", ""))
        prior_debt = int(str(body.get("prior_debt", 0)).replace(",", ""))
        lease_deposit = int(str(body.get("lease_deposit", 0)).replace(",", ""))
    except (ValueError, TypeError):
        return _json_error("금액 형식이 올바르지 않습니다.")

    if kb_price <= 0:
        return _json_error("KB시세를 올바르게 입력하세요.")

    # 대상자 조회 (선택 항목)
    target_user = None
    if target_user_id:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            target_user = User.objects.get(pk=str(target_user_id))
        except User.DoesNotExist:
            return _json_error("대상자를 찾을 수 없습니다.")

    obj, result = save_collateral_eval(
        requester=request.user,
        property_type=property_type,
        kb_price=kb_price,
        prior_debt=prior_debt,
        address=address,
        memo=memo,
        source="manual",
        target_user=target_user,
        lease_deposit=lease_deposit,
    )

    # 감사 로그
    log_action(
        request,
        action=AUDIT_ACTION_COLLATERAL_EVAL,
        object_type="CollateralEval",
        object_id=str(obj.pk) if obj else "N/A",
        meta={
            "property_type":  property_type,
            "address":        address,
            "kb_price":       kb_price,
            "prior_debt":     prior_debt,
            "lease_deposit":  lease_deposit,
            "max_collateral": result.get("max_collateral"),
            "target_user_id": str(target_user_id) if target_user_id else None,
        },
        success=obj is not None,
    )

    if not result["calculable"]:
        return _json_error(result["message"])

    return _json_ok(
        message=result["message"],
        data={
            "eval_id":        obj.pk,
            "apply_rate":     str(result["apply_rate"]),
            "base_amount":    result["base_amount"],
            "max_collateral": result["max_collateral"],
            "target_name":    target_user.name if target_user else "",
            "target_branch":  target_user.branch if target_user else "",
        },
    )


# ── AJAX: 삭제 ────────────────────────────────────────────────────

@login_required
@require_POST
def collateral_delete(request, eval_id: int):
    """
    AJAX: 담보평가 이력 삭제
    - superuser: 전체 삭제 가능
    - head     : 본인 branch 데이터만
    - 그 외     : 403
    """
    grade = getattr(request.user, "grade", "")
    if grade not in ("superuser", "head"):
        return _json_error("삭제 권한이 없습니다.", status=403)

    success, message = delete_collateral_eval(request.user, eval_id)

    log_action(
        request,
        action=f"{AUDIT_ACTION_COLLATERAL_EVAL}_delete",
        object_type="CollateralEval",
        object_id=str(eval_id),
        success=success,
    )

    if not success:
        return _json_error(message, status=403)
    return _json_ok(message=message)