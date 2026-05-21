# django_ma/commission/services/deposit_serializers.py
from __future__ import annotations

"""
Deposit API serializer SSOT.

역할:
- commission.views.api_deposit_impl 에 있던 payload 변환/응답 helper를 분리한다.
- View는 request 파싱, 권한 검증, service 호출만 담당한다.

주의:
- deposit_home.html / deposit_home.js 가 기대하는 응답 key 변경 금지.
- legacy 호환을 위해 user detail 응답은 data + user 키를 모두 유지한다.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.http import JsonResponse

from accounts.models import CustomUser
from commission.models import DepositOther, DepositSummary, DepositSurety
from commission.services.deposit import calc_filtered_totals, calc_keep_totals_all


def to_str(value: Any) -> str:
    return ("" if value is None else str(value)).strip()


def fmt_date(value: Any) -> str:
    try:
        return value.strftime("%Y-%m-%d") if value else "-"
    except Exception:
        return "-"


def to_iso(value: Any) -> str:
    try:
        return value.isoformat() if value else ""
    except Exception:
        return ""


def decimal_str(value: Any, default: str = "0.00") -> str:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return str(value)
    try:
        return str(Decimal(str(value)))
    except Exception:
        return default


def int0(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(Decimal(str(value)))
    except Exception:
        try:
            return int(value)
        except Exception:
            return 0


@dataclass(frozen=True)
class DepositTotalPayload:
    surety_total_all: int
    other_total_all: int
    surety_total: int
    other_total: int
    surety_keep_total: int
    other_keep_total: int

    @property
    def debt_keep_total(self) -> int:
        return self.surety_keep_total + self.other_keep_total

    def as_dict(self) -> dict[str, int]:
        return {
            "surety_total_all": self.surety_total_all,
            "other_total_all": self.other_total_all,
            "surety_total": self.surety_total,
            "other_total": self.other_total,
            "surety_keep_total": self.surety_keep_total,
            "other_keep_total": self.other_keep_total,
            "debt_keep_total": self.debt_keep_total,
        }


def json_rows(rows: list[dict[str, Any]]) -> JsonResponse:
    return JsonResponse({"ok": True, "rows": rows})


def json_user_detail(payload: dict[str, Any]) -> JsonResponse:
    return JsonResponse({"ok": True, "data": payload, "user": payload})


def user_to_payload(user: CustomUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name or "",
        "part": user.part or "",
        "branch": user.branch or "",
        "join_date_display": fmt_date(user.enter),
        "retire_date_display": fmt_date(user.quit),
        "enter": to_iso(user.enter),
        "quit": to_iso(user.quit),
    }


def summary_to_payload(summary: DepositSummary) -> dict[str, Any]:
    g = lambda k, default=None: getattr(summary, k, default)

    return {
        "final_payment": int0(g("final_payment")),
        "sales_total": int0(g("sales_total")),
        "refund_expected": int0(g("refund_expected")),
        "pay_expected": int0(g("pay_expected")),
        "maint_total": decimal_str(g("maint_total"), default="0.00"),

        "debt_total": int0(g("debt_total")),
        "surety_total": int0(g("surety_total")),
        "other_total": int0(g("other_total")),
        "required_debt": int0(g("required_debt")),
        "final_excess_amount": int0(g("final_excess_amount")),

        "div_1m": g("div_1m", "") or "",
        "div_2m": g("div_2m", "") or "",
        "div_3m": g("div_3m", "") or "",

        "inst_current": int0(g("inst_current")),
        "inst_prev": int0(g("inst_prev")),

        "refund_ns": int0(g("refund_ns")),
        "refund_ls": int0(g("refund_ls")),
        "pay_ns": int0(g("pay_ns")),
        "pay_ls": int0(g("pay_ls")),

        "surety_o_refund_ns": int0(g("surety_o_refund_ns")),
        "surety_o_refund_ls": int0(g("surety_o_refund_ls")),
        "surety_o_refund_total": int0(g("surety_o_refund_total")),
        "surety_o_pay_ns": int0(g("surety_o_pay_ns")),
        "surety_o_pay_ls": int0(g("surety_o_pay_ls")),
        "surety_o_pay_total": int0(g("surety_o_pay_total")),

        "surety_x_refund_ns": int0(g("surety_x_refund_ns")),
        "surety_x_refund_ls": int0(g("surety_x_refund_ls")),
        "surety_x_refund_total": int0(g("surety_x_refund_total")),
        "surety_x_pay_ns": int0(g("surety_x_pay_ns")),
        "surety_x_pay_ls": int0(g("surety_x_pay_ls")),
        "surety_x_pay_total": int0(g("surety_x_pay_total")),

        "comm_3m": int0(g("comm_3m")),
        "comm_6m": int0(g("comm_6m")),
        "comm_9m": int0(g("comm_9m")),
        "comm_12m": int0(g("comm_12m")),

        "ns_13_round": decimal_str(g("ns_13_round"), default="0.00"),
        "ns_18_round": decimal_str(g("ns_18_round"), default="0.00"),
        "ls_13_round": decimal_str(g("ls_13_round"), default="0.00"),
        "ls_18_round": decimal_str(g("ls_18_round"), default="0.00"),

        "ns_18_total": decimal_str(g("ns_18_total"), default="0.00"),
        "ns_25_total": decimal_str(g("ns_25_total"), default="0.00"),
        "ls_18_total": decimal_str(g("ls_18_total"), default="0.00"),
        "ls_25_total": decimal_str(g("ls_25_total"), default="0.00"),

        "ns_2_6_due": decimal_str(g("ns_2_6_due"), default="0.00"),
        "ns_2_13_due": decimal_str(g("ns_2_13_due"), default="0.00"),
        "ls_2_6_due": decimal_str(g("ls_2_6_due"), default="0.00"),
        "ls_2_13_due": decimal_str(g("ls_2_13_due"), default="0.00"),
    }


def surety_to_payload(item: DepositSurety) -> dict[str, Any]:
    return {
        "product_name": item.product_name or "",
        "policy_no": item.policy_no or "",
        "amount": item.amount or 0,
        "status": item.status or "",
        "start_date": fmt_date(item.start_date),
        "end_date": fmt_date(item.end_date),
    }


def other_to_payload(item: DepositOther) -> dict[str, Any]:
    return {
        "product_name": item.product_name or "",
        "product_type": item.product_type or "",
        "amount": item.amount or 0,
        "status": item.status or "",
        "bond_no": item.bond_no or "",
        "start_date": fmt_date(item.start_date),
        "memo": item.memo or "",
    }


def build_deposit_total_payload(
    *,
    summary_payload: dict[str, Any],
    user_pk: str,
) -> DepositTotalPayload:
    surety_filtered, other_filtered = calc_filtered_totals(user_pk)
    surety_keep_all, other_keep_all = calc_keep_totals_all(user_pk)

    return DepositTotalPayload(
        surety_total_all=int(summary_payload.get("surety_total", 0) or 0),
        other_total_all=int(summary_payload.get("other_total", 0) or 0),
        surety_total=int(surety_filtered or 0),
        other_total=int(other_filtered or 0),
        surety_keep_total=int(surety_keep_all or 0),
        other_keep_total=int(other_keep_all or 0),
    )


def apply_deposit_summary_totals(
    payload: dict[str, Any],
    user_pk: str,
) -> dict[str, Any]:
    totals = build_deposit_total_payload(
        summary_payload=payload,
        user_pk=user_pk,
    )
    payload.update(totals.as_dict())
    return payload


__all__ = [
    "to_str",
    "json_rows",
    "json_user_detail",
    "user_to_payload",
    "summary_to_payload",
    "surety_to_payload",
    "other_to_payload",
    "apply_deposit_summary_totals",
    "DepositTotalPayload",
]