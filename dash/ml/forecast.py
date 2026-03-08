# django_ma/dash/ml/forecast.py
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from django.conf import settings
from django.db.models import Sum

from dash.models import SalesDailyAgg, SalesForecast, SalesForecastDaily
import logging

logger = logging.getLogger(__name__)

try:
    import lightgbm as lgb
except Exception:
    lgb = None

MODEL_DIR = getattr(settings, "DASH_MODEL_DIR", "var/dash_models")  # 원하는 경로로 조정

CATS = ["long", "car", "long_nonlife", "long_life"]

def _last_day(ym: str) -> int:
    y, m = map(int, ym.split("-"))
    return calendar.monthrange(y, m)[1]

def _prev_ym(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    if m == 1:
        return f"{y-1:04d}-12"
    return f"{y:04d}-{m-1:02d}"

def _prev_year_ym(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{y-1:04d}-{m:02d}"

def _month_total(ym: str, scope_type: str, scope_key: str, category: str) -> int:
    return int(
        SalesDailyAgg.objects.filter(ym=ym, scope_type=scope_type, scope_key=scope_key, category=category)
        .aggregate(s=Sum("amount"))["s"] or 0
    )

def _cumsum_at(ym: str, day: int, scope_type: str, scope_key: str, category: str) -> int:
    row = SalesDailyAgg.objects.filter(
        ym=ym, day=day, scope_type=scope_type, scope_key=scope_key, category=category
    ).values("cumsum").first()
    return int((row or {}).get("cumsum") or 0)

def _build_profile(
    ym_list: List[str], scope_type: str, scope_key: str, category: str, last_day: int
) -> List[float]:
    """
    day_share[d] = avg( amount(d) / month_total )  (최근 ym 평균)
    """
    shares = np.zeros(last_day, dtype=float)
    cnt = 0

    for ym in ym_list:
        total = _month_total(ym, scope_type, scope_key, category)
        if total <= 0:
            continue
        rows = SalesDailyAgg.objects.filter(
            ym=ym, scope_type=scope_type, scope_key=scope_key, category=category
        ).values("day", "amount")
        day_amt = {r["day"]: int(r["amount"] or 0) for r in rows}
        v = np.array([day_amt.get(d, 0) / total for d in range(1, last_day + 1)], dtype=float)
        shares += v
        cnt += 1

    if cnt <= 0:
        # fallback: 균등분배
        return (np.ones(last_day) / last_day).tolist()

    shares = shares / cnt
    # 혹시 음수/NaN 방지
    shares = np.clip(shares, 0, None)
    s = float(shares.sum()) or 1.0
    shares = shares / s
    return shares.tolist()

def _candidate_train_months(end_ym: str, n: int = 24) -> List[str]:
    # end_ym 이전 n개월 목록 (간단 구현)
    y, m = map(int, end_ym.split("-"))
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y -= 1
            m = 12
        out.append(f"{y:04d}-{m:02d}")
    return out

def build_train_df(scope_type: str, scope_key: str, category: str, max_months: int = 24) -> pd.DataFrame:
    """
    학습 데이터: 각 ym에 대해 asof_day(1..last_day)를 샘플로 만들면 많아짐.
    운영은 asof_day를 [5,10,15,20,25] 같은 고정 셋만 써도 충분히 잘 됨.
    """
    # 최근 24개월로 제한
    # (원하면 SalesDailyAgg 존재하는 ym 목록을 distinct로 가져와도 됨)
    # 여기선 “현재월 기준”으로 이전 max_months만
    now_ym = datetime.now().strftime("%Y-%m")
    months = _candidate_train_months(now_ym, max_months)

    rows = []
    for ym in months:
        last_day = _last_day(ym)
        total = _month_total(ym, scope_type, scope_key, category)
        if total <= 0:
            continue

        prev = _prev_ym(ym)
        py = _prev_year_ym(ym)

        for asof in [5, 10, 15, 20, 25]:
            if asof > last_day:
                continue

            to_date = _cumsum_at(ym, asof, scope_type, scope_key, category)
            prev_to_date = _cumsum_at(prev, min(asof, _last_day(prev)), scope_type, scope_key, category)
            py_to_date = _cumsum_at(py, min(asof, _last_day(py)), scope_type, scope_key, category)

            prev_total = _month_total(prev, scope_type, scope_key, category)
            py_total = _month_total(py, scope_type, scope_key, category)

            rows.append({
                "ym": ym,
                "asof_day": asof,
                "last_day": last_day,
                "to_date": to_date,
                "avg_per_day": (to_date / max(asof, 1)),
                "remain_days": (last_day - asof),
                "prev_to_date": prev_to_date,
                "py_to_date": py_to_date,
                "prev_total": prev_total,
                "py_total": py_total,
                "target_total": total,
            })

    df = pd.DataFrame(rows)

    logger.info(
        "[dash.forecast] train dataset rows=%s scope=%s/%s cat=%s",
        len(df), scope_type, scope_key, category
    )

    return df

def _train_quantile_models(df: pd.DataFrame) -> Dict[str, object]:
    if lgb is None:
        raise RuntimeError("lightgbm not installed")

    feats = ["asof_day", "last_day", "to_date", "avg_per_day", "remain_days",
             "prev_to_date", "py_to_date", "prev_total", "py_total"]
    X = df[feats]
    y = df["target_total"]

    params = dict(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
    )

    models = {}
    for q, name in [(0.1, "p10"), (0.5, "p50"), (0.9, "p90")]:
        m = lgb.LGBMRegressor(**params, objective="quantile", alpha=q)
        m.fit(X, y)
        models[name] = (m, feats)
    return models

def save_models(scope_type: str, scope_key: str, category: str, models: Dict[str, object]) -> str:
    import os
    os.makedirs(MODEL_DIR, exist_ok=True)
    tag = f"{scope_type}__{scope_key.replace('/','_')}__{category}"
    path = f"{MODEL_DIR}/lgbm_v1__{tag}.joblib"
    joblib.dump(models, path)
    return path

def load_models(scope_type: str, scope_key: str, category: str) -> Dict[str, object]:
    import os
    tag = f"{scope_type}__{scope_key.replace('/','_')}__{category}"
    path = f"{MODEL_DIR}/lgbm_v1__{tag}.joblib"
    if not os.path.exists(path):
        return {}
    return joblib.load(path)

def predict_month_total(models: Dict[str, object], features: Dict) -> Tuple[int|None, int|None, int|None]:
    if not models:
        return (None, None, None)
    out = {}
    for name in ["p10", "p50", "p90"]:
        m, feats = models[name]
        X = pd.DataFrame([[features.get(f) for f in feats]], columns=feats)
        out[name] = int(max(0, float(m.predict(X)[0])))
    return out["p10"], out["p50"], out["p90"]

def upsert_forecast(
    ym: str, asof_day: int, scope_type: str, scope_key: str, category: str,
    pred_total_p10: int|None, pred_total_p50: int|None, pred_total_p90: int|None,
    profile_months: List[str] | None = None,
    model_ver: str = "lgbm_v1",
) -> SalesForecast:
    last_day = _last_day(ym)
    asof_day = min(asof_day, last_day)
    actual_to_date = _cumsum_at(ym, asof_day, scope_type, scope_key, category)

    obj, _ = SalesForecast.objects.update_or_create(
        ym=ym, asof_day=asof_day, scope_type=scope_type, scope_key=scope_key,
        category=category, model_ver=model_ver,
        defaults=dict(
            pred_total_p10=pred_total_p10,
            pred_total_p50=pred_total_p50,
            pred_total_p90=pred_total_p90,
            actual_to_date=actual_to_date,
        ),
    )

    # 일별 분배(밴드까지)
    prev_months = profile_months or _candidate_train_months(ym, 6)
    shares = _build_profile(prev_months, scope_type, scope_key, category, last_day)

    def build_daily(pred_total: int|None) -> Tuple[List[int|None], List[int|None]]:
        if pred_total is None:
            return ([None]*last_day, [None]*last_day)

        pred_total = max(pred_total, actual_to_date)  # 예측이 실제누적보다 작아지는 것 방지
        remain = pred_total - actual_to_date
        remain_days = list(range(asof_day+1, last_day+1))

        # 남은 일자 share 재정규화
        if remain_days:
            s = sum(shares[d-1] for d in remain_days) or 1.0
        else:
            s = 1.0

        pred_amount = [None]*last_day
        # 과거 일자는 “예측”이 아니라 None로 두고, 차트에서는 실제선 사용
        for d in remain_days:
            w = shares[d-1] / s
            pred_amount[d-1] = int(round(remain * w))

        # 누적(예측선용): asof까지는 actual_to_date로 시작
        pred_cumsum = [None]*last_day
        running = 0
        for d in range(1, last_day+1):
            if d <= asof_day:
                running = _cumsum_at(ym, d, scope_type, scope_key, category)
                pred_cumsum[d-1] = running  # 실제 누적
            else:
                running += int(pred_amount[d-1] or 0)
                pred_cumsum[d-1] = running
        return pred_amount, pred_cumsum

    amt10, cs10 = build_daily(pred_total_p10)
    amt50, cs50 = build_daily(pred_total_p50)
    amt90, cs90 = build_daily(pred_total_p90)

    SalesForecastDaily.objects.filter(forecast=obj).delete()
    bulk = []
    for d in range(1, last_day+1):
        bulk.append(SalesForecastDaily(
            forecast=obj, day=d,
            pred_amount_p10=amt10[d-1], pred_amount_p50=amt50[d-1], pred_amount_p90=amt90[d-1],
            pred_cumsum_p10=cs10[d-1], pred_cumsum_p50=cs50[d-1], pred_cumsum_p90=cs90[d-1],
        ))
    SalesForecastDaily.objects.bulk_create(bulk, batch_size=500)

    return obj
