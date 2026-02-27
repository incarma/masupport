# django_ma/audit/middleware.py
from __future__ import annotations

import time
import uuid

from django.utils.deprecation import MiddlewareMixin

from .models import RequestLog
from .utils import get_client_ip, mask_querystring


class RequestLogMiddleware(MiddlewareMixin):
    """
    모든 요청/응답을 RequestLog로 저장.
    - body는 저장하지 않음
    - querystring은 마스킹 후 저장
    """

    def process_request(self, request):
        request._audit_start = time.perf_counter()
        # trace id (요청 상관관계)
        rid = request.META.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex[:16]
        request.audit_request_id = rid

    def process_response(self, request, response):
        try:
            start = getattr(request, "_audit_start", None)
            duration_ms = int((time.perf_counter() - start) * 1000) if start else 0

            user = getattr(request, "user", None)
            is_auth = bool(getattr(user, "is_authenticated", False))

            # path/querystring
            path = (getattr(request, "path", "") or "")[:512]
            qs = ""
            if hasattr(request, "META"):
                raw_qs = request.META.get("QUERY_STRING", "") or ""
                qs = mask_querystring(raw_qs)[:1024]

            ip = get_client_ip(request)[:64]
            ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:512]
            ref = (request.META.get("HTTP_REFERER", "") or "")[:512]
            sess = (getattr(request, "session", None) and request.session.session_key) or ""
            sess = (sess or "")[:64]
            rid = (getattr(request, "audit_request_id", "") or "")[:64]

            RequestLog.objects.create(
                user=user if is_auth else None,
                is_authenticated=is_auth,
                method=(request.method or "")[:10],
                path=path,
                querystring=qs,
                status_code=int(getattr(response, "status_code", 0) or 0),
                duration_ms=duration_ms,
                ip=ip,
                user_agent=ua,
                referer=ref,
                request_id=rid,
                session_key=sess,
            )
        except Exception:
            # 로깅 실패가 서비스 기능을 깨지 않도록
            pass

        return response

    def process_exception(self, request, exception):
        # 예외도 process_response에서 500으로 잡히는 경우가 많지만,
        # 필요하면 여기서 별도 처리 가능(현재는 비워둠)
        return None