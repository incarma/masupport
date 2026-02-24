# dash/tasks/pipeline.py
from __future__ import annotations

import calendar
import logging
import re
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Tuple

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Sum

from accounts.models import CustomUser
from dash.models import SalesDailyAgg, SalesRecord
from dash.services.agg import build_daily_agg_for_month
from dash.ml.forecast import (
    build_train_df,
    load_models,
    save_models,
    _train_quantile_models,
    predict_month_total,
    upsert_forecast,
)

logger = logging.getLogger(__name__)

CATEGORIES = ["long", "car", "long_nonlife", "long_life"]
MODEL_VER = "lgbm_v1"

# ------------------------------------------------------------
# Lock util (중복 실행 방지)
# ------------------------------------------------------------
def _with_lock(lock_key: str, ttl_sec: int, fn: Callable[[], dict]) -> dict:
    """
    cache.add: 키 없을 때만 set -> True
    """
    if not cache.add(lock_key, "1", ttl_sec):
        logger.info("[dash.pipeline] skip (locked) key=%s", lock_key)
        return {"ok": True, "skipped": True, "lock_key": lock_key}
    try:
        return fn()
    finally:
        cache.delete(lock_key)


# ------------------------------------------------------------
# YM helpers
# ------------------------------------------------------------
def _ym_now() -> str:
    # timezone-aware 권장 (현재는 ym만 쓰므로 날짜 기준만 정확하면 됨)
    return timezone.now().strftime("%Y-%m")


def _ym_to_ordinal(ym: str) -> int:
    """
    YYYY-MM -> (year * 12 + month) 로 월 단위 비교 가능하게 변환
    """
    y, m = map(int, ym.split("-"))
    return y * 12 + m


def _valid_ym_format(ym: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}", (ym or "").strip()))


def _valid_ym_range(ym: str, *, past_months: int = 36, future_months: int = 1) -> bool:
    """
    운영 정책:
    - 과거 past_months 개월 ~ 미래 future_months 개월 범위만 허용
    (연도 기준이 아니라 '월' 기준으로 정확히 제한)
    """
    if not _valid_ym_format(ym):
        return False
    try:
        y, m = map(int, ym.split("-"))
        if not (1 <= m <= 12):
            return False
    except Exception:
        return False

    now_ym = _ym_now()
    now_ord = _ym_to_ordinal(now_ym)
    ym_ord = _ym_to_ordinal(ym)

    if ym_ord < (now_ord - past_months):
        return False
    if ym_ord > (now_ord + future_months):
        return False
    return True


def _prev_ym(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    if m == 1:
        return f"{y-1:04d}-12"
    return f"{y:04d}-{m-1:02d}"


def _last_day(ym: str) -> int:
    y, m = map(int, ym.split("-"))
    return calendar.monthrange(y, m)[1]


def _infer_asof_day(ym: str) -> int:
    """
    운영: '오늘 일자' 기준(말일 초과 방지)
    """
    today = timezone.localdate()
    d = today.day
    return max(1, min(d, _last_day(ym)))


# ------------------------------------------------------------
# scope 수집 (운영 권장: snapshot까지 포함)
# ------------------------------------------------------------
def iter_scopes() -> Iterable[Tuple[str, str]]:
    """
    scope_type: all/part/branch
    scope_key : */부서명/지점명
    """
    # all
    yield ("all", "*")

    # parts: CustomUser + SalesRecord snapshot 합집합
    user_parts = list(
        CustomUser.objects.exclude(part__isnull=True).exclude(part__exact="")
        .values_list("part", flat=True).distinct()
    )
    snap_parts = list(
        SalesRecord.objects.exclude(part_snapshot__isnull=True).exclude(part_snapshot__exact="")
        .values_list("part_snapshot", flat=True).distinct()
    )
    parts = sorted({str(p).strip() for p in (user_parts + snap_parts) if str(p).strip() and str(p).strip().lower() != "nan"})
    for p in parts:
        yield ("part", p)

    # branches: CustomUser + SalesRecord snapshot 합집합
    user_branches = list(
        CustomUser.objects.exclude(branch__isnull=True).exclude(branch__exact="")
        .values_list("branch", flat=True).distinct()
    )
    snap_branches = list(
        SalesRecord.objects.exclude(branch_snapshot__isnull=True).exclude(branch_snapshot__exact="")
        .values_list("branch_snapshot", flat=True).distinct()
    )
    branches = sorted({str(b).strip() for b in (user_branches + snap_branches) if str(b).strip() and str(b).strip().lower() != "nan"})
    for b in branches:
        yield ("branch", b)


# ------------------------------------------------------------
# 모델 학습/로드 보장
# ------------------------------------------------------------
def _ensure_models(scope_type: str, scope_key: str, category: str, *, min_rows: int = 20) -> dict:
    models = load_models(scope_type, scope_key, category)
    if models:
        return models

    df = build_train_df(scope_type, scope_key, category, max_months=24)
    if len(df) < min_rows:
        logger.warning(
            "[dash.pipeline] not enough train rows: %s/%s/%s rows=%s",
            scope_type, scope_key, category, len(df),
        )
        return {}

    models = _train_quantile_models(df)
    save_models(scope_type, scope_key, category, models)
    return models


# ------------------------------------------------------------
# 집계 생성 (SalesDailyAgg upsert)
# ------------------------------------------------------------
def _build_aggs_for_ym(ym: str) -> dict:
    done = 0
    for scope_type, scope_key in iter_scopes():
        try:
            build_daily_agg_for_month(ym, scope_type, scope_key)
            done += 1
        except Exception:
            logger.exception("[dash.pipeline] agg failed ym=%s scope=%s/%s", ym, scope_type, scope_key)
    return {"ym": ym, "scopes_done": done}


# ------------------------------------------------------------
# 예측 생성 (SalesForecast + SalesForecastDaily upsert)
# ------------------------------------------------------------
def _get_cumsum(scope_type: str, scope_key: str, category: str, ym: str, day: int) -> int:
    v = (
        SalesDailyAgg.objects.filter(
            ym=ym, day=day, scope_type=scope_type, scope_key=scope_key, category=category
        )
        .values_list("cumsum", flat=True)
        .first()
    )
    return int(v or 0)


def _get_total(scope_type: str, scope_key: str, category: str, ym: str) -> int:
    s = (
        SalesDailyAgg.objects.filter(
            ym=ym, scope_type=scope_type, scope_key=scope_key, category=category
        )
        .aggregate(s=Sum("amount"))
        .get("s")
    )
    return int(s or 0)


def _build_features(scope_type: str, scope_key: str, category: str, ym: str, asof_day: int) -> Dict[str, float]:
    y, m = map(int, ym.split("-"))
    last_day = calendar.monthrange(y, m)[1]
    prev = f"{y-1:04d}-12" if m == 1 else f"{y:04d}-{m-1:02d}"
    py = f"{y-1:04d}-{m:02d}"

    prev_last = _last_day(prev)
    py_last = _last_day(py)

    asof_day = max(1, min(asof_day, last_day))

    to_date = _get_cumsum(scope_type, scope_key, category, ym, min(asof_day, last_day))
    prev_to_date = _get_cumsum(scope_type, scope_key, category, prev, min(asof_day, prev_last))
    py_to_date = _get_cumsum(scope_type, scope_key, category, py, min(asof_day, py_last))

    prev_total = _get_total(scope_type, scope_key, category, prev)
    py_total = _get_total(scope_type, scope_key, category, py)

    return {
        "asof_day": float(asof_day),
        "last_day": float(last_day),
        "to_date": float(to_date),
        "avg_per_day": float(to_date) / float(max(asof_day, 1)),
        "remain_days": float(last_day - asof_day),
        "prev_to_date": float(prev_to_date),
        "py_to_date": float(py_to_date),
        "prev_total": float(prev_total),
        "py_total": float(py_total),
    }


def _build_forecasts_for_ym(ym: str, asof_day: int) -> dict:
    done = 0
    for scope_type, scope_key in iter_scopes():
        for cat in CATEGORIES:
            try:
                models = _ensure_models(scope_type, scope_key, cat)

                if not models:
                    # 학습데이터 부족 -> None으로 upsert (예측선은 표시 안 됨)
                    upsert_forecast(
                        ym=ym, asof_day=asof_day,
                        scope_type=scope_type, scope_key=scope_key,
                        category=cat, model_ver=MODEL_VER,
                        pred_total_p10=None, pred_total_p50=None, pred_total_p90=None,
                    )
                    done += 1
                    continue

                features = _build_features(scope_type, scope_key, cat, ym, asof_day)
                p10, p50, p90 = predict_month_total(models, features)

                upsert_forecast(
                    ym=ym, asof_day=asof_day,
                    scope_type=scope_type, scope_key=scope_key,
                    category=cat, model_ver=MODEL_VER,
                    pred_total_p10=p10, pred_total_p50=p50, pred_total_p90=p90,
                )
                done += 1

            except Exception:
                logger.exception(
                    "[dash.pipeline] forecast failed ym=%s asof=%s scope=%s/%s cat=%s",
                    ym, asof_day, scope_type, scope_key, cat,
                )

    return {"ym": ym, "asof_day": asof_day, "forecast_items_done": done}


# ------------------------------------------------------------
# ✅ 업로드 직후용: 특정 ym만 집계+예측 (부하 최소화)
# ------------------------------------------------------------
@shared_task(bind=True, ignore_result=True, name="dash.tasks.pipeline.build_sales_forecasts_for_yms")
def build_sales_forecasts_for_yms(self, yms: List[str], include_aggs: bool = True) -> None:
    """
    업로드 직후 '해당 ym만' 예측선을 즉시 만들기 위한 전용 task.

    - yms: ["YYYY-MM", ...]
    - include_aggs: True면 SalesDailyAgg 먼저 최신화
    - 방어:
      1) ym format/range 검증
      2) 최대 3개만 처리
      3) ym별 lock(중복 enqueue 방지)
    """
    if not isinstance(yms, (list, tuple)):
        yms = [str(yms)]

    cleaned: List[str] = []
    seen = set()
    for s in yms:
        ym = (str(s) or "").strip()
        if not _valid_ym_range(ym, past_months=36, future_months=1):
            continue
        if ym in seen:
            continue
        seen.add(ym)
        cleaned.append(ym)

    cleaned.sort(reverse=True)
    cleaned = cleaned[:3]
    if not cleaned:
        return

    for ym in cleaned:
        lock_key = f"dash:pipeline:upload:{ym}:lock"
        got = cache.add(lock_key, "1", timeout=60 * 20)
        if not got:
            continue

        try:
            asof = _infer_asof_day(ym)
            if include_aggs:
                _build_aggs_for_ym(ym)
                # (선택) 전월도 같이 최신화하면 비교선/feature 안정성 ↑
                _build_aggs_for_ym(_prev_ym(ym))
            _build_forecasts_for_ym(ym, asof)
        except Exception:
            logger.exception("[dash.pipeline] upload-triggered build failed ym=%s", ym)
        finally:
            cache.delete(lock_key)


# ============================================================
# Celery scheduled tasks (기존 유지)
# ============================================================
@shared_task(name="dash.tasks.pipeline.build_sales_aggs_hourly")
def build_sales_aggs_hourly():
    ym = _ym_now()
    prev = _prev_ym(ym)

    def run():
        r1 = _build_aggs_for_ym(ym)
        r2 = _build_aggs_for_ym(prev)
        return {"ok": True, "hourly": True, "results": [r1, r2]}

    return _with_lock("dash:pipeline:agg:hourly", 50 * 60, run)


@shared_task(name="dash.tasks.pipeline.build_sales_forecasts_daily")
def build_sales_forecasts_daily():
    ym = _ym_now()
    asof = _infer_asof_day(ym)

    def run():
        # 예측은 집계가 최신이어야 의미가 있으니 먼저 집계
        _build_aggs_for_ym(ym)
        _build_aggs_for_ym(_prev_ym(ym))
        r = _build_forecasts_for_ym(ym, asof)
        return {"ok": True, "daily": True, "result": r}

    return _with_lock("dash:pipeline:forecast:daily", 6 * 60 * 60, run)


@shared_task(name="dash.tasks.pipeline.build_sales_forecasts_hourly")
def build_sales_forecasts_hourly():
    ym = _ym_now()
    asof = _infer_asof_day(ym)

    def run():
        # 운영 기본: 이번달만
        _build_aggs_for_ym(ym)
        r = _build_forecasts_for_ym(ym, asof)
        return {"ok": True, "hourly_forecast": True, "result": r}

    return _with_lock("dash:pipeline:forecast:hourly", 50 * 60, run)