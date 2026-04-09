# board/services/collateral.py
"""
담보평가 서비스 레이어 (SSOT)

규칙:
  - 뷰에서 직접 ORM 호출 금지 → 반드시 이 모듈 경유
  - 계산 규칙 변경 시 board/constants.py 만 수정
  - calculate_collateral() 은 DB 미접촉 순수 함수
  - owner_rel 검사는 property_type 검사보다 나중에 수행
    (불가 사유를 더 구체적으로 안내하기 위해)
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction

from board.constants import (
    COLLATERAL_OWNER_REL_BLOCKED,
    COLLATERAL_RATE_MAP,
    COLLATERAL_UNCALCULABLE_TYPES,
)

logger = logging.getLogger("board")


# ──────────────────────────────────────────────────────────────────────
# 내부 헬퍼: 계산 불가 응답 생성 (반복 제거용)
# ──────────────────────────────────────────────────────────────────────

def _not_calculable(message: str) -> dict:
    return {
        "calculable":     False,
        "apply_rate":     None,
        "base_amount":    None,
        "max_collateral": None,
        "message":        message,
    }


# ──────────────────────────────────────────────────────────────────────
# 1. 순수 계산 함수 (DB 미접촉)
# ──────────────────────────────────────────────────────────────────────

def calculate_collateral(
    property_type: str,
    kb_price: int,
    prior_debt: int,
    lease_deposit: int = 0,
    owner_rel: str = "self",
) -> dict:
    """
    담보 설정 가능 금액 계산 (DB 미접촉 순수 함수).

    검사 우선순위:
        1) property_type 이 "etc" 등 명시적 계산불가 유형인지
        2) property_type 이 RATE_MAP 에 없는 알 수 없는 유형인지
        3) owner_rel 이 근저당 설정 불가 관계(제3자 등)인지
        4) 모두 통과 → 금액 계산

    파라미터:
        property_type : CollateralEval.PROPERTY_TYPE_CHOICES 의 코드값
        kb_price      : KB부동산 시세 (원, 양의 정수)
        prior_debt    : 기설정 채권최고액 합계 (원, 0 이상)
        lease_deposit : 임차보증금 (원, 0 이상)
        owner_rel     : CollateralEval.OWNER_REL_CHOICES 의 코드값

    반환:
        {
            "calculable":     bool,
            "apply_rate":     Decimal | None,   # e.g. Decimal("70")
            "base_amount":    int | None,        # kb_price × rate / 100
            "max_collateral": int | None,        # max(0, base - prior_debt - lease_deposit)
            "message":        str,
        }
    """
    # ── 검사 1: 명시적 계산불가 물건 유형 ─────────────────────────
    if property_type in COLLATERAL_UNCALCULABLE_TYPES:
        return _not_calculable(
            "해당 물건 유형은 담보 설정이 불가합니다."
        )

    # ── 검사 2: 알 수 없는 물건 유형 ──────────────────────────────
    rate = COLLATERAL_RATE_MAP.get(property_type)
    if rate is None:
        return _not_calculable(
            f"알 수 없는 물건 유형입니다. (입력값: {property_type!r})"
        )

    # ── 검사 3: 근저당 설정 불가 소유자 관계 ──────────────────────
    if owner_rel in COLLATERAL_OWNER_REL_BLOCKED:
        return _not_calculable(
            "기타 제3자 소유 부동산은 근저당 설정이 불가합니다."
        )

    # ── 계산 ───────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────────
# 2. 계산 + DB 저장
# ──────────────────────────────────────────────────────────────────────

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
    owner_rel: str = "self",
    owner_name: str = "",
    owner_phone: str = "",
) -> tuple:
    """
    담보평가 계산 수행 후 CollateralEval 인스턴스 저장.

    반환: (CollateralEval | None, result_dict)
        - 계산 불가인 경우: (None, result)  — result["calculable"] == False
        - 저장 성공:        (obj,  result)  — result["calculable"] == True
        - 저장 예외:        (None, result)  — result["message"] 에 에러 내용

    호출 예시:
        obj, result = save_collateral_eval(
            requester=request.user,
            property_type="apt",
            kb_price=500_000_000,
            prior_debt=100_000_000,
            owner_rel="self",
        )
        if not result["calculable"]:
            return _json_error(result["message"])
    """
    # 순환 import 방지 — 서비스 레이어에서만 모델 임포트
    from board.models import CollateralEval

    # ① 계산 (소유자 관계 포함)
    result = calculate_collateral(
        property_type=property_type,
        kb_price=kb_price,
        prior_debt=prior_debt,
        lease_deposit=lease_deposit,
        owner_rel=owner_rel,
    )

    if not result["calculable"]:
        return None, result

    # ② DB 저장
    try:
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
                owner_rel=owner_rel,
                owner_name=owner_name,
                owner_phone=owner_phone,
            )
    except Exception as exc:
        logger.error(
            "CollateralEval 저장 오류: %s | property_type=%r kb_price=%s",
            exc, property_type, kb_price,
            exc_info=True,
        )
        return None, {
            **result,
            "calculable": False,
            "message":    "저장 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        }

    return obj, result


# ──────────────────────────────────────────────────────────────────────
# 3. 이력 조회 (권한 스코프 적용)
# ──────────────────────────────────────────────────────────────────────

def get_eval_history(requester, limit: int = 20) -> list:
    """
    조회자의 grade 에 따른 권한 스코프 이력 반환.

    스코프 정책:
        superuser         → 전체 데이터
        head / leader     → 본인 소속 branch 의 데이터
                            (branch 미설정이면 본인 데이터만)
        그 외 (basic 등)  → 본인이 등록한 데이터만

    select_related 로 requester / target_user N+1 방지.
    """
    from board.models import CollateralEval

    qs = (
        CollateralEval.objects
        .select_related("requester", "target_user")
        .order_by("-created_at")
    )

    grade  = getattr(requester, "grade",  "")
    branch = getattr(requester, "branch", None)

    if grade == "superuser":
        pass  # 전체 조회 — 필터 없음

    elif grade in ("head", "leader"):
        if branch:
            qs = qs.filter(requester__branch=branch)
        else:
            # branch 미설정 head/leader 예외 처리: 본인 데이터만
            qs = qs.filter(requester=requester)

    else:
        qs = qs.filter(requester=requester)

    return list(qs[:limit])


# ──────────────────────────────────────────────────────────────────────
# 4. 삭제 (권한: superuser / head)
# ──────────────────────────────────────────────────────────────────────

def delete_collateral_eval(requester, eval_id: int) -> tuple[bool, str]:
    """
    CollateralEval 레코드 삭제.

    권한 정책:
        superuser → 모든 레코드
        head      → 본인 소속 branch 레코드만
        그 외      → 불가 (False 반환, 뷰에서 403 처리)

    반환: (success: bool, message: str)
    """
    from board.models import CollateralEval

    grade  = getattr(requester, "grade",  "")
    branch = getattr(requester, "branch", None)

    if grade not in ("superuser", "head"):
        return False, "삭제 권한이 없습니다."

    try:
        if grade == "superuser":
            obj = CollateralEval.objects.get(pk=eval_id)
        else:
            # head: 본인 branch 레코드만
            obj = CollateralEval.objects.get(
                pk=eval_id,
                requester__branch=branch,
            )
    except CollateralEval.DoesNotExist:
        return False, "존재하지 않거나 삭제 권한이 없는 데이터입니다."

    obj.delete()
    return True, "삭제되었습니다."