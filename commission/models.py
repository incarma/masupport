# django_ma/commission/models.py
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import UniqueConstraint

# =============================================================================
# Deposit (채권현황)
# =============================================================================


class DepositSummary(models.Model):
    """
    사용자(사번) 단위의 채권 요약.

    - user는 OneToOne + primary_key이므로 row PK == user_id(사번 문자열)
    - 업로드 핸들러는 update_or_create(user_id=uid)를 SSOT로 사용
    """

    DIV_CHOICES = (
        ("", "-"),
        ("정상", "정상"),
        ("분급", "분급"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="deposit_summary",
        verbose_name="사번",
    )

    # -------------------------------------------------------------------------
    # 1) 기본/요약
    # -------------------------------------------------------------------------
    final_payment = models.BigIntegerField(default=0, verbose_name="최종지급액")
    sales_total = models.BigIntegerField(default=0, verbose_name="장기총실적")
    refund_expected = models.BigIntegerField(default=0, verbose_name="환수예상")
    pay_expected = models.BigIntegerField(default=0, verbose_name="지급예상")
    maint_total = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="손생합산통산",
    )

    debt_total = models.BigIntegerField(default=0, verbose_name="채권합계")
    surety_total = models.BigIntegerField(default=0, verbose_name="보증합계")
    other_total = models.BigIntegerField(default=0, verbose_name="기타합계")
    required_debt = models.BigIntegerField(default=0, verbose_name="필요채권")
    final_excess_amount = models.BigIntegerField(default=0, verbose_name="최종초과금액")

    # -------------------------------------------------------------------------
    # 2) 분급/계속분
    # -------------------------------------------------------------------------
    div_1m = models.CharField(max_length=10, blank=True, default="", choices=DIV_CHOICES, verbose_name="1개월전분급")
    div_2m = models.CharField(max_length=10, blank=True, default="", choices=DIV_CHOICES, verbose_name="2개월전분급")
    div_3m = models.CharField(max_length=10, blank=True, default="", choices=DIV_CHOICES, verbose_name="3개월전분급")
    inst_current = models.BigIntegerField(default=0, verbose_name="당월인정계속분")
    inst_prev = models.BigIntegerField(default=0, verbose_name="전월인정계속분")

    # -------------------------------------------------------------------------
    # 3) 일반 환수/지급
    # -------------------------------------------------------------------------
    refund_ns = models.BigIntegerField(default=0, verbose_name="환수손보")
    refund_ls = models.BigIntegerField(default=0, verbose_name="환수생보")
    pay_ns = models.BigIntegerField(default=0, verbose_name="지급손보")
    pay_ls = models.BigIntegerField(default=0, verbose_name="지급생보")

    # -------------------------------------------------------------------------
    # 4) 보증(O/X) 환수/지급
    # -------------------------------------------------------------------------
    surety_o_refund_ns = models.BigIntegerField(default=0, verbose_name="보증(O) 환수손보")
    surety_o_refund_ls = models.BigIntegerField(default=0, verbose_name="보증(O) 환수생보")
    surety_o_refund_total = models.BigIntegerField(default=0, verbose_name="보증(O) 환수합계")

    surety_x_refund_ns = models.BigIntegerField(default=0, verbose_name="보증(X) 환수손보")
    surety_x_refund_ls = models.BigIntegerField(default=0, verbose_name="보증(X) 환수생보")
    surety_x_refund_total = models.BigIntegerField(default=0, verbose_name="보증(X) 환수합계")

    surety_o_pay_ns = models.BigIntegerField(default=0, verbose_name="보증(O) 지급손보")
    surety_o_pay_ls = models.BigIntegerField(default=0, verbose_name="보증(O) 지급생보")
    surety_o_pay_total = models.BigIntegerField(default=0, verbose_name="보증(O) 지급합계")

    surety_x_pay_ns = models.BigIntegerField(default=0, verbose_name="보증(X) 지급손보")
    surety_x_pay_ls = models.BigIntegerField(default=0, verbose_name="보증(X) 지급생보")
    surety_x_pay_total = models.BigIntegerField(default=0, verbose_name="보증(X) 지급합계")

    # -------------------------------------------------------------------------
    # 5) 장기 총수수료
    # -------------------------------------------------------------------------
    comm_3m = models.BigIntegerField(default=0, verbose_name="3개월총수수료")
    comm_6m = models.BigIntegerField(default=0, verbose_name="6개월총수수료")
    comm_9m = models.BigIntegerField(default=0, verbose_name="9개월총수수료")
    comm_12m = models.BigIntegerField(default=0, verbose_name="12개월총수수료")

    # -------------------------------------------------------------------------
    # 6) 통산 회차/통산 유지(파일 기반 업로드)
    # -------------------------------------------------------------------------
    ns_13_round = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="13회손보회차")
    ns_18_round = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="18회손보회차")
    ls_13_round = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="13회생보회차")
    ls_18_round = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="18회생보회차")

    ns_18_total = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="18회손보통산")
    ns_25_total = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="25회손보통산")
    ls_18_total = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="18회생보통산")
    ls_25_total = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="25회생보통산")

    # -------------------------------------------------------------------------
    # 7) 응당(DF 업로드)
    # -------------------------------------------------------------------------
    ns_2_6_due = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="2-6회손보응당")
    ns_2_13_due = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="2-13회손보응당")
    ls_2_6_due = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="2-6회생보응당")
    ls_2_13_due = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="2-13회생보응당")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "deposit_summary"
        verbose_name = "채권 요약"
        verbose_name_plural = "채권 요약"

    def __str__(self) -> str:
        return f"DepositSummary({self.user_id})"


class DepositSurety(models.Model):
    """보증보험 상세(사용자 1:N)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="deposit_sureties",
        verbose_name="사번",
    )
    product_name = models.CharField(max_length=200, verbose_name="상품명")
    policy_no = models.CharField(max_length=100, blank=True, default="", verbose_name="증권번호")
    amount = models.BigIntegerField(default=0, verbose_name="가입금액")
    status = models.CharField(max_length=50, blank=True, default="", verbose_name="상태")
    start_date = models.DateField(null=True, blank=True, verbose_name="보험가입일")
    end_date = models.DateField(null=True, blank=True, verbose_name="보험종료일")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "deposit_surety"
        verbose_name = "보증보험"
        verbose_name_plural = "보증보험"

    def __str__(self) -> str:
        return f"DepositSurety({self.user_id}, {self.product_name})"


class DepositOther(models.Model):
    """기타채권 상세(사용자 1:N)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="deposit_others",
        verbose_name="사번",
    )
    product_name = models.CharField(max_length=200, verbose_name="상품명")
    product_type = models.CharField(max_length=200, blank=True, default="", verbose_name="보증내용")
    amount = models.BigIntegerField(default=0, verbose_name="가입금액")
    bond_no = models.CharField(max_length=100, blank=True, default="", verbose_name="채권번호")
    status = models.CharField(max_length=50, blank=True, default="", verbose_name="상태")
    start_date = models.DateField(null=True, blank=True, verbose_name="가입일")
    memo = models.CharField(max_length=255, blank=True, default="", verbose_name="비고")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "deposit_others"
        verbose_name = "기타채권"
        verbose_name_plural = "기타채권"

    def __str__(self) -> str:
        return f"DepositOther({self.user_id}, {self.product_name})"


class DepositUploadLog(models.Model):
    """Deposit 업로드 로그(part + upload_type unique)."""

    part = models.CharField(max_length=50, db_index=True, verbose_name="부서")
    upload_type = models.CharField(max_length=50, db_index=True, verbose_name="업로드 구분")
    uploaded_at = models.DateTimeField(auto_now=True, verbose_name="마지막 업로드 일시")

    row_count = models.IntegerField(default=0, verbose_name="행 수(추정)")
    file_name = models.CharField(max_length=255, blank=True, default="", verbose_name="파일명")

    class Meta:
        db_table = "deposit_upload_log"
        constraints = [
            UniqueConstraint(fields=["part", "upload_type"], name="uq_deposit_uploadlog_part_type"),
        ]

    def __str__(self) -> str:
        return f"{self.part}/{self.upload_type} ({self.uploaded_at:%Y-%m-%d})"


# =============================================================================
# Approval / Efficiency (수수료결재 / 지점효율)
# =============================================================================


class ApprovalExcelUploadLog(models.Model):
    """결재/효율 업로드 로그(월도 + 부서 + kind unique)."""

    KIND_EFFICIENCY = "efficiency"
    KIND_APPROVAL = "approval"

    KIND_CHOICES = (
        (KIND_EFFICIENCY, "지점효율"),
        (KIND_APPROVAL, "수수료결재"),
    )

    ym = models.CharField(max_length=7, db_index=True, verbose_name="월도(YYYY-MM)")
    part = models.CharField(max_length=50, blank=True, default="", db_index=True, verbose_name="부서")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, db_index=True, verbose_name="구분")

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_excel_upload_logs",
        verbose_name="업로드 사용자",
    )
    uploaded_at = models.DateTimeField(auto_now=True, verbose_name="업로드 일시")
    row_count = models.IntegerField(default=0, verbose_name="행 수(추정)")
    file_name = models.CharField(max_length=255, blank=True, default="", verbose_name="파일명")

    class Meta:
        db_table = "approval_excel_upload_log"
        verbose_name = "결재/효율 엑셀 업로드 로그"
        verbose_name_plural = "결재/효율 엑셀 업로드 로그"
        ordering = ["-uploaded_at"]
        constraints = [
            UniqueConstraint(fields=["ym", "part", "kind"], name="uq_approval_exceluploadlog_ym_part_kind"),
        ]

    def __str__(self) -> str:
        part_label = self.part or "전체"
        return f"{self.ym} / {part_label} / {self.kind} / {self.file_name}"


class ApprovalPending(models.Model):
    """수수료 미결 현황(월도 + 사용자 unique)."""

    ym = models.CharField(max_length=7, db_index=True, verbose_name="월도(YYYY-MM)")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="approval_pendings",
        verbose_name="사번",
    )
    emp_name = models.CharField(max_length=200, blank=True, default="", verbose_name="사원명(B열)")
    actual_pay = models.BigIntegerField(default=0, verbose_name="실지급액(N열)")
    approval_flag = models.CharField(max_length=20, blank=True, default="", verbose_name="결재(O열)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "approval_pending"
        verbose_name = "수수료 미결현황"
        verbose_name_plural = "수수료 미결현황"
        ordering = ["ym", "user_id"]
        constraints = [
            UniqueConstraint(fields=["ym", "user"], name="uq_approval_pending_ym_user"),
        ]

    def __str__(self) -> str:
        return f"{self.ym}/{self.user_id} ({self.emp_name})"


class EfficiencyPayExcess(models.Model):
    """지점효율 지급 초과 현황(월도 + 사용자 unique)."""

    ym = models.CharField(max_length=7, db_index=True, verbose_name="월도(YYYY-MM)")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="efficiency_pay_excesses",
        verbose_name="사번",
    )
    pay_amount_sum = models.BigIntegerField(default=0, verbose_name="지급금액합계")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "efficiency_pay_excess"
        verbose_name = "지점효율지급 초과현황"
        verbose_name_plural = "지점효율지급 초과현황"
        ordering = ["ym", "user_id"]
        constraints = [
            UniqueConstraint(fields=["ym", "user"], name="uq_efficiency_payexcess_ym_user"),
        ]

    def __str__(self) -> str:
        return f"{self.ym}/{self.user_id} ({self.pay_amount_sum})"