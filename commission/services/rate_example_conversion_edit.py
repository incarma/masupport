# commission/services/rate_example_conversion_edit.py
from __future__ import annotations

"""
RateExample 환산율/수정률 직접수정 서비스.

역할:
- 환산율 확인 모달의 수정 모드에서 전달한 row 생성/수정/삭제를 처리한다.
- View는 HTTP/JSON 처리만 담당하고, ORM 변경·검증·트랜잭션은 본 서비스가 SSOT로 담당한다.

보안/운영 원칙:
- superuser 권한 검사는 view decorator에서 수행한다.
- row id가 요청 보험사 scope에 속하는지 서버에서 재검증한다.
- 신규 row는 해당 보험사의 최신 RateExample source_file에 연결한다.
- DB 저장값은 기존 정책과 동일하게 백분율 Decimal 수치로 저장한다.
  예: 화면 입력 "100%" 또는 "100.0" → Decimal("100.0000")
"""

from decimal import Decimal, InvalidOperation

from django.db import transaction

from commission.models import RateExample, RateExampleConversionRow


class RateExampleConversionEditError(ValueError):
    """사용자에게 노출 가능한 환산율 직접수정 오류."""


EDITABLE_TEXT_FIELDS = {
    "coverage_type",
    "strategy_flag",
    "product_name",
    "plan_type",
    "pay_period",
}

EDITABLE_RATE_FIELDS = {
    "year1",
    "year2",
    "year3",
    "year4",
}

STRATEGY_CHOICES = {
    "",
    "전략상품1",
    "전략상품2",
    "전략상품3",
    "전략상품4",
}


def _clean(value: object) -> str:
    """입력값을 앞뒤 공백 제거 문자열로 정규화한다."""
    return str(value or "").strip()


def _parse_int(value: object, *, field_name: str) -> int:
    """row id 등 정수 입력값 검증."""
    text = _clean(value)
    if not text.isdigit():
        raise RateExampleConversionEditError(f"{field_name} 값이 올바르지 않습니다.")
    return int(text)


def _to_decimal_or_none(value: object, *, field_name: str) -> Decimal | None:
    """
    환산율 입력값을 Decimal로 변환한다.

    허용:
    - ""
    - None
    - "100"
    - "100.0"
    - "100%"
    - "1,000.25%"
    """
    text = _clean(value).replace(",", "").replace("%", "")
    if not text:
        return None

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise RateExampleConversionEditError(f"{field_name} 값이 올바르지 않습니다.")


def _validate_scope(insurer_type: str, insurer: str) -> None:
    """수정 가능한 환산율 scope 검증."""
    if insurer_type not in {RateExample.TYPE_LIFE, RateExample.TYPE_NONLIFE}:
        raise RateExampleConversionEditError("손생구분 값이 올바르지 않습니다.")

    if not insurer:
        raise RateExampleConversionEditError("보험사를 선택해 주세요.")

    # IBK는 지급률(pay) 전용 특수 보험사이므로 환산율 직접수정 대상에서 제외한다.
    if insurer == "IBK":
        raise RateExampleConversionEditError("IBK는 환산율 수정 대상이 아닙니다.")


def _latest_source_file(insurer_type: str, insurer: str) -> RateExample:
    """
    신규 row에 연결할 최신 source_file을 찾는다.

    모델상 RateExampleConversionRow.source_file은 필수 FK이므로,
    직접 추가 row도 해당 보험사의 최신 업로드 파일에 귀속시킨다.
    """
    source_file = (
        RateExample.objects
        .filter(
            insurer_type=insurer_type,
            category=RateExample.CAT_CONV,
            insurer=insurer,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if not source_file:
        raise RateExampleConversionEditError(
            "신규 행을 추가하려면 먼저 해당 보험사의 환산율 파일을 1회 이상 업로드해야 합니다."
        )
    return source_file


def _row_payload_to_fields(row_data: dict) -> dict:
    """
    프론트 row payload를 모델 필드 dict로 변환한다.
    """
    fields = {
        "coverage_type": _clean(row_data.get("coverage_type")),
        "strategy_flag": _clean(row_data.get("strategy_flag")),
        "product_name": _clean(row_data.get("product_name")),
        "plan_type": _clean(row_data.get("plan_type")),
        "pay_period": _clean(row_data.get("pay_period")),
        "year1": _to_decimal_or_none(row_data.get("year1"), field_name="1차년"),
        "year2": _to_decimal_or_none(row_data.get("year2"), field_name="2차년"),
        "year3": _to_decimal_or_none(row_data.get("year3"), field_name="3차년"),
        "year4": _to_decimal_or_none(row_data.get("year4"), field_name="4차년"),
    }

    if fields["strategy_flag"] not in STRATEGY_CHOICES:
        raise RateExampleConversionEditError("전략유무 값이 올바르지 않습니다.")

    if not fields["product_name"]:
        raise RateExampleConversionEditError("상품명은 필수입니다.")

    return fields


@transaction.atomic
def bulk_edit_conversion_rows(*, payload: dict, actor) -> dict:
    """
    환산율/수정률 정규화 row 일괄 수정.

    Payload:
    {
        "insurer_type": "life",
        "insurer": "DB",
        "rows": [
            {"id": 1, "product_name": "...", "year1": "100.0", ...},
            {"id": null, "product_name": "신규상품", "year1": "100.0", ...}
        ],
        "deleted_ids": [10, 11]
    }

    반환:
    {
        "insurer_type": "life",
        "insurer": "DB",
        "created_count": 1,
        "updated_count": 2,
        "deleted_count": 1
    }
    """
    insurer_type = _clean(payload.get("insurer_type"))
    insurer = _clean(payload.get("insurer"))
    rows = payload.get("rows") or []
    deleted_ids = payload.get("deleted_ids") or []

    _validate_scope(insurer_type, insurer)

    if not isinstance(rows, list):
        raise RateExampleConversionEditError("rows 값이 올바르지 않습니다.")
    if not isinstance(deleted_ids, list):
        raise RateExampleConversionEditError("deleted_ids 값이 올바르지 않습니다.")

    scope_filter = {
        "insurer_type": insurer_type,
        "category": RateExample.CAT_CONV,
        "insurer": insurer,
    }

    # ── 삭제 처리 ─────────────────────────────────────────────────────────
    # 전달된 id가 현재 보험사 scope에 속하는 경우에만 삭제한다.
    parsed_deleted_ids = [
        _parse_int(v, field_name="삭제 대상 id")
        for v in deleted_ids
        if _clean(v)
    ]
    deleted_count = 0
    if parsed_deleted_ids:
        deleted_count, _ = (
            RateExampleConversionRow.objects
            .filter(**scope_filter, id__in=parsed_deleted_ids)
            .delete()
        )

    # ── 수정/추가 처리 ─────────────────────────────────────────────────────
    source_file = None
    created_count = 0
    updated_count = 0

    for row_data in rows:
        if not isinstance(row_data, dict):
            raise RateExampleConversionEditError("row 데이터 형식이 올바르지 않습니다.")

        fields = _row_payload_to_fields(row_data)
        row_id = _clean(row_data.get("id"))

        if row_id:
            pk = _parse_int(row_id, field_name="수정 대상 id")
            row = (
                RateExampleConversionRow.objects
                .select_for_update()
                .filter(**scope_filter, pk=pk)
                .first()
            )
            if not row:
                raise RateExampleConversionEditError("수정 대상 데이터를 찾을 수 없습니다.")

            for field, value in fields.items():
                setattr(row, field, value)

            row.save(update_fields=[*fields.keys()])
            updated_count += 1
            continue

        # 신규 row는 최신 source_file에 귀속한다.
        if source_file is None:
            source_file = _latest_source_file(insurer_type, insurer)

        RateExampleConversionRow.objects.create(
            source_file=source_file,
            source_sheet="manual_edit",
            source_row_no=0,
            insurer_type=insurer_type,
            category=RateExample.CAT_CONV,
            insurer=insurer,
            **fields,
        )
        created_count += 1

    return {
        "insurer_type": insurer_type,
        "insurer": insurer,
        "created_count": created_count,
        "updated_count": updated_count,
        "deleted_count": deleted_count,
    }