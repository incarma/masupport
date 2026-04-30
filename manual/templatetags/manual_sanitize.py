# django_ma/manual/templatetags/manual_sanitize.py
from __future__ import annotations

"""
Manual HTML Sanitizer Template Filter

목적:
- manual block content를 화면에 렌더링하기 전에 HTML allowlist 기반으로 정제한다.
- 기존 {{ b.content|safe }} 직접 렌더링을 제거하여 stored XSS 위험을 낮춘다.
- CSP style-src 'self' 전환을 위해 style attribute는 허용하지 않는다.

주의:
- 이 필터는 출력 방어선이다.
- 저장 시점 sanitize까지 추가하면 더 좋지만, 기존 DB에 저장된 content도 보호하려면 출력 필터가 우선이다.
"""

from django import template
from django.utils.safestring import mark_safe

import bleach

register = template.Library()


ALLOWED_TAGS = [
    "p", "br", "div", "span",
    "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li",
    "blockquote", "pre", "code",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td",
    "a",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "table": ["class"],
    "thead": ["class"],
    "tbody": ["class"],
    "tr": ["class"],
    "th": ["class", "colspan", "rowspan"],
    "td": ["class", "colspan", "rowspan"],
    "p": ["class"],
    "div": ["class"],
    "span": ["class"],
    "blockquote": ["class"],
    "pre": ["class"],
    "code": ["class"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def _nofollow_target_blank(attrs, new=False):
    """
    a[target=_blank] 링크에 rel 보강.
    bleach callback은 태그별 속성 후처리 용도.
    """
    href = attrs.get((None, "href"))
    if href:
        target = attrs.get((None, "target"))
        if target == "_blank":
            attrs[(None, "rel")] = "noopener noreferrer"
    return attrs


@register.filter(name="sanitize_manual_html")
def sanitize_manual_html(value: str) -> str:
    raw = "" if value is None else str(value)

    cleaned = bleach.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )

    # 링크 보강. style/on* 속성은 bleach.clean 단계에서 이미 제거된다.
    cleaned = bleach.linkify(
        cleaned,
        callbacks=[_nofollow_target_blank],
        skip_tags=["pre", "code"],
        parse_email=True,
    )

    return mark_safe(cleaned)