# commission/views/api_rate_example_conversion.py
from __future__ import annotations

"""
예시표 환산율/수정률 정규화 데이터 조회 API.

역할:
- rate_example_home.html의 환산율/수정률 모달에서 테이블 조회용 JSON 제공
- 현재는 생명보험/ABL 정규화 결과 조회에 사용
"""

import logging
import json
from json import JSONDecodeError

from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import grade_required
from audit.constants import ACTION
from audit.services import log_action
from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example_conversion_edit import (
    RateExampleConversionEditError,
    bulk_edit_conversion_rows,
)
from commission.views.utils_json import _json_error, _json_ok

logger = logging.getLogger(__name__)


STRATEGY_CHOICES = {
    "",
    "전략상품1",
    "전략상품2",
    "전략상품3",
    "전략상품4",
}


def _format_decimal(value) -> str:
    """
    Decimal 값을 과학적 표기법 없이 문자열로 변환한다.
    예:
    - Decimal("2.7E+2") → "270.0"
    - Decimal("0.3500") → "0.35"
    """
    if value is None:
        return ""
    
    text = format(value, "f")

    if "." in text:
        text = text.rstrip("0").rstrip(".")
    
    # raw 환산율이 정수처럼 보여도 화면에서는 실수 형태로 명시한다.
    if text and "." not in text:
        text = f"{text}.0"
    
    return text


def _format_rate_percent(value) -> str:
    """
    환산율/수정률 화면 표시용 포맷.

    저장 정책:
    - ABL/DB/IM 모두 DB에는 백분율 수치 기준 Decimal로 저장한다.
      예: 100.0%, 126.0% → Decimal("100.0"), Decimal("126.0")
    - 모달 출력 시에는 사용자에게 raw 의미가 명확하도록 '%'를 붙인다.

    계산 정책:
    - 보험료 × 환산율 × 지급률 × 수수료율 계산 시에는
      row.year1 / Decimal("100") 형태로 비례 적용한다.
    """
    text = _format_decimal(value)
    if not text:
        return ""
    return f"{text}%"


def _format_percent_decimal(value) -> str:
    """
    백분율 기준으로 저장된 환산율 값을 화면 표시용 문자열로 변환한다.

    사용 대상:
    - IM normalizer는 raw 표시값이 126%인 경우 DB에 Decimal("126")으로 저장한다.
    - 모달에서는 raw와 동일하게 "126%" 형태로 표시한다.

    주의:
    - 기존 ABL/DB는 기존 _format_decimal() 출력 정책을 유지한다.
    - 계산 시에는 저장값 / 100으로 비례 적용한다.
    """
    if value is None:
        return ""

    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")

    if not text:
        return ""
    return f"{text}%"


def _format_rate_value(row: RateExampleConversionRow, value) -> str:
    """
    보험사별 환산율 표시 정책.

    - IM: raw 백분율 표시와 동일하게 126% 형태
    - 그 외 기존 보험사: 기존 실수/정수 표시 정책 유지
    """
    if row.insurer == "IM":
        return _format_percent_decimal(value)
    return _format_decimal(value)


def _format_dt(value) -> str:
    """마지막 업데이트 일시 표시용 포맷."""
    if not value:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")


@login_required
@grade_required("superuser", forbidden_template=None)
@require_GET
def rate_example_conversion_list(request):
    insurer_type = (request.GET.get("insurer_type") or "").strip()
    insurer = (request.GET.get("insurer") or "").strip()
    category = RateExample.CAT_CONV

    if insurer_type not in (RateExample.TYPE_LIFE, RateExample.TYPE_FIRE):
        return _json_error("손생구분 값이 올바르지 않습니다.", status=400)
    if not insurer:
        return _json_error("보험사를 선택해 주세요.", status=400)

    qs = (
        RateExampleConversionRow.objects
        .select_related("source_file", "source_file__uploaded_by")
        .filter(insurer_type=insurer_type, category=category, insurer=insurer)
        .order_by("coverage_type", "product_name", "plan_type", "pay_period", "id")
    )

    # ── 마지막 업데이트 정보 ─────────────────────────────────────
    # 같은 보험사/구분 데이터는 최신 업로드 파일 기준으로 교체되므로
    # source_file.created_at 최신값을 화면의 "마지막 업데이트"로 사용한다.
    latest_row = (
        qs.order_by("-source_file__created_at", "-source_file_id", "-id")
        .first()
    )
    latest_file = latest_row.source_file if latest_row else None
    latest_uploader = getattr(latest_file, "uploaded_by", None) if latest_file else None

    rows = [
        {
            "id": row.id,
            "coverage_type": row.coverage_type,
            "strategy_flag": row.strategy_flag,
            "product_name": row.product_name,
            "plan_type": row.plan_type,
            "pay_period": row.pay_period,
            "year1": _format_rate_percent(row.year1),
            "year2": _format_rate_percent(row.year2),
            "year3": _format_rate_percent(row.year3),
            "year4": _format_rate_percent(row.year4),
            "source_sheet": row.source_sheet,
            "source_row_no": row.source_row_no,
        }
        for row in qs
    ]

    return _json_ok(
        "조회되었습니다.",
        data={
            "rows": rows,
            "count": len(rows),
            "last_updated_at": _format_dt(getattr(latest_file, "created_at", None)),
            "last_updated_by": getattr(latest_uploader, "name", "") or "",
            "source_file_name": getattr(latest_file, "original_name", "") or "",
        },
    )


@login_required
@grade_required("superuser", forbidden_template=None)
@require_POST
def rate_example_conversion_bulk_edit(request):
    """
    환산율/수정률 정규화 row 일괄 수정 API.

    역할:
    - 환산율 확인 모달의 수정 모드에서 전달한 create/update/delete 요청을 처리한다.
    - 기존 업로드 replace/append 정책은 건드리지 않고, 정규화 master row만 직접 수정한다.

    보안:
    - superuser 전용
    - CSRF 유지
    - row id가 요청 보험사 scope에 속하는지 서비스에서 재검증한다.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, JSONDecodeError):
        return _json_error("요청 JSON 형식이 올바르지 않습니다.", status=400)

    try:
        result = bulk_edit_conversion_rows(payload=payload, actor=request.user)
    except RateExampleConversionEditError as exc:
        return _json_error(str(exc), status=400)
    except Exception:
        logger.exception("[rate_example_conversion_bulk_edit] unexpected error")
        return _json_error("환산율 저장 중 오류가 발생했습니다.", status=500)

    try:
        log_action(
            request,
            ACTION.COMMISSION_RATE_EXAMPLE_CONVERSION_BULK_EDIT,
            meta={
                "insurer_type": result["insurer_type"],
                "insurer": result["insurer"],
                "created_count": result["created_count"],
                "updated_count": result["updated_count"],
                "deleted_count": result["deleted_count"],
            },
            success=True,
        )
    except Exception:
        logger.exception("rate_example conversion bulk_edit audit log failed")

    return _json_ok(
        "저장되었습니다.",
        data=result,
    )


@login_required
@grade_required("superuser", forbidden_template=None)
@require_POST
def rate_example_conversion_strategy_update(request):
    """
    환산율/수정률 정규화 row의 전략유무 값을 저장한다.

    - DB 구조 변경 없음: RateExampleConversionRow.strategy_flag 재사용
    - 허용값 외 입력 차단
    """
    row_id = (request.POST.get("id") or "").strip()
    strategy_flag = (request.POST.get("strategy_flag") or "").strip()

    if not row_id.isdigit():
        return _json_error("대상 행 정보가 올바르지 않습니다.", status=400)

    if strategy_flag not in STRATEGY_CHOICES:
        return _json_error("전략유무 값이 올바르지 않습니다.", status=400)

    row = RateExampleConversionRow.objects.filter(pk=int(row_id)).first()
    if not row:
        return _json_error("대상 데이터를 찾을 수 없습니다.", status=404)

    old_value = row.strategy_flag
    row.strategy_flag = strategy_flag
    row.save(update_fields=["strategy_flag"])

    try:
        log_action(
            request,
            ACTION.COMMISSION_RATE_EXAMPLE_STRATEGY_UPDATE,
            obj=row,
            meta={
                "insurer_type": row.insurer_type,
                "insurer": row.insurer,
                "coverage_type": row.coverage_type,
                "product_name": row.product_name,
                "plan_type": row.plan_type,
                "from": old_value,
                "to": strategy_flag,
            },
            success=True,
        )
    except Exception:
        logger.exception("rate_example_conversion strategy_update audit log failed")

    return _json_ok(
        "저장되었습니다.",
        data={
            "id": row.id,
            "strategy_flag": row.strategy_flag,
        },
    )


# ── 환산율 정규화 데이터 초기화 (보험사 단위) ────────────────────────────────
@login_required
@grade_required("superuser", forbidden_template=None)
@require_POST
def rate_example_conversion_reset(request):
    """
    특정 보험사의 환산율 정규화 데이터(RateExampleConversionRow) 전체 삭제.

    POST params:
        insurer_type: "life" 고정
        insurer: 삭제 대상 보험사명
    """
    from commission.models import RateExampleConversionRow  # noqa: PLC0415
    from audit.constants import ACTION  # noqa: PLC0415
    from audit.services import log_action  # noqa: PLC0415

    insurer_type = request.POST.get("insurer_type", "").strip()
    insurer      = request.POST.get("insurer", "").strip()

    if not insurer_type or not insurer:
        return _json_error("insurer_type 및 insurer 파라미터가 필요합니다.")

    deleted_count, _ = RateExampleConversionRow.objects.filter(
        insurer_type=insurer_type,
        insurer=insurer,
    ).delete()

    try:
        log_action(
            request,
            ACTION.COMMISSION_RATE_EXAMPLE_UPLOAD,   # 가장 근접한 기존 ACTION 재사용
            meta={
                "action_detail": "conversion_reset",
                "insurer_type": insurer_type,
                "insurer": insurer,
                "deleted_count": deleted_count,
            },
            success=True,
        )
    except Exception:
        logger.exception("rate_example conversion_reset audit log failed")

    return _json_ok(
        f"{insurer} 환산율 데이터 {deleted_count}건을 삭제했습니다.",
        data={"deleted_count": deleted_count},
    )