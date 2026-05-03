# django_ma/board/services/holidays.py
"""
대한민국 공휴일 수집/조회 서비스.

핵심 원칙:
- View/JS에서 외부 API 직접 호출 금지
- 이 서비스가 외부 API 호출, 응답 정규화, DB upsert, 캘린더 조회를 담당
- API 장애 시 기존 DB 캐시를 유지
- source='manual' 또는 'override' 데이터는 기본적으로 API 수집이 덮어쓰지 않음
"""

from __future__ import annotations

import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from audit.constants import ACTION
from audit.services import log_action
from board.models import KrHoliday

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 10 * 60
LOCK_KEY_PREFIX = "board:kr_holidays:sync"


class HolidaySyncError(RuntimeError):
    """공휴일 동기화 실패."""


def _year_lock_key(year: int) -> str:
    return f"{LOCK_KEY_PREFIX}:{year}"


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _mask_url_for_log(url: str) -> str:
    """
    serviceKey 노출 방지용 로그 URL 마스킹.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
        qs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        safe_qs = []
        for k, v in qs:
            if k.lower() in {"servicekey", "apikey", "api_key", "key"}:
                safe_qs.append((k, "***"))
            else:
                safe_qs.append((k, v))
        safe_query = urllib.parse.urlencode(safe_qs)
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, safe_query, parsed.fragment)
        )
    except Exception:
        return "<masked-url>"


def _build_api_url(year: int) -> str:
    """
    공공데이터포털 특일 정보 API URL 생성.

    주의:
    - serviceKey는 이미 인코딩된 키/디코딩 키가 운영 환경마다 다를 수 있다.
    - 나머지 파라미터만 urlencode하고 serviceKey는 원문 그대로 붙인다.
    """
    base_url = getattr(settings, "KR_HOLIDAY_API_BASE_URL", "").strip()
    api_key = getattr(settings, "KR_HOLIDAY_API_KEY", "").strip()

    if not base_url:
        raise HolidaySyncError("KR_HOLIDAY_API_BASE_URL이 설정되지 않았습니다.")
    if not api_key:
        raise HolidaySyncError("KR_HOLIDAY_API_KEY가 설정되지 않았습니다.")

    params = {
        "solYear": str(year),
        "numOfRows": "100",
        "pageNo": "1",
    }

    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}serviceKey={api_key}&{urllib.parse.urlencode(params)}"


def _text_of(parent: ET.Element, name: str) -> str:
    child = parent.find(name)
    return (child.text or "").strip() if child is not None else ""


def _parse_response_xml(raw: bytes) -> list[dict[str, Any]]:
    """
    XML 응답에서 item 목록을 추출한다.
    기대 필드:
      - dateName: 공휴일명
      - locdate: YYYYMMDD
      - isHoliday: Y/N
      - seq: 순번
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise HolidaySyncError("공휴일 API XML 파싱에 실패했습니다.") from exc

    result_code = root.findtext(".//resultCode", default="").strip()
    result_msg = root.findtext(".//resultMsg", default="").strip()
    if result_code and result_code not in {"00", "0"}:
        raise HolidaySyncError(f"공휴일 API 오류: {result_code} {result_msg}")

    items = root.findall(".//item")
    rows: list[dict[str, Any]] = []

    for item in items:
        rows.append(
            {
                "dateName": _text_of(item, "dateName"),
                "locdate": _text_of(item, "locdate"),
                "isHoliday": _text_of(item, "isHoliday"),
                "seq": _text_of(item, "seq"),
                "raw": {child.tag: child.text for child in list(item)},
            }
        )

    return rows


def fetch_kr_holidays_from_api(year: int) -> list[dict[str, Any]]:
    """
    외부 API에서 특정 연도 공휴일 데이터를 가져온다.
    """
    if not getattr(settings, "KR_HOLIDAY_API_ENABLED", False):
        raise HolidaySyncError("KR_HOLIDAY_API_ENABLED=False 상태입니다.")

    url = _build_api_url(year)
    timeout = int(getattr(settings, "KR_HOLIDAY_API_TIMEOUT", 10) or 10)

    logger.info("[kr_holidays] fetch start year=%s url=%s", year, _mask_url_for_log(url))

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "django_ma/kr-holiday-sync",
            "Accept": "application/xml,text/xml,*/*",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as exc:
        logger.exception("[kr_holidays] fetch failed year=%s", year)
        raise HolidaySyncError(f"{year}년 공휴일 API 호출 실패") from exc

    rows = _parse_response_xml(raw)
    logger.info("[kr_holidays] fetch done year=%s rows=%s", year, len(rows))
    return rows


def normalize_holiday_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    API 응답 1건을 KrHoliday upsert 가능한 dict로 정규화한다.
    """
    locdate = str(raw.get("locdate") or "").strip()
    name = str(raw.get("dateName") or "").strip()
    is_holiday_raw = str(raw.get("isHoliday") or "Y").strip().upper()

    if len(locdate) != 8 or not locdate.isdigit() or not name:
        return None

    y, m, d = int(locdate[:4]), int(locdate[4:6]), int(locdate[6:8])
    try:
        holiday_date = date(y, m, d)
    except ValueError:
        return None

    seq = str(raw.get("seq") or "").strip()
    source_event_id = f"{locdate}:{seq}" if seq else locdate

    return {
        "date": holiday_date,
        "name": name,
        "is_holiday": is_holiday_raw != "N",
        "is_temporary": "임시" in name,
        "source": KrHoliday.SOURCE_API,
        "source_event_id": source_event_id,
        "raw_payload": raw.get("raw") or raw,
        "fetched_at": timezone.now(),
    }


def sync_kr_holidays_for_year(
    year: int,
    *,
    request=None,
    source: str = KrHoliday.SOURCE_API,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """
    특정 연도 공휴일을 수집하고 DB에 upsert한다.

    force=False:
      - source='manual' 또는 'override' 기존 데이터는 보호한다.
    """
    year = _as_int(year)
    if year < 1900 or year > 2100:
        raise HolidaySyncError(f"지원하지 않는 연도입니다: {year}")

    lock_key = _year_lock_key(year)
    lock_acquired = False

    if not force:
        lock_acquired = cache.add(lock_key, "1", LOCK_TTL_SECONDS)
        if not lock_acquired:
            return {
                "ok": False,
                "year": year,
                "fetched": 0,
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "message": "동일 연도 동기화가 이미 실행 중입니다.",
            }

    try:
        fetched_rows = fetch_kr_holidays_from_api(year)
        normalized = [row for row in (normalize_holiday_row(r) for r in fetched_rows) if row]

        created = 0
        updated = 0
        skipped = 0

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "year": year,
                "fetched": len(fetched_rows),
                "normalized": len(normalized),
                "created": 0,
                "updated": 0,
                "skipped": 0,
            }

        with transaction.atomic():
            for row in normalized:
                existing = KrHoliday.objects.filter(date=row["date"]).first()

                if existing and existing.source in {KrHoliday.SOURCE_MANUAL, KrHoliday.SOURCE_OVERRIDE} and not force:
                    skipped += 1
                    continue

                if existing:
                    for field in (
                        "name",
                        "is_holiday",
                        "is_temporary",
                        "source",
                        "source_event_id",
                        "raw_payload",
                        "fetched_at",
                    ):
                        setattr(existing, field, row[field])
                    existing.save(
                        update_fields=[
                            "name",
                            "is_holiday",
                            "is_temporary",
                            "source",
                            "source_event_id",
                            "raw_payload",
                            "fetched_at",
                            "updated_at",
                        ]
                    )
                    updated += 1
                else:
                    KrHoliday.objects.create(**row)
                    created += 1

        result = {
            "ok": True,
            "year": year,
            "fetched": len(fetched_rows),
            "normalized": len(normalized),
            "created": created,
            "updated": updated,
            "skipped": skipped,
        }

        try:
            log_action(
                request,
                ACTION.BOARD_KR_HOLIDAY_SYNC,
                object_type="KrHoliday",
                object_id=str(year),
                meta=result,
                success=True,
            )
        except Exception:
            logger.exception("[kr_holidays] audit log failed year=%s", year)

        return result

    except Exception as exc:
        try:
            log_action(
                request,
                ACTION.BOARD_KR_HOLIDAY_SYNC,
                object_type="KrHoliday",
                object_id=str(year),
                meta={"year": year, "error": str(exc)},
                success=False,
                reason=str(exc)[:300],
            )
        except Exception:
            logger.exception("[kr_holidays] audit failure log failed year=%s", year)
        raise

    finally:
        if not force and lock_acquired:
            cache.delete(lock_key)


def get_sync_window_years(base_year: int | None = None) -> list[int]:
    """
    settings 기준 수집 window 연도 목록 반환.
    기본: 현재연도-1 ~ 현재연도+2
    """
    today = timezone.localdate()
    base = base_year or today.year
    before = max(0, int(getattr(settings, "KR_HOLIDAY_FETCH_YEARS_BEFORE", 1) or 0))
    after = max(0, int(getattr(settings, "KR_HOLIDAY_FETCH_YEARS_AFTER", 2) or 0))
    return list(range(base - before, base + after + 1))


def sync_kr_holidays_window(
    *,
    request=None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """
    기본 window 전체 연도를 순차 동기화한다.
    """
    results = []
    ok = True

    for year in get_sync_window_years():
        try:
            results.append(
                sync_kr_holidays_for_year(
                    year,
                    request=request,
                    dry_run=dry_run,
                    force=force,
                )
            )
        except Exception as exc:
            ok = False
            logger.exception("[kr_holidays] window sync failed year=%s", year)
            results.append(
                {
                    "ok": False,
                    "year": year,
                    "error": str(exc),
                }
            )

    return {
        "ok": ok,
        "years": [r.get("year") for r in results],
        "results": results,
    }


def get_holidays_between(start: date, end: date) -> list[dict[str, Any]]:
    """
    WorkTask 캘린더 렌더링용 공휴일 목록 반환.
    """
    if not start or not end:
        return []

    rows = (
        KrHoliday.objects
        .filter(date__gte=start, date__lte=end, is_holiday=True)
        .order_by("date")
        .values("date", "name", "is_temporary", "source")
    )

    return [
        {
            "date": row["date"].isoformat(),
            "name": row["name"],
            "is_temporary": bool(row["is_temporary"]),
            "source": row["source"],
        }
        for row in rows
    ]


# =============================================================================
# WorkTask 영업일 보정
# =============================================================================
def get_holiday_dates_between(start: date, end: date) -> set[date]:
    """
    기간 내 공휴일 날짜 set 반환.
    - WorkTask 캘린더의 '오늘 업무 표시일' 보정에 사용한다.
    """
    if not start or not end:
        return set()

    return set(
        KrHoliday.objects
        .filter(date__gte=start, date__lte=end, is_holiday=True)
        .values_list("date", flat=True)
    )


def is_business_day(day: date, *, holiday_dates: set[date] | None = None) -> bool:
    """
    평일 + 공휴일 아님 여부.
    """
    if day.weekday() >= 5:
        return False
    return day not in (holiday_dates or set())


def resolve_next_business_day(day: date, *, max_days: int = 14) -> date:
    """
    기준일이 주말/공휴일이면 가장 먼저 도래하는 평일을 반환한다.

    예:
      - 토요일 → 다음 월요일
      - 공휴일 화요일 → 다음 수요일
      - 연휴 중간 → 연휴 종료 후 첫 평일
    """
    end = day + timedelta(days=max_days)
    holiday_dates = get_holiday_dates_between(day, end)

    current = day
    for _ in range(max_days + 1):
        if is_business_day(current, holiday_dates=holiday_dates):
            return current
        current += timedelta(days=1)

    return day