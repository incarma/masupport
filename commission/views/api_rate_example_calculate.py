# django_ma/commission/views/api_rate_example_calculate.py
from __future__ import annotations

"""
수수료 예시표 계산 API.

역할:
- rate_example_home.html의 계산 테이블에서 POST JSON을 수신한다.
- 계산 서비스(rate_example_calculator.py)를 호출한다.
- 사용자 표시용 계산 결과를 JSON으로 반환한다.

보안:
- superuser 전용
- CSRF 유지
- 파일 직접 노출 없음
- 내부 traceback은 logger.exception으로만 기록
"""

import json
import logging
from json import JSONDecodeError

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from audit.constants import ACTION
from audit.services import log_action
from commission.services.rate_example_calculator import (
    RateExampleCalcError,
    calculate_rate_example_commission,
)
from commission.views.utils_json import _json_error, _json_ok

logger = logging.getLogger(__name__)


def _premium_range(value: str | int | None) -> str:
    """
    Audit meta에 보험료 원문을 그대로 남기지 않기 위한 축약값.
    """
    try:
        n = int(str(value or "0").replace(",", ""))
    except ValueError:
        return "invalid"

    if n <= 0:
        return "invalid"
    if n < 100_000:
        return "10만원미만"
    if n < 1_000_000:
        return "10만원대"
    if n < 10_000_000:
        return "100만원대"
    return "1000만원이상"


def _normalize_insurer_type(value: str | None) -> str:
    """
    감사로그용 insurer_type 정규화.
    - 프론트/레거시에서 nonlife가 넘어와도 현재 SSOT인 fire로 기록한다.
    - 허용 외 값은 life로 방어한다.
    """
    raw = str(value or "life").strip()
    if raw == "nonlife":
        return "fire"
    if raw in {"life", "fire"}:
        return raw
    return "life"


def _audit_meta_base(payload: dict, *, data: dict | None = None) -> dict:
    """
    수수료 예시표 조회/계산 감사로그 meta 공통 생성.

    보안/개인정보 원칙:
    - 보험료 원문은 저장하지 않고 구간값만 저장한다.
    - 상품명/구분/납기는 업무상 감사 추적에 필요한 최소 식별정보로 유지한다.
    - 생보/손보 구분은 insurer_type으로 명확히 기록한다.
    """
    insurer_type = _normalize_insurer_type(payload.get("insurer_type"))

    meta = {
        "event": "rate_example_calculate",
        "insurer_type": insurer_type,
        "insurer_type_label": "손해보험" if insurer_type == "fire" else "생명보험",
        "insurer": payload.get("insurer"),
        "product_name": payload.get("product_name"),
        "plan_type": payload.get("plan_type"),
        "pay_period": payload.get("pay_period"),
        "premium_range": _premium_range(payload.get("premium")),
        "commission_rate": payload.get("commission_rate"),
    }

    if data:
        meta.update(
            {
                "coverage_type": data.get("coverage_type"),
                "pay_coverage_type": data.get("pay_coverage_type"),
                "total_amount": data.get("total_amount"),
                "total_ratio": data.get("total_ratio"),
            }
        )

    return meta


def _log_rate_example_calculate(request, payload: dict, *, data: dict | None = None, success: bool = True, reason: str = "") -> None:
    """
    감사로그 실패가 사용자 계산 기능을 막지 않도록 방어한다.
    """
    try:
        log_action(
            request,
            ACTION.COMMISSION_RATE_EXAMPLE_CALCULATE,
            object_type="RateExampleCalculate",
            object_id=_normalize_insurer_type(payload.get("insurer_type")),
            meta=_audit_meta_base(payload, data=data),
            success=success,
            reason=reason,
        )
    except Exception:
        logger.exception("[rate_example_calculate] audit log failed")


@require_POST
@login_required
@grade_required("superuser", forbidden_template=None)
def rate_example_calculate(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, JSONDecodeError):
        return _json_error("요청 JSON 형식이 올바르지 않습니다.", status=400)

    try:
        data = calculate_rate_example_commission(payload)
        _log_rate_example_calculate(request, payload, data=data, success=True)
        return _json_ok(data=data)

    except RateExampleCalcError as exc:
        _log_rate_example_calculate(request, payload, success=False, reason=str(exc))
        return _json_error(str(exc), status=400)

    except Exception as exc:
        logger.exception("[rate_example_calculate] unexpected error")
        _log_rate_example_calculate(request, payload, success=False, reason=exc.__class__.__name__)
        return _json_error("계산 중 오류가 발생했습니다.", status=500)