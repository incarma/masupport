# django_ma/dash/services/retention.py
from __future__ import annotations

import logging
import re
from decimal import Decimal

import pandas as pd
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.db.models.functions import Coalesce

from accounts.models import CustomUser
from dash.models import RetentionRecord, RetentionAgg

logger = logging.getLogger(__name__)


def _float_rate(rate) -> float | None:
    if rate is None:
        return None
    try:
        return float(rate)
    except (TypeError, ValueError):
        return None

# ── 유지율 분자 상태 ─────────────────────────────────────────
NUMERATOR_STATUSES = {"정상", "유예"}

# ── 엑셀 컬럼 SSOT ───────────────────────────────────────────
REQUIRED_COLS = [
    "증권번호", "보험사", "상품명",
    "최초(모집)인정실적", "대상회차", "최종월도", "상태",
    "소속", "파트너", "모집자", "모집자코드",
]


def _norm_ym(raw) -> str | None:
    """최종월도(YYYYMM 또는 int) → 'YYYY-MM'"""
    s = str(int(raw)).strip() if isinstance(raw, float) else str(raw).strip()
    s = re.sub(r"[^0-9]", "", s)
    if len(s) == 6:
        return f"{s[:4]}-{s[4:6]}"
    return None


def _norm_str(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _norm_round(v) -> int | None:
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _norm_amount(v) -> int:
    try:
        s = str(v).replace(",", "").strip()
        return max(0, int(float(s)))
    except (ValueError, TypeError):
        return 0


def _norm_emp_id(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s or None


def _detect_life_nl(df: pd.DataFrame) -> str:
    """
    생보/손보 자동 감지:
    - 보험사 컬럼의 값을 constants의 LIFE_INSURERS로 판별
    - 생보 비율 > 60% → 생보, 아니면 손보
    """
    from dash.viewmods.constants import LIFE_INSURERS
    sample = df["보험사"].dropna().head(200)
    life_cnt = sum(1 for v in sample if str(v).strip() in LIFE_INSURERS)
    return "생보" if life_cnt / max(len(sample), 1) > 0.5 else "손보"


def parse_retention_excel(df: pd.DataFrame, life_nl: str) -> tuple[list[dict], list[str]]:
    """
    DataFrame → RetentionRecord upsert용 dict 목록 반환
    returns: (records, errors)
    """
    # 컬럼 정규화
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        return [], [f"필수 컬럼 누락: {missing}"]

    records = []
    errors = []

    for idx, row in df.iterrows():
        try:
            policy_no = _norm_str(row.get("증권번호"))
            if not policy_no:
                continue

            round_no = _norm_round(row.get("대상회차"))
            if round_no is None:
                continue

            ym = _norm_ym(row.get("최종월도"))
            if not ym:
                continue

            insurer = _norm_str(row.get("보험사"))
            status  = _norm_str(row.get("상태"))
            recruit = _norm_amount(row.get("최초(모집)인정실적"))

            emp_id  = _norm_emp_id(row.get("모집자코드"))
            name    = _norm_str(row.get("모집자")) or None
            part    = _norm_str(row.get("소속"))   or None
            branch  = _norm_str(row.get("파트너")) or None
            product = _norm_str(row.get("상품명")) or None

            records.append({
                "policy_no":      policy_no,
                "round_no":       round_no,
                "insurer":        insurer,
                "product_name":   product,
                "life_nl":        life_nl,
                "recruit_amount": recruit,
                "status":         status,
                "ym":             ym,
                "emp_id_snapshot": emp_id,
                "name_snapshot":  name,
                "part_snapshot":  part,
                "branch_snapshot": branch,
            })
        except Exception as e:  # 행별 파싱 — 예외 종류 불특정
            errors.append(f"row={idx}: {e}")

    return records, errors


@transaction.atomic
def bulk_upsert_retention_records(records: list[dict]) -> tuple[int, int]:
    """
    records → RetentionRecord bulk upsert
    returns: (upserted, skipped)
    """
    if not records:
        return 0, 0

    # 설계사 사번 → User 캐시
    emp_ids = {r["emp_id_snapshot"] for r in records if r.get("emp_id_snapshot")}
    user_map: dict[str, int] = {
        str(u.id): u.pk
        for u in CustomUser.objects.filter(id__in=emp_ids)
    }

    upserted = skipped = 0

    for r in records:
        try:
            user_id = user_map.get(r.get("emp_id_snapshot") or "") or None
            RetentionRecord.objects.update_or_create(
                policy_no=r["policy_no"],
                round_no=r["round_no"],
                defaults={
                    "insurer":        r["insurer"],
                    "product_name":   r.get("product_name"),
                    "life_nl":        r["life_nl"],
                    "recruit_amount": r["recruit_amount"],
                    "status":         r["status"],
                    "ym":             r["ym"],
                    "user_id":        user_id,
                    "emp_id_snapshot": r.get("emp_id_snapshot"),
                    "name_snapshot":  r.get("name_snapshot"),
                    "part_snapshot":  r.get("part_snapshot"),
                    "branch_snapshot": r.get("branch_snapshot"),
                },
            )
            upserted += 1
        except Exception as e:  # DB 제약 위반 등 예외 종류 불특정
            logger.exception("retention upsert failed: %s", e)
            skipped += 1

    return upserted, skipped


def _scope_filter_retention(scope_type: str, scope_key: str):
    """RetentionRecord용 scope 필터 (agg.py의 _scope_filter와 동일 패턴)"""
    from django.db.models import Q
    scope_key = (scope_key or "").strip()
    if scope_type == "all":
        return Q()
    if not scope_key:
        return Q(pk__isnull=True)
    if scope_type == "part":
        return Q(user__isnull=False, user__part=scope_key) | Q(part_snapshot=scope_key)
    if scope_type == "branch":
        return Q(user__isnull=False, user__branch=scope_key) | Q(branch_snapshot=scope_key)
    return Q()


@transaction.atomic
def rebuild_retention_agg(ym: str, life_nl: str = "") -> int:
    """
    ym 전체(또는 life_nl 지정) RetentionAgg를 재계산
    returns: upserted count
    """
    from accounts.models import CustomUser
    from dash.models import SalesRecord  # scope 목록 재사용

    # 집계 대상 scope 목록 (iter_scopes 패턴 그대로)
    scopes: list[tuple[str, str]] = [("all", "*")]

    user_parts = list(
        CustomUser.objects.exclude(part__isnull=True).exclude(part="")
        .values_list("part", flat=True).distinct()
    )
    snap_parts = list(
        RetentionRecord.objects.filter(ym=ym)
        .exclude(part_snapshot__isnull=True).exclude(part_snapshot="")
        .values_list("part_snapshot", flat=True).distinct()
    )
    for p in sorted({str(v).strip() for v in user_parts + snap_parts if str(v).strip()}):
        scopes.append(("part", p))

    user_branches = list(
        CustomUser.objects.exclude(branch__isnull=True).exclude(branch="")
        .values_list("branch", flat=True).distinct()
    )
    snap_branches = list(
        RetentionRecord.objects.filter(ym=ym)
        .exclude(branch_snapshot__isnull=True).exclude(branch_snapshot="")
        .values_list("branch_snapshot", flat=True).distinct()
    )
    for b in sorted({str(v).strip() for v in user_branches + snap_branches if str(v).strip()}):
        scopes.append(("branch", b))

    base_qs = RetentionRecord.objects.filter(ym=ym)
    if life_nl:
        base_qs = base_qs.filter(life_nl=life_nl)

    # 존재하는 회차 목록
    round_list = list(
        base_qs.values_list("round_no", flat=True).distinct().order_by("round_no")
    )
    # 존재하는 보험사 목록 + "" (전체)
    insurer_list = [""] + sorted(
        base_qs.exclude(insurer="").values_list("insurer", flat=True).distinct()
    )

    life_nl_list = [life_nl] if life_nl else ["생보", "손보", ""]

    upserted = 0
    for ln in life_nl_list:
        qs_ln = base_qs.filter(life_nl=ln) if ln else base_qs
        for scope_type, scope_key in scopes:
            qs_scope = qs_ln.filter(_scope_filter_retention(scope_type, scope_key))
            for rnd in round_list:
                qs_rnd = qs_scope.filter(round_no=rnd)
                for ins in insurer_list:
                    qs_ins = qs_rnd.filter(insurer=ins) if ins else qs_rnd
                    total_amount = qs_ins.aggregate(s=Sum("recruit_amount"))["s"] or 0
                    paid_amount  = qs_ins.filter(
                        status__in=list(NUMERATOR_STATUSES)
                    ).aggregate(s=Sum("recruit_amount"))["s"] or 0
                    total_count  = qs_ins.count()
                    paid_count   = qs_ins.filter(status__in=list(NUMERATOR_STATUSES)).count()
                    rate = Decimal(str(round(paid_amount / total_amount * 100, 2))) \
                        if total_amount > 0 else Decimal("0")

                    RetentionAgg.objects.update_or_create(
                        ym=ym, life_nl=ln, round_no=rnd,
                        scope_type=scope_type, scope_key=scope_key, insurer=ins,
                        defaults={
                            "total_amount": total_amount,
                            "paid_amount":  paid_amount,
                            "total_count":  total_count,
                            "paid_count":   paid_count,
                            "rate":         rate,
                        },
                    )
                    upserted += 1

    logger.info("[retention.agg] rebuild done ym=%s life_nl=%s upserted=%s", ym, life_nl, upserted)
    return upserted


def get_retention_api_payload(
    ym: str,
    life_nl: str,
    scope_type: str,
    scope_key: str,
    q: str,
) -> dict:
    """
    유지율 API 응답 payload 조립.
    뷰에서 캐시 확인 후 cache miss 시에만 호출한다.
    """
    effective_key = scope_key if scope_type != "all" else "*"

    # ── 집계 데이터 ───────────────────────────────────────────
    agg_qs = RetentionAgg.objects.filter(
        ym=ym, scope_type=scope_type, scope_key=effective_key,
    )
    if life_nl:
        agg_qs = agg_qs.filter(life_nl=life_nl)

    rounds = sorted(
        agg_qs.filter(insurer="").values_list("round_no", flat=True).distinct()
    )

    # summary (insurer="" = 전체)
    summary: dict = {}
    for rnd in rounds:
        row = agg_qs.filter(round_no=rnd, insurer="").first()
        if row:
            summary[rnd] = {
                "total_amount": row.total_amount,
                "paid_amount":  row.paid_amount,
                "total_count":  row.total_count,
                "paid_count":   row.paid_count,
                "rate":         _float_rate(row.rate),
            }

    # trend (최근 6개월)
    y_int, m_int = map(int, ym.split("-"))
    trend_labels = []
    for i in range(5, -1, -1):
        mm = m_int - i
        yy = y_int
        while mm <= 0:
            mm += 12
            yy -= 1
        trend_labels.append(f"{yy:04d}-{mm:02d}")

    trend_by_round: dict[int, list] = {rnd: [] for rnd in rounds}
    for label in trend_labels:
        for rnd in rounds:
            t_agg = RetentionAgg.objects.filter(
                ym=label,
                life_nl=life_nl or "",
                round_no=rnd,
                scope_type=scope_type,
                scope_key=effective_key,
                insurer="",
            ).first()
            trend_by_round[rnd].append(_float_rate(t_agg.rate) if t_agg else None)

    # by_insurer
    insurer_rows_qs = agg_qs.exclude(insurer="")
    if q:
        insurer_rows_qs = insurer_rows_qs.filter(insurer__icontains=q)

    insurer_map: dict[str, dict] = {}
    for row in insurer_rows_qs:
        key = row.insurer
        if key not in insurer_map:
            insurer_map[key] = {"insurer": key, "rounds": {}, "total_count": 0}
        insurer_map[key]["rounds"][row.round_no] = _float_rate(row.rate)
        insurer_map[key]["total_count"] = max(
            insurer_map[key]["total_count"], row.total_count
        )
    by_insurer = sorted(insurer_map.values(), key=lambda x: -x["total_count"])[:20]

    # by_planner (설계사별 — 집계 테이블에 설계사 차원 없으므로 record 직접 집계)
    rec_qs = RetentionRecord.objects.filter(ym=ym)
    if life_nl:
        rec_qs = rec_qs.filter(life_nl=life_nl)
    rec_qs = rec_qs.filter(_scope_filter_retention(scope_type, effective_key))
    if q:
        rec_qs = rec_qs.filter(
            Q(name_snapshot__icontains=q)
            | Q(emp_id_snapshot__icontains=q)
            | Q(insurer__icontains=q)
            | Q(product_name__icontains=q)
        )

    planner_map: dict[str, dict] = {}
    for rnd in rounds:
        rows = (
            rec_qs.filter(round_no=rnd)
            .values("emp_id_snapshot", "name_snapshot", "part_snapshot", "branch_snapshot")
            .annotate(
                total=Sum("recruit_amount"),
                paid=Sum("recruit_amount", filter=Q(status__in=["정상", "유예"])),
                cnt=Count("policy_no"),
            )
            .order_by("-total")[:20]
        )
        for row in rows:
            key = row["emp_id_snapshot"] or row["name_snapshot"] or ""
            if not key:
                continue
            if key not in planner_map:
                planner_map[key] = {
                    "emp_id":      row["emp_id_snapshot"],
                    "name":        row["name_snapshot"],
                    "part":        row["part_snapshot"],
                    "branch":      row["branch_snapshot"],
                    "rounds":      {},
                    "total_count": 0,
                }
            total = row["total"] or 0
            paid  = row["paid"]  or 0
            rate  = round(paid / total * 100, 2) if total > 0 else None
            planner_map[key]["rounds"][rnd]    = rate
            planner_map[key]["total_count"]   += row["cnt"] or 0

    by_planner = sorted(planner_map.values(), key=lambda x: -x["total_count"])[:20]

    return {
        "ym":         ym,
        "life_nl":    life_nl,
        "scope_type": scope_type,
        "scope_key":  scope_key,
        "rounds":     rounds,
        "summary":    summary,
        "trend": {
            "labels":   trend_labels,
            "by_round": {str(k): v for k, v in trend_by_round.items()},
        },
        "by_insurer": by_insurer,
        "by_planner": by_planner,
    }