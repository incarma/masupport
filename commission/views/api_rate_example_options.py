# django_ma/commission/views/api_rate_example_options.py
from __future__ import annotations

"""
RateExample 계산 입력용 옵션 조회 API.

역할:
- 수수료 예시표 메인 테이블에서 보험사/상품명/구분/납기 연동 옵션 제공
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


@require_GET
@grade_required("superuser", forbidden_template=None)
def rate_example_options(request):
    """
    옵션 조회 API.

    QueryString:
    - kind=insurers|products|plan_types|pay_periods
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
        query = RateExampleOptionQuery(
            kind=(request.GET.get("kind") or "").strip(),
            insurer=(request.GET.get("insurer") or "").strip(),
            product_name=(request.GET.get("product_name") or "").strip(),
            plan_type=(request.GET.get("plan_type") or "").strip(),
        )
        items = get_rate_example_options(query)
        return _json_ok({"items": items})
    except Exception:
        logger.exception("[rate_example_options] failed")
        return _json_error("옵션 조회 중 오류가 발생했습니다.", status=500)