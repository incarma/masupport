# django_ma/board/services/rate_limit.py
# =========================================================
# Board Rate Limit Service (SSOT)
# ---------------------------------------------------------
# 목적:
# - Board 내부 JSON/API성 엔드포인트 abuse 방어
# - Redis cache 기반 고정 윈도우 rate limit
# - DB migration 없이 적용
# - Redis/cache 장애 시 업무 중단 방지를 위해 fail-open
#
# 사용 예:
#   rl = check_rate_limit(request, scope="industry:preference", rule="30/60")
#   if not rl.allowed:
#       return rate_limited_json(rl)
#
# rule 형식:
#   "요청횟수/초"
#   "30/60" = 60초 동안 30회 허용
# =========================================================

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger("board")


@dataclass(frozen=True)
class RateLimitResult:
    """
    Rate limit 판정 결과.
    """
    allowed: bool
    key: str
    count: int
    limit: int
    window: int
    retry_after: int


# =========================================================
# 1. Rule parsing
# =========================================================
def parse_rate_rule(
    rule: str,
    *,
    default_limit: int = 30,
    default_window: int = 60,
) -> tuple[int, int]:
    """
    rate limit rule 문자열을 (limit, window seconds)로 변환한다.

    정상:
        "30/60" -> (30, 60)

    비정상:
        "", None, "abc", "30" -> 기본값 fallback

    안전 보정:
        limit/window는 최소 1 이상으로 보정한다.
    """
    raw = str(rule or "").strip()

    try:
        left, right = raw.split("/", 1)
        limit = int(left)
        window = int(right)
    except Exception:
        limit = default_limit
        window = default_window

    return max(1, limit), max(1, window)


# =========================================================
# 2. Request identity
# =========================================================
def get_rate_limit_identity(request) -> str:
    """
    요청자를 rate limit key로 변환한다.

    우선순위:
    1) 로그인 사용자: user:<pk>
    2) 비로그인/예외 상황: ip:<client_ip>

    Board 내부 API는 대부분 login_required이나,
    유틸 재사용 가능성을 위해 IP fallback을 유지한다.
    """
    user = getattr(request, "user", None)

    if getattr(user, "is_authenticated", False):
        return f"user:{getattr(user, 'pk', '')}"

    meta = getattr(request, "META", {}) or {}
    forwarded = str(meta.get("HTTP_X_FORWARDED_FOR", "") or "").split(",")[0].strip()
    ip = forwarded or str(meta.get("REMOTE_ADDR", "") or "").strip() or "unknown"
    return f"ip:{ip}"


# =========================================================
# 3. Core limiter
# =========================================================
def check_rate_limit(request, *, scope: str, rule: str) -> RateLimitResult:
    """
    고정 윈도우 기반 rate limit 검사.

    특징:
    - Redis cache 사용
    - key 구조: rl:board:<scope>:<identity>
    - cache.add()로 윈도우 시작
    - cache.incr()로 카운트 증가
    - cache 장애 시 fail-open

    주의:
    - 보안상 엄격 차단보다 내부 서비스 안정성을 우선한다.
    - 외부 공개 API가 아니라 내부 업무 시스템 abuse 방어 목적이다.
    """
    limit, window = parse_rate_rule(rule)

    if not getattr(settings, "BOARD_RATE_LIMIT_ENABLED", True):
        return RateLimitResult(
            allowed=True,
            key="",
            count=0,
            limit=limit,
            window=window,
            retry_after=0,
        )

    safe_scope = str(scope or "default").strip().replace(" ", "_") or "default"
    ident = get_rate_limit_identity(request)
    key = f"rl:board:{safe_scope}:{ident}"

    try:
        added = cache.add(key, 1, timeout=window)
        if added:
            return RateLimitResult(
                allowed=True,
                key=key,
                count=1,
                limit=limit,
                window=window,
                retry_after=0,
            )

        try:
            count = cache.incr(key)
        except Exception:
            count = int(cache.get(key, 0) or 0) + 1
            cache.set(key, count, timeout=window)

        allowed = count <= limit
        return RateLimitResult(
            allowed=allowed,
            key=key,
            count=count,
            limit=limit,
            window=window,
            retry_after=0 if allowed else window,
        )

    except Exception as exc:
        logger.warning(
            "[board.rate_limit] fail-open scope=%s error=%s",
            safe_scope,
            exc,
            exc_info=True,
        )
        return RateLimitResult(
            allowed=True,
            key=key,
            count=0,
            limit=limit,
            window=window,
            retry_after=0,
        )


# =========================================================
# 4. JSON response helper
# =========================================================
def rate_limited_json(result: RateLimitResult) -> JsonResponse:
    """
    rate limit 차단 JSON 응답.

    프론트 공통 처리:
    - ok=False
    - message 제공
    - HTTP 429
    - Retry-After header 포함
    """
    retry_after = result.retry_after or result.window

    response = JsonResponse(
        {
            "ok": False,
            "message": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
            "data": {
                "retry_after": retry_after,
                "limit": result.limit,
                "window": result.window,
            },
        },
        status=429,
    )
    response["Retry-After"] = str(retry_after)
    return response


# =========================================================
# 5. Convenience helper
# =========================================================
def is_rate_limited(request, *, scope: str, rule: str) -> JsonResponse | None:
    """
    뷰에서 간단히 쓰기 위한 helper.

    사용 예:
        limited = is_rate_limited(request, scope="board:search_user", rule="30/60")
        if limited:
            return limited
    """
    result = check_rate_limit(request, scope=scope, rule=rule)
    if result.allowed:
        return None
    return rate_limited_json(result)