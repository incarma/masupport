# django_ma/audit/utils.py
from __future__ import annotations

import re
from ipaddress import ip_address, ip_network
from urllib.parse import parse_qsl, urlencode

from django.conf import settings

SENSITIVE_KEYS = {
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token",
    "authorization", "auth", "api_key",
    "ssn", "resident", "resident_no", "jumin", "주민번호",
    "session", "sessionid", "csrftoken",
}

SENSITIVE_KEY_FRAGMENTS = (
    "password", "passwd", "pwd",
    "token", "authorization", "auth", "api_key",
    "secret", "session", "cookie", "csrf",
    "ssn", "resident", "jumin", "주민",
)

PHONE_RE = re.compile(r"\b(01[016789])[-.\s]?(\d{3,4})[-.\s]?(\d{4})\b")
SSN_RE = re.compile(r"\b(\d{6})[-\s]?(\d{7})\b")


def is_sensitive_key(key: str) -> bool:
    k = (key or "").strip().lower()
    if not k:
        return False
    return k in SENSITIVE_KEYS or any(fragment in k for fragment in SENSITIVE_KEY_FRAGMENTS)


def mask_value(v: str) -> str:
    if not v:
        return ""
    s = str(v)

    # Phone: 010-1234-5678 -> 010-****-5678
    s = PHONE_RE.sub(lambda m: f"{m.group(1)}-****-{m.group(3)}", s)

    # SSN: 900101-1234567 -> 900101-*******
    s = SSN_RE.sub(lambda m: f"{m.group(1)}-*******", s)

    # Hard truncate (avoid huge log)
    if len(s) > 500:
        s = s[:500] + "…"
    return s


def mask_querystring(raw_qs: str) -> str:
    """
    Querystring은 저장해도 되지만,
    민감키는 value를 마스킹/삭제한다.
    """
    if not raw_qs:
        return ""
    try:
        pairs = parse_qsl(raw_qs, keep_blank_values=True)
        out = []
        for k, v in pairs:
            kl = (k or "").strip().lower()
            if is_sensitive_key(kl):
                out.append((k, "***"))
            else:
                out.append((k, mask_value(v)))
        return urlencode(out, doseq=True)
    except Exception:
        # 파싱 실패 시 통째로 마스킹
        return "***"


def get_client_ip(request) -> str:
    """
    신뢰 가능한 reverse proxy에서 들어온 요청일 때만 X-Forwarded-For/X-Real-IP를 사용한다.
    그렇지 않으면 REMOTE_ADDR을 최종 IP로 사용한다.
    """
    if request is None:
        return ""

    remote_addr = (request.META.get("REMOTE_ADDR", "") or "").strip()

    # 운영에서만 proxy header 신뢰를 켜는 것을 기본값으로 둔다.
    # dev/local 직접 접근에서는 X-Forwarded-For spoofing 방지를 위해 REMOTE_ADDR만 사용한다.
    if not getattr(settings, "AUDIT_PROXY_HEADER_ENABLED", False):
        return remote_addr

    trusted_cidrs = getattr(settings, "AUDIT_TRUSTED_PROXY_CIDRS", ())
    trusted = False
    try:
        remote_ip = ip_address(remote_addr)
        trusted = any(remote_ip in ip_network(cidr, strict=False) for cidr in trusted_cidrs)
    except Exception:
        trusted = False

    if not trusted:
        return remote_addr

    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        # XFF 형식: client, proxy1, proxy2
        # 신뢰 가능한 proxy가 전달한 값일 때만 가장 왼쪽의 유효 IP를 client IP로 본다.
        for candidate in xff.split(","):
            candidate = candidate.strip()
            try:
                ip_address(candidate)
                return candidate
            except Exception:
                continue

    xrip = request.META.get("HTTP_X_REAL_IP", "")
    if xrip:
        try:
            ip_address(xrip.strip())
            return xrip.strip()
        except Exception:
            pass

    return remote_addr