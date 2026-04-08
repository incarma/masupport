# board/services/collateral.py
"""
담보평가 서비스 레이어 (SSOT)
- 뷰에서 직접 ORM 호출 금지 → 반드시 이 모듈 경유
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction

from board.constants import (
    COLLATERAL_RATE_MAP,
    COLLATERAL_UNCALCULABLE_TYPES,
)

logger = logging.getLogger("board")


# ──────────────────────────────────────────────────────────
# 1. 순수 계산 함수 (DB 미접촉)
# ──────────────────────────────────────────────────────────

def calculate_collateral(
    property_type: str,
    kb_price: int,
    prior_debt: int,
    lease_deposit: int = 0,
) -> dict:
    """
    담보 설정 가능 금액 계산 (DB 미접촉)

    반환:
        {
            "calculable":     bool,
            "apply_rate":     Decimal | None,
            "base_amount":    int | None,
            "max_collateral": int | None,
            "message":        str,
        }
    """
    if property_type in COLLATERAL_UNCALCULABLE_TYPES:
        return {
            "calculable": False,
            "apply_rate": None,
            "base_amount": None,
            "max_collateral": None,
            "message": "해당 물건 유형은 담보 설정이 불가합니다.",
        }

    rate = COLLATERAL_RATE_MAP.get(property_type)
    if rate is None:
        return {
            "calculable": False,
            "apply_rate": None,
            "base_amount": None,
            "max_collateral": None,
            "message": "알 수 없는 물건 유형입니다.",
        }

    apply_rate   = Decimal(str(rate))
    base_amount  = int(kb_price * rate / 100)
    max_col      = max(0, base_amount - prior_debt - lease_deposit)

    return {
        "calculable":     True,
        "apply_rate":     apply_rate,
        "base_amount":    base_amount,
        "max_collateral": max_col,
        "message":        "계산 완료",
    }


# ──────────────────────────────────────────────────────────
# 2. 계산 + DB 저장
# ──────────────────────────────────────────────────────────

def save_collateral_eval(
    requester,
    property_type: str,
    kb_price: int,
    prior_debt: int,
    address: str = "",
    memo: str = "",
    source: str = "manual",
    target_user=None,
    lease_deposit: int = 0,
) -> tuple:
    """
    계산 수행 후 CollateralEval 저장

    반환: (CollateralEval | None, result_dict)
    - 계산 불가 유형이면 obj=None, result["calculable"]=False
    """
    from board.models import CollateralEval

    result = calculate_collateral(property_type, kb_price, prior_debt, lease_deposit)

    if not result["calculable"]:
        return None, result

    with transaction.atomic():
        obj = CollateralEval.objects.create(
            requester=requester,
            target_user=target_user,
            property_type=property_type,
            address=address,
            kb_price=kb_price,
            prior_debt=prior_debt,
            lease_deposit=lease_deposit,
            apply_rate=result["apply_rate"],
            max_collateral=result["max_collateral"],
            source=source,
            memo=memo,
        )

    return obj, result


# ──────────────────────────────────────────────────────────
# 3. 이력 조회 (권한 스코프 적용)
# ──────────────────────────────────────────────────────────

def get_eval_history(requester, limit: int = 20) -> list:
    """
    조회자 권한 스코프에 따른 이력 반환

    - superuser  : 전체 데이터
    - head/leader: 본인 소속 branch 데이터만
    - 그 외       : 본인 데이터만

    select_related로 requester/target_user 소속 정보 포함
    """
    from board.models import CollateralEval

    qs = CollateralEval.objects.select_related(
        "requester", "target_user"
    ).order_by("-created_at")

    grade = getattr(requester, "grade", "")

    if grade == "superuser":
        pass  # 전체 조회
    elif grade in ("head", "leader"):
        branch = getattr(requester, "branch", None)
        if branch:
            qs = qs.filter(requester__branch=branch)
        else:
            qs = qs.filter(requester=requester)
    else:
        qs = qs.filter(requester=requester)

    return list(qs[:limit])


# ──────────────────────────────────────────────────────────
# 4. 삭제 (권한: superuser 또는 head)
# ──────────────────────────────────────────────────────────

def delete_collateral_eval(requester, eval_id: int) -> tuple[bool, str]:
    """
    CollateralEval 삭제

    - superuser: 모든 레코드 삭제 가능
    - head     : 본인 소속 branch 레코드만 삭제 가능
    - 그 외     : 권한 없음

    반환: (success: bool, message: str)
    """
    from board.models import CollateralEval

    grade  = getattr(requester, "grade", "")
    branch = getattr(requester, "branch", None)

    if grade not in ("superuser", "head"):
        return False, "삭제 권한이 없습니다."

    try:
        if grade == "superuser":
            obj = CollateralEval.objects.get(pk=eval_id)
        else:
            # head: 본인 branch 레코드만
            obj = CollateralEval.objects.get(
                pk=eval_id, requester__branch=branch
            )
    except CollateralEval.DoesNotExist:
        return False, "존재하지 않거나 권한이 없는 데이터입니다."

    obj.delete()
    return True, "삭제되었습니다."