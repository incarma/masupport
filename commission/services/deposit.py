# django_ma/commission/services/deposit.py
from __future__ import annotations

"""
Deposit 조회/합계 서비스.

역할:
- commission/views/api_deposit_impl.py에서 사용하던 ORM 조회/합계 로직을 분리한다.
- View는 request 파싱, 권한 검증, JSON 응답만 담당하게 한다.

주의:
- 응답 key/계산식/필터 조건 변경 없음.
- 권한 검증은 기존처럼 View 계층에서 수행한다.
- payload 직렬화는 commission.services.deposit_serializers 가 담당한다.
"""

from typing import Optional, Tuple

from django.db.models import QuerySet, Sum
from django.db.models.functions import Coalesce

from commission.models import DepositOther, DepositSummary, DepositSurety, DepositUploadLog


SURETY_PRODUCT_KEYWORD = "GA개인"
OTHER_PRODUCT_TYPE_KEYWORD = "수수료"
STATUS_KEEP = "유지"
STATUS_KEEP_IN = "유지인"


__all__ = [
    "get_deposit_summary",
    "get_deposit_surety_queryset",
    "get_deposit_other_queryset",
    "calc_filtered_totals",
    "calc_keep_totals_all",
    "get_upload_dates",
]


def _amount_total(qs: QuerySet) -> int:
    """amount 합계 aggregate 공통 처리."""
    total = qs.aggregate(total=Coalesce(Sum("amount"), 0))["total"]
    return int(total or 0)


def get_deposit_summary(user_pk: str) -> Optional[DepositSummary]:
    """
    DepositSummary 단건 조회.

    user_pk는 CustomUser.pk인 사번 문자열이다.
    """
    return DepositSummary.objects.filter(user_id=user_pk).first()


def get_deposit_surety_queryset(user_pk: str) -> QuerySet[DepositSurety]:
    """
    보증보험 상세 조회 queryset.

    View/serializer에서 list 변환 전까지 queryset을 유지한다.
    """
    return DepositSurety.objects.filter(user_id=user_pk).order_by("-id")


def get_deposit_other_queryset(user_pk: str) -> QuerySet[DepositOther]:
    """
    기타채권 상세 조회 queryset.

    View/serializer에서 list 변환 전까지 queryset을 유지한다.
    """
    return DepositOther.objects.filter(user_id=user_pk).order_by("-id")


def calc_filtered_totals(user_pk: str) -> Tuple[int, int]:
    """
    요구사항 기준 합계.

    - 보증합계: DepositSurety / 상품명 'GA개인' 포함 + 상태 '유지'
    - 기타합계: DepositOther / 보증내용 '수수료' 포함 + 상태 ('유지', '유지인')
    """
    surety_total = DepositSurety.objects.filter(
        user_id=user_pk,
        product_name__icontains=SURETY_PRODUCT_KEYWORD,
        status=STATUS_KEEP,
    )

    other_total = DepositOther.objects.filter(
        user_id=user_pk,
        product_type__icontains=OTHER_PRODUCT_TYPE_KEYWORD,
        status__in=[STATUS_KEEP_IN, STATUS_KEEP],
    )

    return _amount_total(surety_total), _amount_total(other_total)


def calc_keep_totals_all(user_pk: str) -> Tuple[int, int]:
    """상태='유지' 전체 합계."""
    surety_keep_all = DepositSurety.objects.filter(
        user_id=user_pk,
        status=STATUS_KEEP,
    )

    other_keep_all = DepositOther.objects.filter(
        user_id=user_pk,
        status=STATUS_KEEP,
    )

    return _amount_total(surety_keep_all), _amount_total(other_keep_all)


def get_upload_dates(
    parts: list[str], upload_types: list[str]
) -> dict[str, dict[str, str]]:
    """
    부서×업로드타입 업로드 최신일 매핑.

    deposit_home 페이지의 업로드 현황 표에 사용한다.
    반환 형식: {부서: {업로드타입: "YYYY-MM-DD" | "-"}}
    누락 셀은 "-"로 채운다.
    """
    logs = (
        DepositUploadLog.objects.filter(
            part__in=parts,
            upload_type__in=upload_types,
        )
        .only("part", "upload_type", "uploaded_at")
    )

    result: dict[str, dict[str, str]] = {p: {} for p in parts}
    for row in logs:
        ts = getattr(row, "uploaded_at", None)
        result[row.part][row.upload_type] = ts.strftime("%Y-%m-%d") if ts else "-"

    for p in parts:
        for ut in upload_types:
            result[p].setdefault(ut, "-")

    return result