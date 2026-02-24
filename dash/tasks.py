# django_ma/dash/tasks.py
from __future__ import annotations

from celery import shared_task
from datetime import datetime
from django.db import connection

from dash.services.agg import build_daily_agg_for_month
from dash.ml.forecast import build_train_df, _train_quantile_models, save_models, load_models, predict_month_total, upsert_forecast, CATS

def _scopes_for_run():
    # 운영에서는 all + (part 몇개) + (branch 몇개) 전부 돌리면 무거울 수 있음.
    # 우선: all + “현재월에 등장한 branch/part”만 대상으로 확장 추천.
    yield ("all", "*")

@shared_task
def dash_refresh_agg_and_forecast(ym: str | None = None, asof_day: int | None = None):
    if ym is None:
        ym = datetime.now().strftime("%Y-%m")
    if asof_day is None:
        asof_day = datetime.now().day

    for scope_type, scope_key in _scopes_for_run():
        # 1) 집계 갱신
        build_daily_agg_for_month(ym, scope_type, scope_key)

        for category in CATS:
            # 2) 모델 로드(없으면 학습 후 저장)
            models = load_models(scope_type, scope_key, category)
            if not models:
                df = build_train_df(scope_type, scope_key, category, max_months=24)
                if len(df) >= 30:  # 최소 샘플 가드
                    models = _train_quantile_models(df)
                    save_models(scope_type, scope_key, category, models)
                else:
                    # 샘플 부족이면 예측 생략(프로필만으로도 가능하게 바꿀 수 있음)
                    models = {}

            # 3) 피처 구성(현재월)
            #   - 집계테이블 기반으로 asof 누적, 전월/전년 동일 asof 누적, 전월/전년 총액
            from dash.ml.forecast import _last_day, _prev_ym, _prev_year_ym, _cumsum_at, _month_total
            last_day = _last_day(ym)
            asof = min(asof_day, last_day)

            prev = _prev_ym(ym)
            py = _prev_year_ym(ym)

            to_date = _cumsum_at(ym, asof, scope_type, scope_key, category)
            prev_to_date = _cumsum_at(prev, min(asof, _last_day(prev)), scope_type, scope_key, category)
            py_to_date = _cumsum_at(py, min(asof, _last_day(py)), scope_type, scope_key, category)
            prev_total = _month_total(prev, scope_type, scope_key, category)
            py_total = _month_total(py, scope_type, scope_key, category)

            feats = {
                "asof_day": asof,
                "last_day": last_day,
                "to_date": to_date,
                "avg_per_day": (to_date / max(asof, 1)),
                "remain_days": (last_day - asof),
                "prev_to_date": prev_to_date,
                "py_to_date": py_to_date,
                "prev_total": prev_total,
                "py_total": py_total,
            }

            p10, p50, p90 = predict_month_total(models, feats) if models else (None, None, None)

            # 4) 예측 저장 + 일별 분배 저장
            upsert_forecast(
                ym=ym, asof_day=asof, scope_type=scope_type, scope_key=scope_key, category=category,
                pred_total_p10=p10, pred_total_p50=p50, pred_total_p90=p90,
                model_ver="lgbm_v1",
            )
