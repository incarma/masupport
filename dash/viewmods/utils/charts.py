# django_ma/dash/viewmods/utils/charts.py
from __future__ import annotations

import calendar
from django.db.models import Sum
from django.db.models.functions import Coalesce


def month_day_labels(ym_str: str) -> list[str]:
    y_s, m_s = ym_str.split("-")
    y = int(y_s)
    m = int(m_s)
    last_day = calendar.monthrange(y, m)[1]
    return [f"{y:04d}-{m:02d}-{d:02d}" for d in range(1, last_day + 1)]


def daily_sum_map(qs) -> dict[str, int]:
    qs = qs.order_by().exclude(receipt_date__isnull=True)
    rows = (
        qs.values("receipt_date")
        .annotate(daily_sum=Sum(Coalesce("receipt_amount", 0)))
        .order_by("receipt_date")
    )
    out: dict[str, int] = {}
    for r in rows:
        d = r["receipt_date"]
        if not d:
            continue
        out[d.strftime("%Y-%m-%d")] = int(r["daily_sum"] or 0)
    return out


def build_cumsum_aligned(qs, labels: list[str]) -> list[int]:
    dm = daily_sum_map(qs)
    running = 0
    out: list[int] = []
    for day in labels:
        running += int(dm.get(day, 0))
        out.append(running)
    return out


def build_cumsum_prevmonth_aligned(qs_prev, current_labels: list[str], prev_ym_str: str) -> list[int]:
    py_s, pm_s = prev_ym_str.split("-")
    py = int(py_s)
    pm = int(pm_s)
    prev_last_day = calendar.monthrange(py, pm)[1]

    dm = daily_sum_map(qs_prev)
    running = 0
    out: list[int] = []

    for day_str in current_labels:
        d = int(day_str[-2:])
        if d <= prev_last_day:
            prev_day_str = f"{py:04d}-{pm:02d}-{d:02d}"
            running += int(dm.get(prev_day_str, 0))
            out.append(running)
        else:
            out.append(running)

    return out


def build_cumsum_othermonth_aligned(qs_other, current_labels: list[str], other_ym_str: str) -> list[int]:
    oy_s, om_s = other_ym_str.split("-")
    oy = int(oy_s)
    om = int(om_s)
    other_last_day = calendar.monthrange(oy, om)[1]

    dm = daily_sum_map(qs_other)
    running = 0
    out: list[int] = []

    for day_str in current_labels:
        d = int(day_str[-2:])
        if d <= other_last_day:
            other_day_str = f"{oy:04d}-{om:02d}-{d:02d}"
            running += int(dm.get(other_day_str, 0))
            out.append(running)
        else:
            out.append(running)

    return out


def nice_step_and_max(max_value: int) -> tuple[int, int]:
    mv = int(max_value or 0)
    if mv <= 0:
        return 1_000_000, 5_000_000

    target_ticks = 6
    raw_step = max(1, mv // target_ticks)

    pow10 = 10 ** max(0, len(str(raw_step)) - 1)
    candidates = [1 * pow10, 2 * pow10, 5 * pow10, 10 * pow10]

    step = candidates[-1]
    for c in candidates:
        if raw_step <= c:
            step = c
            break

    y_max = ((mv + step - 1) // step) * step
    return int(step), int(y_max)


def prev_ym_str(ym_str: str) -> str:
    y_s, m_s = ym_str.split("-")
    y = int(y_s)
    m = int(m_s)
    if m == 1:
        return f"{y-1:04d}-12"
    return f"{y:04d}-{m-1:02d}"


def prev_year_ym_str(ym_str: str) -> str:
    y_s, m_s = ym_str.split("-")
    y = int(y_s)
    m = int(m_s)
    return f"{y-1:04d}-{m:02d}"