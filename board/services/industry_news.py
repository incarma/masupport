# django_ma/board/services/industry_news.py
# =========================================================
# Board Industry News Service
# - 네이버 뉴스 수집/정규화/토픽추론/중복해시 로직 SSOT
# - 3단계부터 board가 수집 로직의 소유자
# - DB 저장 대상 모델은 현재 support.models.SupportArticle 재사용
# =========================================================

from __future__ import annotations

import hashlib
import json
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from board.constants_industry import (
    DEFAULT_INDUSTRY_NEWS_QUERIES,
    SOURCE_NAVER,
    TOPIC_KEYWORDS,
)

NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"
ALLOWED_ARTICLE_URL_SCHEMES = {"http", "https"}


def normalize_external_url(value: str) -> str:
    """
    외부 기사 URL 정규화/검증 SSOT.

    허용:
    - http://
    - https://

    차단:
    - javascript:, data:, file:, vbscript:
    - scheme 없는 상대경로
    - host 없는 URL
    """
    raw = (value or "").strip()
    if not raw:
        return ""

    try:
        parsed = urlsplit(raw)
    except Exception:
        return ""

    scheme = (parsed.scheme or "").lower()
    netloc = (parsed.netloc or "").strip()

    if scheme not in ALLOWED_ARTICLE_URL_SCHEMES:
        return ""
    if not netloc:
        return ""

    return raw[:1000]


def extract_source_name(url: str) -> str:
    """
    검증된 URL에서 출처 host 추출.
    """
    safe_url = normalize_external_url(url)
    if not safe_url:
        return ""
    try:
        return urlsplit(safe_url).netloc[:120]
    except Exception:
        return ""


def normalize_text(value: str) -> str:
    """
    네이버 검색 API 응답의 HTML 태그 및 엔티티 정리
    """
    return unescape(value or "").replace("<b>", "").replace("</b>", "").strip()


def infer_topic(title: str, summary: str) -> str:
    """
    제목/요약 기반 토픽 추론

    현재는 키워드 매칭 기반의 단순 분류이며,
    추후 AI 분류/요약으로 교체할 수 있습니다.
    """
    haystack = f"{title} {summary}".lower()

    for topic, keywords in TOPIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in haystack:
                return topic

    return ""


def build_hash(title: str, source_name: str, published_at) -> str:
    """
    기사 중복 제거용 해시
    """
    raw = f"{title}|{source_name}|{published_at.isoformat() if published_at else ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_naver_news(query: str, display: int = 20, start: int = 1, sort: str = "date") -> dict:
    """
    네이버 뉴스 검색 API 호출

    주의:
    - 페이지 렌더링 요청에서 직접 호출하지 않습니다.
    - 배치 수집 task에서만 사용합니다.
    """
    client_id = (getattr(settings, "NAVER_SEARCH_CLIENT_ID", "") or "").strip()
    client_secret = (getattr(settings, "NAVER_SEARCH_CLIENT_SECRET", "") or "").strip()

    if not client_id or not client_secret:
        raise RuntimeError("NAVER_SEARCH_CLIENT_ID / NAVER_SEARCH_CLIENT_SECRET 미설정")

    url = f"{NAVER_NEWS_API_URL}?query={quote(query)}&display={display}&start={start}&sort={sort}"
    req = Request(url)
    req.add_header("X-Naver-Client-Id", client_id)
    req.add_header("X-Naver-Client-Secret", client_secret)

    with urlopen(req, timeout=20) as resp:
        payload = resp.read().decode("utf-8")

    return json.loads(payload)


def parse_naver_item(item: dict, query: str) -> dict:
    """
    네이버 뉴스 item을 SupportArticle defaults dict 형태로 변환
    """
    title = normalize_text(item.get("title", ""))
    summary = normalize_text(item.get("description", ""))
    published_at = None

    pub_date = item.get("pubDate", "")
    if pub_date:
        published_at = parsedate_to_datetime(pub_date)
        if timezone.is_naive(published_at):
            published_at = timezone.make_aware(published_at, timezone.get_current_timezone())

    origin = normalize_external_url(item.get("originallink") or "")
    portal = normalize_external_url(item.get("link") or "")

    source_name = extract_source_name(origin or portal)

    topic = infer_topic(title, summary)
    normalized_hash = build_hash(title, source_name, published_at)

    return {
        "source_portal": SOURCE_NAVER,
        "source_name": source_name[:120],
        "external_id": portal[:255],
        "title": title[:300],
        "summary": summary,
        "original_url": origin,
        "portal_url": portal,
        "published_at": published_at,
        "collected_at": timezone.now(),
        "keyword_query": query[:120],
        "topic": topic,
        "tags_json": [query, topic] if topic else [query],
        "normalized_hash": normalized_hash,
        "raw_payload_json": item,
    }


def default_queries() -> list[str]:
    """
    기본 수집 키워드 목록 반환
    """
    return DEFAULT_INDUSTRY_NEWS_QUERIES[:]