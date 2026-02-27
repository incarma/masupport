# django_ma/audit/utils.py
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode

SENSITIVE_KEYS = {
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token",
    "authorization", "auth", "api_key",
    "ssn", "resident", "resident_no", "jumin", "주민번호",
    "session", "sessionid", "csrftoken",
}

PHONE_RE = re.compile(r"\b(01[016789])[-.\s]?(\d{3,4})[-.\s]?(\d{4})\b")
SSN_RE = re.compile(r"\b(\d{6})[-\s]?(\d{7})\b")


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
            if kl in SENSITIVE_KEYS:
                out.append((k, "***"))
            else:
                out.append((k, mask_value(v)))
        return urlencode(out, doseq=True)
    except Exception:
        # 파싱 실패 시 통째로 마스킹
        return "***"


def get_client_ip(request) -> str:
    # (운영 환경에 따라) X-Forwarded-For / X-Real-IP 를 신뢰할지 결정 필요
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        # "client, proxy1, proxy2"
        return xff.split(",")[0].strip()
    xrip = request.META.get("HTTP_X_REAL_IP", "")
    if xrip:
        return xrip.strip()
    return request.META.get("REMOTE_ADDR", "") or ""