# django_ma/dash/task_runtime.py
from __future__ import annotations

import calendar
import logging
import re
from typing import Callable, Dict, Iterable, List, Tuple

from celery import shared_task
from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone

from accounts.models import CustomUser
from dash.models import SalesDailyAgg, SalesForecast, SalesRecord
from dash.services.agg import build_daily_agg_for_month
from dash.ml.forecast import (
    build_train_df,
    load_models,
    predict_month_total,
    save_models,
    upsert_forecast,
    _train_quantile_models,
)

logger = logging.getLogger(__name__)

# 대시보드 4개 차트 기준 카테고리 SSOT
CATEGORIES = ["long", "car", "long_nonlife", "long_life"]

# 예측 모델 버전 SSOT
MODEL_VER = "lgbm_v1"


# ============================================================
# 공통 Lock 유틸
# - 중복 실행 방지용
# - cache.add()가 True일 때만 실행
# ============================================================
def _with_lock(lock_key: str, ttl_sec: int, fn: Callable[[], dict]) -> dict:
    if not cache.add(lock_key, "1", ttl_sec):
        logger.info("[dash.runtime] skip (locked) key=%s", lock_key)
        return {"ok": True, "skipped": True, "lock_key": lock_key}
    try:
        return fn()
    finally:
        cache.delete(lock_key)


# ============================================================
# YM / 날짜 유틸
# ============================================================
def _ym_now() -> str:
    return timezone.now().strftime("%Y-%m")


def _ym_to_ordinal(ym: str) -> int:
    y, m = map(int, ym.split("-"))
    return y * 12 + m


def _valid_ym_format(ym: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}", (ym or "").strip()))


def _valid_ym_range(ym: str, *, past_months: int = 36, future_months: int = 1) -> bool:
    """
    운영 방어 규칙
    - 과거 36개월 ~ 미래 1개월 범위만 허용
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
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def _last_day(ym: str) -> int:
    y, m = map(int, ym.split("-"))
    return calendar.monthrange(y, m)[1]


def _infer_asof_day(ym: str) -> int:
    """
    운영 기준:
    - 현재 로컬 날짜 기준 일자 사용
    - 말일 초과 방지
    """
    today = timezone.localdate()
    return max(1, min(today.day, _last_day(ym)))


# ============================================================
# Scope 수집
# - SalesDailyAgg는 scope_type/scope_key 구조를 사용하므로
#   예측/집계는 동일한 scope 집합을 기준으로 돌아야 함
# ============================================================
def iter_scopes() -> Iterable[Tuple[str, str]]:
    """
    반환 형식
    - ("all", "*")
    - ("part", "<부서명>")
    - ("branch", "<지점명>")
    """
    # 전체 스코프
    yield ("all", "*")

    # 부서 scope: CustomUser + SalesRecord snapshot 합집합
    user_parts = list(
        CustomUser.objects.exclude(part__isnull=True)
        .exclude(part__exact="")
        .values_list("part", flat=True)
        .distinct()
    )
    snap_parts = list(
        SalesRecord.objects.exclude(part_snapshot__isnull=True)
        .exclude(part_snapshot__exact="")
        .values_list("part_snapshot", flat=True)
        .distinct()
    )
    parts = sorted(
        {
            str(p).strip()
            for p in (user_parts + snap_parts)
            if p and str(p).strip() and str(p).strip().lower() != "nan"
        }
    )
    for p in parts:
        yield ("part", p)

    # 지점 scope: CustomUser + SalesRecord snapshot 합집합
    user_branches = list(
        CustomUser.objects.exclude(branch__isnull=True)
        .exclude(branch__exact="")
        .values_list("branch", flat=True)
        .distinct()
    )
    snap_branches = list(
        SalesRecord.objects.exclude(branch_snapshot__isnull=True)
        .exclude(branch_snapshot__exact="")
        .values_list("branch_snapshot", flat=True)
        .distinct()
    )
    branches = sorted(
        {
            str(b).strip()
            for b in (user_branches + snap_branches)
            if b and str(b).strip() and str(b).strip().lower() != "nan"
        }
    )
    for b in branches:
        yield ("branch", b)


# ============================================================
# Aggregation 생성
# - 특정 scope 단위 집계
# - 특정 월 전체 scope 집계
# ============================================================
def _build_aggs_for_scope(ym: str, scope_type: str, scope_key: str) -> None:
    logger.info("[dash.runtime] build agg ym=%s scope=%s/%s", ym, scope_type, scope_key)
    build_daily_agg_for_month(ym, scope_type, scope_key)


def _build_aggs_for_ym(ym: str) -> dict:
    done = 0
    for scope_type, scope_key in iter_scopes():
        try:
            _build_aggs_for_scope(ym, scope_type, scope_key)
            done += 1
        except Exception:
            logger.exception("[dash.runtime] agg failed ym=%s scope=%s/%s", ym, scope_type, scope_key)

    return {"ym": ym, "scopes_done": done}


# ============================================================
# 모델 준비
# - 저장된 모델이 있으면 재사용
# - 없으면 학습 데이터 생성 후 LightGBM 학습
# - 학습 row 부족 시 빈 dict 반환
# ============================================================
def _ensure_models(scope_type: str, scope_key: str, category: str, *, min_rows: int = 20) -> dict:
    models = load_models(scope_type, scope_key, category)
    if models:
        return models

    df = build_train_df(scope_type, scope_key, category, max_months=24)
    if len(df) < min_rows:
        logger.warning(
            "[dash.runtime] not enough train rows: %s/%s/%s rows=%s",
            scope_type,
            scope_key,
            category,
            len(df),
        )
        return {}

    models = _train_quantile_models(df)
    save_models(scope_type, scope_key, category, models)
    return models


# ============================================================
# Aggregation 조회 유틸
# - feature 생성과 upsert_forecast 계산에 공통 사용
# ============================================================
def _get_cumsum(scope_type: str, scope_key: str, category: str, ym: str, day: int) -> int:
    value = (
        SalesDailyAgg.objects.filter(
            ym=ym,
            day=day,
            scope_type=scope_type,
            scope_key=scope_key,
            category=category,
        )
        .values_list("cumsum", flat=True)
        .first()
    )
    return int(value or 0)


def _get_total(scope_type: str, scope_key: str, category: str, ym: str) -> int:
    summed = (
        SalesDailyAgg.objects.filter(
            ym=ym,
            scope_type=scope_type,
            scope_key=scope_key,
            category=category,
        )
        .aggregate(s=Sum("amount"))
        .get("s")
    )
    return int(summed or 0)


# ============================================================
# 예측 feature 생성
# - 이번달 asof 시점
# - 전월 동일 asof
# - 전년동월 동일 asof
# ============================================================
def _build_features(scope_type: str, scope_key: str, category: str, ym: str, asof_day: int) -> Dict[str, float]:
    y, m = map(int, ym.split("-"))
    last_day = calendar.monthrange(y, m)[1]
    prev = _prev_ym(ym)
    py = f"{y - 1:04d}-{m:02d}"

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


# ============================================================
# 특정 scope 예측 생성
# - 카테고리 4종에 대해 반복
# - 학습 데이터가 부족하면 None forecast를 저장
#   (프론트는 pred=None 처리)
# ============================================================
def _build_forecast_for_scope(ym: str, asof_day: int, scope_type: str, scope_key: str) -> dict:
    done = 0

    for category in CATEGORIES:
        try:
            models = _ensure_models(scope_type, scope_key, category)

            if not models:
                upsert_forecast(
                    ym=ym,
                    asof_day=asof_day,
                    scope_type=scope_type,
                    scope_key=scope_key,
                    category=category,
                    model_ver=MODEL_VER,
                    pred_total_p10=None,
                    pred_total_p50=None,
                    pred_total_p90=None,
                )
                done += 1
                continue

            features = _build_features(scope_type, scope_key, category, ym, asof_day)
            p10, p50, p90 = predict_month_total(models, features)

            upsert_forecast(
                ym=ym,
                asof_day=asof_day,
                scope_type=scope_type,
                scope_key=scope_key,
                category=category,
                model_ver=MODEL_VER,
                pred_total_p10=p10,
                pred_total_p50=p50,
                pred_total_p90=p90,
            )
            done += 1

        except Exception:
            logger.exception(
                "[dash.runtime] forecast failed ym=%s asof=%s scope=%s/%s cat=%s",
                ym,
                asof_day,
                scope_type,
                scope_key,
                category,
            )

    return {
        "ym": ym,
        "asof_day": asof_day,
        "scope_type": scope_type,
        "scope_key": scope_key,
        "forecast_items_done": done,
    }


# ============================================================
# API / 수동 디버깅용 동기 helper
# - 요청된 특정 scope에 대해서만 집계 + 예측 생성
# - api_forecast bootstrap에서 사용
# ============================================================
def build_scope_forecast_now(
    ym: str,
    asof_day: int,
    scope_type: str,
    scope_key: str,
    *,
    include_prev: bool = True,
) -> dict:
    _build_aggs_for_scope(ym, scope_type, scope_key)

    if include_prev:
        _build_aggs_for_scope(_prev_ym(ym), scope_type, scope_key)

    return _build_forecast_for_scope(ym, asof_day, scope_type, scope_key)


# ============================================================
# 업로드 직후 특정 YM 예측 생성 task
# - 현재 월도 최대 3개만 처리
# - include_aggs=True면 집계 먼저 최신화
# ============================================================
@shared_task(bind=True, ignore_result=True, name="dash.tasks.build_sales_forecasts_for_yms")
def build_sales_forecasts_for_yms(self, yms: List[str], include_aggs: bool = True) -> None:
    if not isinstance(yms, (list, tuple)):
        yms = [str(yms)]

    cleaned: List[str] = []
    seen = set()

    for raw in yms:
        ym = (str(raw) or "").strip()
        if not _valid_ym_range(ym, past_months=36, future_months=1):
            continue
        if ym in seen:
            continue
        seen.add(ym)
        cleaned.append(ym)

    cleaned.sort(reverse=True)
    cleaned = cleaned[:3]

    if not cleaned:
        logger.info("[dash.runtime] upload task skipped: no valid ym")
        return

    for ym in cleaned:
        lock_key = f"dash:runtime:upload:{ym}:lock"
        got = cache.add(lock_key, "1", timeout=60 * 20)
        if not got:
            logger.info("[dash.runtime] upload task locked ym=%s", ym)
            continue

        try:
            asof = _infer_asof_day(ym)

            if include_aggs:
                _build_aggs_for_ym(ym)
                # feature 안정성을 위해 전월 집계도 갱신
                _build_aggs_for_ym(_prev_ym(ym))

            for scope_type, scope_key in iter_scopes():
                _build_forecast_for_scope(ym, asof, scope_type, scope_key)

        except Exception:
            logger.exception("[dash.runtime] upload-triggered build failed ym=%s", ym)
        finally:
            cache.delete(lock_key)


# ============================================================
# 레거시 호환용 전체 새로고침 task
# - Celery worker가 실제로 인식하는 이름은 dash.tasks.* 여야 하므로
#   기존 코드/운영과 호환되도록 유지
# ============================================================
@shared_task(bind=True, ignore_result=True, name="dash.tasks.dash_refresh_agg_and_forecast")
def dash_refresh_agg_and_forecast(self, ym: str | None = None, asof_day: int | None = None) -> dict:
    ym = (ym or _ym_now()).strip()
    asof_day = int(asof_day or _infer_asof_day(ym))

    def run():
        agg_now = _build_aggs_for_ym(ym)
        agg_prev = _build_aggs_for_ym(_prev_ym(ym))

        total_done = 0
        for scope_type, scope_key in iter_scopes():
            result = _build_forecast_for_scope(ym, asof_day, scope_type, scope_key)
            total_done += int(result.get("forecast_items_done") or 0)

        return {
            "ok": True,
            "ym": ym,
            "asof_day": asof_day,
            "agg_now": agg_now,
            "agg_prev": agg_prev,
            "forecast_items_done": total_done,
        }

    return _with_lock(f"dash:runtime:refresh:{ym}", 30 * 60, run)


# ============================================================
# 주기 집계 task
# ============================================================
@shared_task(name="dash.tasks.build_sales_aggs_hourly")
def build_sales_aggs_hourly():
    ym = _ym_now()
    prev = _prev_ym(ym)

    def run():
        result_now = _build_aggs_for_ym(ym)
        result_prev = _build_aggs_for_ym(prev)
        return {
            "ok": True,
            "hourly": True,
            "results": [result_now, result_prev],
        }

    return _with_lock("dash:runtime:agg:hourly", 50 * 60, run)


# ============================================================
# 일 1회 예측 task
# - 집계 최신화 후 이번달 forecast 생성
# ============================================================
@shared_task(name="dash.tasks.build_sales_forecasts_daily")
def build_sales_forecasts_daily():
    ym = _ym_now()
    asof = _infer_asof_day(ym)

    def run():
        _build_aggs_for_ym(ym)
        _build_aggs_for_ym(_prev_ym(ym))

        total_done = 0
        for scope_type, scope_key in iter_scopes():
            result = _build_forecast_for_scope(ym, asof, scope_type, scope_key)
            total_done += int(result.get("forecast_items_done") or 0)

        return {
            "ok": True,
            "daily": True,
            "ym": ym,
            "forecast_items_done": total_done,
        }

    return _with_lock("dash:runtime:forecast:daily", 6 * 60 * 60, run)


# ============================================================
# 시간 단위 예측 task
# - 현재 월도 기준 빠른 갱신용
# ============================================================
@shared_task(name="dash.tasks.build_sales_forecasts_hourly")
def build_sales_forecasts_hourly():
    ym = _ym_now()
    asof = _infer_asof_day(ym)

    def run():
        _build_aggs_for_ym(ym)

        total_done = 0
        for scope_type, scope_key in iter_scopes():
            result = _build_forecast_for_scope(ym, asof, scope_type, scope_key)
            total_done += int(result.get("forecast_items_done") or 0)

        return {
            "ok": True,
            "hourly_forecast": True,
            "ym": ym,
            "forecast_items_done": total_done,
        }

    return _with_lock("dash:runtime:forecast:hourly", 50 * 60, run)