# django_ma/commission/apps.py
from __future__ import annotations

from django.apps import AppConfig


class CommissionConfig(AppConfig):
    """
    Commission app config

    도메인:
    - Deposit: 채권현황 (DepositSummary / Surety / Other)
    - Approval: 수수료 결재/미결 (ApprovalPending)
    - Efficiency: 지점효율 지급 초과 (EfficiencyPayExcess)

    현재 signals 사용 없음.
    필요 시 ready()에서 signals import 패턴으로 확장 가능.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "commission"
    verbose_name = "Commission"

    # def ready(self) -> None:
    #     # signals.py가 생기면 여기서 import
    #     # from . import signals  # noqa
    #     return