# commission/services/approval.py
from __future__ import annotations

"""
Approval / Efficiency 도메인 서비스 레이어.

역할:
- pages.py, downloads.py, approval.py 뷰에서 직접 호출하던 ORM을 분리한다.
- View는 HTTP/JSON 처리·권한 데코레이터만 담당하고 ORM은 이 모듈이 SSOT다.

주의:
- 권한 검증은 기존처럼 View 계층(@grade_required)에서 수행한다.
- 트랜잭션 경계는 호출부 뷰(approval.py) transaction.atomic() 안에서 유지한다.
"""

from typing import Any, Optional

from django.db.models import QuerySet

from accounts.models import CustomUser
from commission.models import (
    ApprovalExcelUploadLog,
    ApprovalPending,
    EfficiencyPayExcess,
)

__all__ = [
    "list_parts_excluding_centers",
    "get_approval_pending_qs",
    "get_efficiency_excess_qs",
    "delete_pending_scope",
    "upsert_upload_log",
    "get_approval_pending_for_download",
    "get_efficiency_excess_all",
    "filter_by_ym_or_latest",
]


# =============================================================================
# 공통 헬퍼
# =============================================================================


def list_parts_excluding_centers() -> list[str]:
    """
    CustomUser 기준 부서 목록 (센터 제외, 중복 없음, 오름차순).

    deposit_home, approval_home 페이지의 부서 드롭다운에 사용한다.
    """
    qs = (
        CustomUser.objects.exclude(part__isnull=True)
        .exclude(part__exact="")
        .exclude(part__icontains="센터")
        .values_list("part", flat=True)
        .distinct()
        .order_by("part")
    )
    return list(qs)


def filter_by_ym_or_latest(
    qs: QuerySet, ym: str
) -> tuple[str, Optional[QuerySet]]:
    """
    다운로드 공통 월도 필터.
    - ym이 있으면 해당 ym 필터
    - ym이 없으면 queryset에서 최신 ym fallback
    - queryset이 비어 있으면 (str, None) 반환
    """
    if ym:
        return ym, qs.filter(ym=ym)

    latest = qs.order_by("-ym").values_list("ym", flat=True).first()
    if not latest:
        return "", None

    return latest, qs.filter(ym=latest)


# =============================================================================
# Approval 페이지 전용
# =============================================================================


def get_approval_pending_qs(
    ym: str, part: str = ""
) -> QuerySet[ApprovalPending]:
    """
    수수료 미결현황 QuerySet.

    - approval_flag='N', user.regist 필터 적용 (기존 approval_home 조건 유지)
    - part 인자가 있으면 추가 필터
    - 정렬: user__part, branch, name, id
    """
    qs = ApprovalPending.objects.select_related("user").filter(
        ym=ym,
        user__isnull=False,
        approval_flag="N",
        user__regist__in=["손생등록", "손보등록", "생보등록"],
    )
    if part:
        qs = qs.filter(user__part=part)
    return qs.order_by("user__part", "user__branch", "user__name", "user__id")


def get_efficiency_excess_qs(
    ym: str, part: str = "", threshold: int = 0
) -> QuerySet[EfficiencyPayExcess]:
    """
    지점효율 지급 초과현황 QuerySet.

    - pay_amount_sum > threshold 필터 적용
    - part 인자가 있으면 추가 필터
    - 정렬: user__part, branch, name, id
    """
    qs = EfficiencyPayExcess.objects.select_related("user").filter(
        ym=ym,
        user__isnull=False,
        pay_amount_sum__gt=threshold,
    )
    if part:
        qs = qs.filter(user__part=part)
    return qs.order_by("user__part", "user__branch", "user__name", "user__id")


# =============================================================================
# Approval 업로드 흐름 (approval.py _common_upload 에서 분리)
# =============================================================================


def delete_pending_scope(ym: str, part: str, kind: str) -> None:
    """
    업로드 전 기존 데이터(ym + part scope) 삭제.

    - kind='approval'  → ApprovalPending 삭제
    - kind='efficiency' → EfficiencyPayExcess 삭제
    - 호출부(approval.py)의 transaction.atomic() 안에서 수행한다.
    """
    if kind == "approval":
        del_qs: Any = ApprovalPending.objects.filter(ym=ym)
        if part:
            del_qs = del_qs.filter(user__part=part)
        del_qs.delete()

    elif kind == "efficiency":
        del_qs = EfficiencyPayExcess.objects.filter(ym=ym)
        if part:
            del_qs = del_qs.filter(user__part=part)
        del_qs.delete()

    else:
        raise ValueError("구분(kind)을 선택해주세요. (efficiency/approval)")


def upsert_upload_log(
    *,
    ym: str,
    part: str,
    kind: str,
    uploaded_by: Any,
    row_count: int,
    file_name: str,
) -> None:
    """
    ApprovalExcelUploadLog upsert (ym + part + kind unique key).

    호출부(approval.py)의 transaction.atomic() 안에서 수행한다.
    """
    ApprovalExcelUploadLog.objects.update_or_create(
        ym=ym,
        part=part,
        kind=kind,
        defaults={
            "uploaded_by": uploaded_by,
            "row_count": row_count,
            "file_name": (file_name or "")[:255],
        },
    )


# =============================================================================
# Downloads 전용
# =============================================================================


def get_approval_pending_for_download(
    ym: str, min_actual_pay: int
) -> QuerySet[ApprovalPending]:
    """
    수수료 미결현황 다운로드용 QuerySet (ym 필터 없이 전체 반환, 호출부가 ym 필터 적용).

    - approval_flag='N', actual_pay >= min_actual_pay
    - select_related("user") 포함
    """
    return (
        ApprovalPending.objects.filter(
            approval_flag="N",
            actual_pay__gte=min_actual_pay,
        )
        .select_related("user")
    )


def get_efficiency_excess_all() -> QuerySet[EfficiencyPayExcess]:
    """지점효율 지급 초과현황 다운로드용 전체 QuerySet (ym 필터 없음)."""
    return EfficiencyPayExcess.objects.all().select_related("user")
