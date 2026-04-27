# django_ma/manual/utils/sanitize.py

from __future__ import annotations

import re

try:
    import bleach
    from bleach.css_sanitizer import CSSSanitizer
except Exception:  # pragma: no cover
    bleach = None
    CSSSanitizer = None


ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s",
    "ol", "ul", "li",
    "blockquote", "pre", "code",
    "h1", "h2", "h3",
    "span", "a",
}

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "span": ["class"],
    "p": ["class"],
    "li": ["class"],
}

ALLOWED_PROTOCOLS = {"http", "https", "mailto"}

ALLOWED_CSS_PROPERTIES = {
    "color",
    "background-color",
    "text-align",
}


_DANGEROUS_TAG_RE = re.compile(
    r"<\s*/?\s*(script|iframe|object|embed|form|input|button|meta|link|style)[^>]*>",
    re.IGNORECASE,
)
_EVENT_HANDLER_RE = re.compile(r"\s+on[a-zA-Z]+\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL)
_JS_PROTOCOL_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


def _fallback_sanitize(html: str) -> str:
    """
    bleach 미설치 환경 방어용 최소 sanitizer.

    운영 권장:
    - requirements.txt에 bleach 추가
    - bleach 기반 allowlist sanitize 사용
    """
    value = str(html or "")

    value = _DANGEROUS_TAG_RE.sub("", value)
    value = _EVENT_HANDLER_RE.sub("", value)
    value = _JS_PROTOCOL_RE.sub("", value)

    return value


def _force_safe_anchor_attrs(html: str) -> str:
    """
    새 창 링크 보안 보강.

    Quill 링크가 target=_blank로 저장될 수 있으므로
    rel=noopener noreferrer를 보장한다.
    """
    def repl(match: re.Match) -> str:
        attrs = match.group(1) or ""

        # 이미 rel 속성이 있으면 중복 삽입하지 않는다.
        if re.search(r'\srel\s*=', attrs, flags=re.IGNORECASE):
            return f"<a{attrs}>"

        return f'<a rel="noopener noreferrer"{attrs}>'

    return re.sub(
        r"<a([^>]*)>",
        repl,
        html,
        flags=re.IGNORECASE,
    )


def sanitize_quill_html(html: str) -> str:
    """
    Quill HTML 저장 전 서버단 sanitize.

    차단 대상:
    - script / iframe / object / embed 등 실행성 태그
    - onerror / onclick 등 이벤트 핸들러 속성
    - javascript: URL
    """
    raw = str(html or "").strip()
    if not raw:
        return ""

    if bleach is None:
        return _force_safe_anchor_attrs(_fallback_sanitize(raw))
    
    css_sanitizer = (
        CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)
        if CSSSanitizer is not None
        else None
    )

    cleaned = bleach.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=css_sanitizer,
        strip=True,
    )

    return _force_safe_anchor_attrs(cleaned)