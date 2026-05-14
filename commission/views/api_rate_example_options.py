# django_ma/commission/views/api_rate_example_options.py
from __future__ import annotations

"""
RateExample 계산 입력용 옵션 조회 API.

역할:
- 수수료 예시표 메인 테이블에서 보험사/상품명/구분/납기 연동 옵션 제공
- 생명보험(life) / 손해보험(fire) 탭 상태를 insurer_type으로 받아 동일 API에서 분기
- 정규화 master(RateExampleConversionRow)를 직접 노출하지 않고
  필요한 distinct option만 JSON으로 반환한다.

보안:
- superuser 전용
- GET 전용
- JSON 응답만 반환
"""

import logging

from django.views.decorators.http import require_GET

from accounts.decorators import grade_required
from commission.services.rate_example_options import (
    RateExampleOptionQuery,
    get_rate_example_options,
)
from commission.views.utils_json import _json_ok, _json_error

logger = logging.getLogger(__name__)


def _normalize_insurer_type(value: str) -> str:
    """
    보험 구분 QueryString 정규화.

    - life/fire만 허용한다.
    - 미입력/오입력은 기존 생명보험 페이지 동작 보장을 위해 life로 fallback한다.
    """
    value = (value or "life").strip()
    if value == "nonlife":
        return "fire"
    return value if value in {"life", "fire"} else "life"


@require_GET
@grade_required("superuser", forbidden_template=None)
def rate_example_options(request):
    """
    옵션 조회 API.

    QueryString:
    - kind=insurers|products|plan_types|pay_periods
    - insurer_type=life|fire
    - insurer=보험사
    - product_name=상품명
    - plan_type=구분

    Response:
    {
      "ok": true,
      "data": {
        "items": [...]
      }
    }
    """
    try:
        insurer_type = _normalize_insurer_type(request.GET.get("insurer_type"))

        query = RateExampleOptionQuery(
            kind=(request.GET.get("kind") or "").strip(),
            insurer_type=insurer_type,
            insurer=(request.GET.get("insurer") or "").strip(),
            product_name=(request.GET.get("product_name") or "").strip(),
            plan_type=(request.GET.get("plan_type") or "").strip(),
        )
        items = get_rate_example_options(query)
        return _json_ok(
            "조회되었습니다.",
            data={"items": items},
        )
    except Exception:
        logger.exception("[rate_example_options] failed")
        return _json_error("옵션 조회 중 오류가 발생했습니다.", status=500)