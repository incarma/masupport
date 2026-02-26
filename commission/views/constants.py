# django_ma/commission/views/constants.py
from __future__ import annotations

from decimal import Decimal

# 업로드 화면에서 보여줄 카테고리(정렬용)
UPLOAD_CATEGORIES = [
    "최종지급액",
    "환수지급예상",
    "보증증액",
    "보증보험",
    "기타채권",
    "통산생보",
    "통산손보",
    "응당생보",
    "응당손보",
]


def _build_supported_upload_types() -> frozenset[str]:
    """
    ✅ SSOT: commission.upload_handlers.registry 기반으로 허용 업로드 타입 자동 생성.

    import 시점에 registry import가 실패하면(드물게 초기 로딩/순환),
    최소한 서버가 죽지 않도록 fallback을 둔다.
    """
    try:
        from commission.upload_handlers.registry import supported_upload_types

        return frozenset(supported_upload_types())
    except Exception:
        # fallback (마지막 안전망)
        return frozenset(
            {
                "최종지급액",
                "환수지급예상",
                "보증증액",
                "응당생보",
                "응당손보",
                "보증보험",
                "기타채권",
                "통산손보",
                "통산생보",
            }
        )


# api_upload(채권)에서 허용하는 타입 (SSOT 자동 생성)
SUPPORTED_UPLOAD_TYPES = _build_supported_upload_types()

# 통산(소수) 기본 자리수
DEC2 = Decimal("0.00")

# 지점효율 초과 판단 기준(원 단위)
EXCESS_THRESHOLD = 10_000_000

__all__ = [
    "UPLOAD_CATEGORIES",
    "SUPPORTED_UPLOAD_TYPES",
    "DEC2",
    "EXCESS_THRESHOLD",
]