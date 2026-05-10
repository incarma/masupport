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
    
# =============================================================================
# Step 2: 환수관리 전용 모델 3개
# commission/models.py 최하단에 추가한다.
# (기존 모델 일절 수정 금지)
# =============================================================================

# =============================================================================
# CollectRecord — 환수관리 전용 데이터 (엑셀 36개 컬럼 전체 저장)
# =============================================================================
class CollectRecord(models.Model):
    """
    환수관리 전용 엑셀 업로드 데이터 테이블.

    [설계 원칙]
    - emp_id: FK 없이 CharField로 저장
      → CustomUser에 없는 사번도 저장 가능 (엑셀 원본 그대로 보존)
    - ym: "202603" (YYYYMM 6자리) 형식으로 저장
    - UniqueConstraint(emp_id, ym): 같은 사번+월도 재업로드 시 덮어쓰기
    - None → "" (str 필드) / 0 (int 필드) 정규화 후 저장
    - 탭 조건(final_payment < 0) 조회: Index(ym, part), Index(ym, bizmoon) 커버
    """

    # ── 월도 ──
    ym = models.CharField(
        max_length=6,
        db_index=True,
        verbose_name="월도",
        help_text="YYYYMM 형식 (예: 202603)",
    )

    # ── 조직 정보 ──
    bizmoon_total = models.CharField(max_length=100, blank=True, default="", verbose_name="부문총괄")
    bizmoon       = models.CharField(max_length=50,  blank=True, default="", verbose_name="부문")
    total         = models.CharField(max_length=50,  blank=True, default="", verbose_name="총괄")
    part          = models.CharField(max_length=50,  blank=True, default="", db_index=True, verbose_name="부서")
    branch        = models.CharField(max_length=100, blank=True, default="", verbose_name="영업가족")
    branch_code   = models.CharField(max_length=50,  blank=True, default="", verbose_name="영업가족코드")
    affiliation   = models.CharField(max_length=300, blank=True, default="", verbose_name="소속")

    # ── 개인 정보 ──
    regist_type = models.CharField(max_length=50,  blank=True, default="", verbose_name="등록구분")
    emp_name    = models.CharField(max_length=100, blank=True, default="", verbose_name="사원명")
    work_status = models.CharField(max_length=50,  blank=True, default="", verbose_name="재직(설계사)")
    enter_date  = models.DateField(null=True, blank=True, verbose_name="입사일")
    emp_id      = models.CharField(max_length=30,  db_index=True, verbose_name="사번")

    # ── 수수료 핵심 지표 ──
    final_payment = models.BigIntegerField(default=0, verbose_name="최종지급액")  # 음수 가능
    approval      = models.CharField(max_length=10,  blank=True, default="", verbose_name="결재")
    pay_flag      = models.CharField(max_length=10,  blank=True, default="", verbose_name="지급")

    # ── 채권/보증 ──
    surety_bond_total  = models.BigIntegerField(default=0, verbose_name="보증채권합계")
    surety_bond_detail = models.CharField(max_length=200, blank=True, default="", verbose_name="보증/채권")

    # ── 환수 관련 ──
    collect_action = models.CharField(max_length=200, blank=True, default="", verbose_name="환수조치")
    status         = models.CharField(max_length=100, blank=True, default="", verbose_name="상태")
    action_detail  = models.CharField(max_length=500, blank=True, default="", verbose_name="조치상세")

    # ── 수수료 세부 항목 ──
    car      = models.BigIntegerField(default=0, verbose_name="자동차")
    general  = models.BigIntegerField(default=0, verbose_name="일반")
    ns_init  = models.BigIntegerField(default=0, verbose_name="손보초회")
    ns_cont  = models.BigIntegerField(default=0, verbose_name="손보계속")
    ns_total = models.BigIntegerField(default=0, verbose_name="손보합계")
    ls_init  = models.BigIntegerField(default=0, verbose_name="생보초회")
    ls_cont  = models.BigIntegerField(default=0, verbose_name="생보계속")
    ls_total = models.BigIntegerField(default=0, verbose_name="생보합계")

    # ── 지급/공제 ──
    etc_pay   = models.BigIntegerField(default=0, verbose_name="기타지급")
    etc_deduct = models.BigIntegerField(default=0, verbose_name="기타공제")   # 음수 가능
    prepay    = models.BigIntegerField(default=0, verbose_name="선지급")
    first_pay = models.BigIntegerField(default=0, verbose_name="1차지급")
    tax       = models.BigIntegerField(default=0, verbose_name="세금")        # 음수 가능
    actual_pay  = models.BigIntegerField(default=0, verbose_name="실지급액")
    self_settle = models.BigIntegerField(default=0, verbose_name="자체정산")

    # ── 메타 ──
    uploaded_at = models.DateTimeField(auto_now=True, verbose_name="업로드일시")

    class Meta:
        db_table = "collect_record"
        verbose_name = "환수관리 레코드"
        verbose_name_plural = "환수관리 레코드"
        ordering = ["ym", "part", "emp_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["emp_id", "ym"],
                name="uq_collect_record_empid_ym",
            )
        ]
        indexes = [
            # 탭별 필터 조회 성능 (ym + 부서 / ym + 부문)
            models.Index(fields=["ym", "part"],    name="idx_collect_record_ym_part"),
            models.Index(fields=["ym", "bizmoon"], name="idx_collect_record_ym_bizmoon"),
        ]

    def __str__(self) -> str:
        return f"{self.emp_id} ({self.emp_name}) / {self.ym} / {self.final_payment:,}"


# =============================================================================
# CollectFeedback — 환수관리 피드백 (사번 기준, FK 없음)
# =============================================================================
class CollectFeedback(models.Model):
    """
    환수 대상자에 대한 운영 피드백(메모) 모델.

    [설계 원칙]
    - emp_id: FK 없이 CharField로 설계
      → CollectRecord에 없는 사번에도 피드백 입력 가능
      → 엑셀 업로드 전에도 피드백 미리 입력 가능
    - author: CustomUser FK — 작성자 추적 및 본인 여부 판정
    - 수정·삭제 권한: author(본인)만, 서비스 레이어에서 최종 판정
    - 소프트 삭제 미적용 → 하드 삭제
    """

    emp_id = models.CharField(
        max_length=30,
        db_index=True,
        verbose_name="대상자 사번",
        help_text="CollectRecord.emp_id와 동일 형식. FK 없이 독립 저장.",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,                       # 작성자 삭제 시 피드백 보존
        related_name="collect_feedbacks_written",
        verbose_name="작성자",
    )
    content    = models.TextField(verbose_name="피드백 내용")

    # ── 추가 메타 정보 (1번 요구사항) ──
    DEPARTMENT_CHOICES = [
        ("채권추심부", "채권추심부"),
        ("담당부서",   "담당부서"),
        ("영업지점",   "영업지점"),
    ]
    date_input  = models.DateField(
        null=True, blank=True, verbose_name="입력일",
        help_text="피드백 작성 기준일 (자동 입력일과 별개)"
    )
    department  = models.CharField(
        max_length=20, blank=True, default="",
        choices=DEPARTMENT_CHOICES, verbose_name="담당부서"
    )
    manager     = models.CharField(
        max_length=50, blank=True, default="", verbose_name="담당자"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="작성일시")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="수정일시")

    class Meta:
        db_table = "collect_feedback"
        verbose_name = "환수 피드백"
        verbose_name_plural = "환수 피드백"
        ordering = ["-created_at"]
        indexes = [
            # 특정 사번의 최신 피드백 조회 + Subquery 성능
            models.Index(
                fields=["emp_id", "-created_at"],
                name="idx_collect_feedback_empid_dt",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.emp_id}] by {self.author_id} @ {self.created_at:%Y-%m-%d}"


# =============================================================================
# CollectUploadLog — 환수관리 업로드 이력
# =============================================================================
class CollectUploadLog(models.Model):
    """
    환수관리 엑셀 업로드 이력 테이블.

    [설계 원칙]
    - ym 기준 UniqueConstraint: 월도당 1건 (update_or_create 방식)
    - 재업로드 시 uploaded_at, row_count, file_name이 갱신됨
    - uploaded_by: 업로드한 superuser 추적
    - collect_home.html 상단 업로드 현황 표시에 활용
    """

    ym = models.CharField(
        max_length=6,
        db_index=True,
        verbose_name="업로드 월도",
        help_text="YYYYMM 형식",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collect_upload_logs",
        verbose_name="업로드 사용자",
    )
    uploaded_at = models.DateTimeField(
        auto_now=True,
        verbose_name="업로드일시",
    )
    row_count = models.IntegerField(default=0, verbose_name="처리 행 수")
    file_name = models.CharField(max_length=255, blank=True, default="", verbose_name="원본 파일명")

    class Meta:
        db_table = "collect_upload_log"
        verbose_name = "환수관리 업로드 이력"
        verbose_name_plural = "환수관리 업로드 이력"
        ordering = ["-uploaded_at"]
        constraints = [
            # 월도당 1건만 유지 (재업로드 시 갱신)
            models.UniqueConstraint(
                fields=["ym"],
                name="uq_collect_uploadlog_ym",
            )
        ]

    def __str__(self) -> str:
        return f"{self.ym} / {self.file_name} / {self.row_count}건"
    

class CollectDropdownFeedback(models.Model):
    """
    환수관리 드랍다운 피드백 (영업가족/본사 구분).

    [설계 원칙]
    - feedback_type: 'branch'(영업가족, head/leader 작성)
                     'hq'(본사, superuser 작성)
    - 이력 누적: UniqueConstraint 없음 → 최신 1건을 서비스에서 Subquery로 조회
    - emp_id: FK 없이 CharField (CollectRecord.emp_id 규약과 동일)
    - author: PROTECT (작성자 삭제 시 이력 보존)
    - ym: CollectRecord.ym 규약과 동일 (YYYYMM 6자리)
    """

    FEEDBACK_TYPE_CHOICES = [
        ("branch", "영업가족 피드백"),
        ("hq",     "본사 피드백"),
    ]

    # 영업가족 피드백 선택지
    BRANCH_VALUE_CHOICES = [
        ("",               "선택"),
        ("입금예정",        "입금예정"),
        ("익월상계",        "익월상계"),
        ("상위차감",        "상위차감"),
        ("연락두절(추심요청)", "연락두절(추심요청)"),
        ("기타",           "기타"),
    ]

    # 본사 피드백 선택지
    HQ_VALUE_CHOICES = [
        ("",        "선택"),
        ("입금예정", "입금예정"),
        ("익월상계", "익월상계"),
        ("상위차감", "상위차감"),
        ("보증청구", "보증청구"),
        ("기타",    "기타"),
    ]

    emp_id        = models.CharField(max_length=30, db_index=True, verbose_name="대상자 사번")
    ym            = models.CharField(max_length=6,  db_index=True, verbose_name="월도(YYYYMM)")
    feedback_type = models.CharField(max_length=10, choices=FEEDBACK_TYPE_CHOICES, verbose_name="피드백 구분")
    value         = models.CharField(max_length=30, blank=True, default="", verbose_name="피드백 값")
    author        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="collect_dropdown_feedbacks",
        verbose_name="작성자",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="작성일시")

    class Meta:
        db_table  = "collect_dropdown_feedback"
        verbose_name        = "환수관리 드랍다운 피드백"
        verbose_name_plural = "환수관리 드랍다운 피드백"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["emp_id", "ym", "feedback_type"],
                name="idx_collect_df_empid_ym_type",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.feedback_type}] {self.emp_id} / {self.ym} / {self.value}"


# =============================================================================
# RateExample — 예시표 파일 메타 정보
# =============================================================================
class RateExample(models.Model):
    """
    예시표 파일 메타 정보.
    ⚠️ file.url 직접 노출 금지 — 반드시 rate_example_download 뷰 경유.
    """

    # ── 손생 구분 ────────────────────────────────────────────
    TYPE_LIFE    = "life"
    TYPE_NONLIFE = "nonlife"
    TYPE_CHOICES = [
        (TYPE_LIFE,    "생명보험"),
        (TYPE_NONLIFE, "손해보험"),
    ]

    # ── 구분 ─────────────────────────────────────────────────
    CAT_CONV = "conv"   # 환산율/수정률
    CAT_PAY  = "pay"    # 지급률
    CAT_CHOICES = [
        (CAT_CONV, "환산율/수정률"),
        (CAT_PAY,  "지급률"),
    ]

    # ── 보험사 허용 목록 ─────────────────────────────────────
    LIFE_INSURERS = [
        "ABL", "DB", "IM", "KB", "KDB", "교보", "농협", "동양",
        "라이나", "메트", "미래", "삼성", "신한", "처브",
        "카디프", "푸본현대", "하나", "한화", "흥국",
    ]
    NONLIFE_INSURERS = [
        "AIG", "DB", "KB", "농협", "롯데", "메리츠",
        "삼성", "한화", "현대", "흥국",
    ]

    # ── 허용 파일 형식 ────────────────────────────────────────
    ALLOWED_EXTENSIONS = {".pdf", ".xls", ".xlsx"}
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

    # ── 필드 ─────────────────────────────────────────────────
    insurer_type  = models.CharField(
        max_length=10, choices=TYPE_CHOICES, verbose_name="손생구분"
    )
    category      = models.CharField(
        max_length=10, choices=CAT_CHOICES, verbose_name="구분"
    )
    insurer       = models.CharField(max_length=30, verbose_name="보험사")
    file          = models.FileField(
        upload_to="commission/rate_examples/%Y/%m/",
        verbose_name="첨부파일",
    )
    original_name = models.CharField(
        max_length=255, blank=True, default="", verbose_name="원본파일명"
    )
    uploaded_by   = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="rate_examples_uploaded",
        verbose_name="업로더",
    )
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering     = ["-created_at"]
        verbose_name = "예시표"
        indexes      = [
            models.Index(fields=["insurer_type", "category", "insurer"]),
        ]

    def __str__(self):
        return (
            f"[{self.get_insurer_type_display()}]"
            f" {self.insurer} - {self.get_category_display()}"
        )
    

# =============================================================================
# RateExampleConversionRow — 예시표 환산율/수정률 정규화 테이블
# =============================================================================
class RateExampleConversionRow(models.Model):
    """
    예시표 환산율/수정률 정규화 행.

    [설계 원칙]
    - RateExample은 원본 파일 메타/다운로드용으로 유지한다.
    - 본 모델은 조회·계산용 정규화 master 역할을 담당한다.
    - 동일 보험사/손생구분/category는 최신 업로드 기준으로 교체된다.
    """

    source_file = models.ForeignKey(
        RateExample,
        on_delete=models.CASCADE,
        related_name="conversion_rows",
        verbose_name="원본 예시표 파일",
    )
    source_sheet = models.CharField(max_length=100, blank=True, default="", verbose_name="원본시트")
    source_row_no = models.PositiveIntegerField(default=0, verbose_name="원본행번호")

    insurer_type = models.CharField(max_length=10, db_index=True, verbose_name="손생구분")
    category = models.CharField(max_length=10, db_index=True, verbose_name="구분")
    insurer = models.CharField(max_length=30, db_index=True, verbose_name="보험사")

    coverage_type = models.CharField(max_length=50, blank=True, default="", verbose_name="보종")
    strategy_flag = models.CharField(max_length=30, blank=True, default="", verbose_name="전략유무")
    product_name = models.CharField(max_length=255, blank=True, default="", verbose_name="상품명")
    plan_type = models.CharField(max_length=100, blank=True, default="", verbose_name="구분")
    pay_period = models.CharField(max_length=50, blank=True, default="", verbose_name="납기")

    year1 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="1차년")
    year2 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="2차년")
    year3 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="3차년")
    year4 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="4차년")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["insurer_type", "insurer", "coverage_type", "product_name", "pay_period", "id"]
        verbose_name = "예시표 환산율/수정률 정규화 행"
        verbose_name_plural = "예시표 환산율/수정률 정규화 행"
        indexes = [
            models.Index(fields=["insurer_type", "category", "insurer"], name="idx_re_conv_scope"),
            models.Index(fields=["source_file", "source_sheet"], name="idx_re_conv_source"),
        ]

    def __str__(self) -> str:
        return f"{self.insurer}/{self.coverage_type}/{self.product_name}/{self.pay_period}"