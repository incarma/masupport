# django_ma/partner/models.py

from django.db import models
from accounts.models import CustomUser


class RateChange(models.Model):
    requester = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="ratechange_requests")
    target = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="ratechange_targets")

    part = models.CharField(max_length=50, default="-")
    branch = models.CharField(max_length=50, default="-")
    month = models.CharField(max_length=7, db_index=True)  # "YYYY-MM"

    before_ftable = models.CharField(max_length=100, blank=True, default="")
    before_frate = models.CharField(max_length=20, blank=True, default="")
    before_ltable = models.CharField(max_length=100, blank=True, default="")
    before_lrate = models.CharField(max_length=20, blank=True, default="")

    after_ftable = models.CharField(max_length=100, blank=True, default="")
    after_frate = models.CharField(max_length=20, blank=True, default="")
    after_ltable = models.CharField(max_length=100, blank=True, default="")
    after_lrate = models.CharField(max_length=20, blank=True, default="")

    memo = models.CharField(max_length=200, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    process_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["month", "branch"])]


# ------------------------------------------------------------
# 편제 변경 (조직 관리)
# ------------------------------------------------------------
class StructureChange(models.Model):
    requester = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="structure_requests", help_text="변경 요청자"
    )
    target = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="structure_targets", help_text="변경 대상자"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    part = models.CharField(max_length=50, blank=True, null=True, verbose_name="부서")
    branch = models.CharField(max_length=50, blank=True, null=True, help_text="요청자 소속")
    target_branch = models.CharField(max_length=50, blank=True, null=True, help_text="대상자 기존 소속")
    chg_branch = models.CharField(max_length=50, blank=True, null=True, help_text="변경 후 소속")

    rank = models.CharField(max_length=20, blank=True, null=True)
    chg_rank = models.CharField(max_length=20, blank=True, null=True)
    table_name = models.CharField(max_length=20, blank=True, null=True)
    chg_table = models.CharField(max_length=20, blank=True, null=True)

    rate = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    chg_rate = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    memo = models.CharField(max_length=100, blank=True, null=True)
    or_flag = models.BooleanField(default=False, help_text="OR 여부 플래그")

    month = models.CharField(max_length=7, help_text="YYYY-MM")
    request_date = models.DateTimeField(auto_now_add=True)
    process_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "편제변경 데이터"
        verbose_name_plural = "편제변경 데이터"
        ordering = ["-month", "-request_date"]

    def __str__(self):
        target_name = getattr(self.target, "name", "-")
        return f"{self.month} - {target_name}"


class PartnerChangeLog(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, help_text="작업자")
    action = models.CharField(max_length=50, help_text="수행된 작업 유형 (save/delete/set_deadline 등)")
    detail = models.TextField(blank=True, null=True, help_text="추가 상세 내역")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "편제변경 로그"
        verbose_name_plural = "편제변경 로그"
        ordering = ["-timestamp"]

    def __str__(self):
        user_name = getattr(self.user, "name", str(self.user))
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {user_name} - {self.action}"


class StructureDeadline(models.Model):
    branch = models.CharField(max_length=50)
    month = models.CharField(max_length=7, help_text="YYYY-MM")
    deadline_day = models.PositiveSmallIntegerField(help_text="마감 일자 (1~31)")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("branch", "month")
        verbose_name = "편제변경 마감일"
        verbose_name_plural = "편제변경 마감일"
        ordering = ["-month", "branch"]

    def __str__(self):
        return f"{self.branch} {self.month} ({self.deadline_day}일)"


class SubAdminTemp(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="subadmin_detail")

    name = models.CharField(max_length=50)
    part = models.CharField(max_length=50, blank=True, null=True)
    branch = models.CharField(max_length=50, blank=True, null=True)
    grade = models.CharField(max_length=20, blank=True, null=True)

    team_a = models.CharField(max_length=50, blank=True, null=True)
    team_b = models.CharField(max_length=50, blank=True, null=True)
    team_c = models.CharField(max_length=50, blank=True, null=True)
    position = models.CharField(max_length=30, blank=True, null=True)

    LEVEL_CHOICES = [
        ("-", "-"),
        ("A레벨", "A레벨"),
        ("B레벨", "B레벨"),
        ("C레벨", "C레벨"),
    ]
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default="-", verbose_name="레벨")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "partner_subadmin_temp"
        verbose_name = "권한관리 확장정보"
        verbose_name_plural = "권한관리 확장정보"

    def __str__(self):
        return f"{self.name} ({self.part})"


class TableSetting(models.Model):
    branch = models.CharField(max_length=100)
    table_name = models.CharField(max_length=100)
    rate = models.CharField(max_length=20, blank=True, null=True)
    order = models.PositiveIntegerField(default=0, help_text="표시 순서")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("branch", "table_name")
        ordering = ["branch", "table_name"]

    def __str__(self):
        return f"{self.branch} - {self.table_name}"


class RateTable(models.Model):
    user = models.OneToOneField(
        "accounts.CustomUser",
        on_delete=models.CASCADE,
        related_name="rate_table",
        verbose_name="사용자",
    )

    branch = models.CharField(max_length=50, blank=True, null=True, verbose_name="지점")
    team_a = models.CharField(max_length=50, blank=True, null=True, verbose_name="팀A")
    team_b = models.CharField(max_length=50, blank=True, null=True, verbose_name="팀B")
    team_c = models.CharField(max_length=50, blank=True, null=True, verbose_name="팀C")

    non_life_table = models.CharField(max_length=100, blank=True, null=True, verbose_name="손보 테이블명")
    life_table = models.CharField(max_length=100, blank=True, null=True, verbose_name="생보 테이블명")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "요율관리 테이블"
        verbose_name_plural = "요율관리 테이블"
        ordering = ["branch", "user__name"]

    def __str__(self):
        return f"{self.user.name} ({self.branch})"


# ------------------------------------------------------------
# ✅ 지점효율 확인서 업로드 그룹
# ------------------------------------------------------------
class EfficiencyConfirmGroup(models.Model):
    confirm_group_id = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="그룹ID")

    uploader = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="efficiency_confirm_groups",
        verbose_name="업로더",
    )

    part = models.CharField(max_length=50, default="-", verbose_name="부서")
    branch = models.CharField(max_length=50, default="-", verbose_name="지점")
    month = models.CharField(max_length=7, db_index=True, verbose_name="월(YYYY-MM)")

    title = models.CharField(max_length=120, blank=True, default="", verbose_name="그룹 제목")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="메모")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["month", "branch"])]
        verbose_name = "지점효율 확인서(그룹)"
        verbose_name_plural = "지점효율 확인서(그룹)"

    def __str__(self):
        return f"{self.month}/{self.branch} [{self.confirm_group_id}]"


# ------------------------------------------------------------
# ✅ 지점효율 확인서 첨부(파일) — 방향2 핵심: group FK + related_name="attachments"
# ------------------------------------------------------------
class EfficiencyConfirmAttachment(models.Model):
    group = models.ForeignKey(
        "partner.EfficiencyConfirmGroup",
        on_delete=models.CASCADE,
        related_name="attachments",
        null=True,      # ✅ 기존 데이터 백필 위해 1단계는 null 허용
        blank=True,
        verbose_name="확인서 그룹",
    )

    uploader = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="efficiency_confirm_uploads",
        verbose_name="업로더",
    )

    part = models.CharField(max_length=50, default="-", verbose_name="부서")
    branch = models.CharField(max_length=50, default="-", verbose_name="지점")
    month = models.CharField(max_length=7, db_index=True, verbose_name="월(YYYY-MM)")

    file = models.FileField(upload_to="partner/efficiency_confirm/%Y/%m/", verbose_name="확인서 파일")
    original_name = models.CharField(max_length=255, blank=True, default="", verbose_name="원본파일명")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["month", "branch"])]
        verbose_name = "지점효율 확인서(파일)"
        verbose_name_plural = "지점효율 확인서(파일)"

    def __str__(self):
        return f"{self.month} / {self.branch} / {self.original_name or (self.file.name if self.file else '-')}"


# ------------------------------------------------------------
# ✅ 지점효율(행) — 정식 연결: confirm_group
# ------------------------------------------------------------
class EfficiencyChange(models.Model):
    requester = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name="efficiency_requests")
    target = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="efficiency_targets")

    part = models.CharField(max_length=50, default="-")
    branch = models.CharField(max_length=50, default="-")
    month = models.CharField(max_length=7, db_index=True)  # "YYYY-MM"

    category = models.CharField(max_length=30, blank=True, default="")
    amount = models.PositiveIntegerField(null=True, blank=True)

    ded_name = models.CharField(max_length=50, blank=True, default="")
    ded_id = models.CharField(max_length=20, blank=True, default="")
    pay_name = models.CharField(max_length=50, blank=True, default="")
    pay_id = models.CharField(max_length=20, blank=True, default="")

    content = models.CharField(max_length=80, blank=True, default="")
    memo = models.CharField(max_length=200, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    process_date = models.DateField(null=True, blank=True)

    # ✅ 정식 연결 (Accordion/그룹 집계의 기준)
    confirm_group = models.ForeignKey(
        "partner.EfficiencyConfirmGroup",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="efficiency_rows",
        verbose_name="확인서 그룹",
    )

    # ✅ 레거시 호환 (백필 완료 후 제거 가능)
    confirm_attachment = models.ForeignKey(
        "partner.EfficiencyConfirmAttachment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="efficiency_rows_legacy",
        verbose_name="확인서(레거시)",
    )

    # 전자서명 연동 필드 (blank 허용 — 기존 저장 경로 영향 없음)
    start_ym = models.CharField(
        max_length=7, blank=True, default='',
        verbose_name='시작월도',  # "YYYY-MM"
    )
    end_ym = models.CharField(
        max_length=7, blank=True, default='',
        verbose_name='종료월도',  # "YYYY-MM"
    )

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["month", "branch"]),
            models.Index(fields=["confirm_group"]),
        ]

    def __str__(self):
        return f"{self.month} - {getattr(self.requester, 'name', '-')}"
    


# ============================================================
# 전자서명 시스템 — Phase 1 신규 모델
# 설계 기준: django_ma_esign_final_design.md v2.0
# ============================================================

class EfficiencySignRequest(models.Model):
    """
    지점효율 사실확인서 전자서명 요청 단위.
    EfficiencyConfirmGroup 1개당 1:1 대응.

    ⚠️ pdf_file.url 직접 노출 절대 금지.
       반드시 esign_pdf_download 뷰에서 FileResponse로만 제공.
    """

    STATUS_PENDING   = 'pending'
    STATUS_PARTIAL   = 'partial'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING,   '서명 대기'),
        (STATUS_PARTIAL,   '일부 서명'),
        (STATUS_COMPLETED, '서명 완료'),
        (STATUS_CANCELLED, '취소'),
    ]

    confirm_group = models.OneToOneField(
        'partner.EfficiencyConfirmGroup',
        on_delete=models.CASCADE,
        related_name='sign_request',
        null=True,
        blank=True,
    )

    ym         = models.CharField(max_length=7, verbose_name='월도')       # "YYYY-MM"
    branch     = models.CharField(max_length=50, default='-', verbose_name='지점')
    created_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.PROTECT,
        related_name='esign_requests_created',
        verbose_name='생성자',
    )

    # 완성 PDF — 서명 완료 시에만 생성
    doc_hash = models.CharField(
        max_length=64, blank=True, default='',
        verbose_name='PDF SHA-256',
    )
    pdf_file = models.FileField(
        upload_to='esign/completed/',
        null=True, blank=True,
        verbose_name='완성 PDF',
    )

    status     = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_PENDING, verbose_name='서명 상태',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '전자서명 요청'
        verbose_name_plural = '전자서명 요청 목록'
        indexes = [
            models.Index(fields=['ym', 'branch']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.ym}/{self.branch} [{self.get_status_display()}]"

    @property
    def is_pending(self):
        return self.status == self.STATUS_PENDING

    @property
    def is_completed(self):
        return self.status == self.STATUS_COMPLETED


class EfficiencyConfirmSign(models.Model):
    """
    서명 요청 내 개별 참여자 서명 상태 — 감사추적 핵심 테이블.

    role:
      'deduct'       → 공제대상자 (ded_id 기준 자동 등록)
      'pay'          → 지급대상자 (pay_id 기준 자동 등록)
      'head_confirm' → 최고관리자 확인 (branch head 자동 등록)
    """

    ROLE_DEDUCT       = 'deduct'
    ROLE_PAY          = 'pay'
    ROLE_HEAD_CONFIRM = 'head_confirm'

    ROLE_CHOICES = [
        (ROLE_DEDUCT,       '공제대상자'),
        (ROLE_PAY,          '지급대상자'),
        (ROLE_HEAD_CONFIRM, '최고관리자 확인'),
    ]

    request = models.ForeignKey(
        EfficiencySignRequest,
        on_delete=models.CASCADE,
        related_name='signs',
        verbose_name='서명 요청',
    )
    signer = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.PROTECT,
        related_name='esign_participations',
        verbose_name='서명자',
    )
    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES,
        verbose_name='역할',
    )

    # ── 서명 감사추적 ────────────────────────────────────────────
    # ⚠️ 민감 개인정보(전화번호·CI 등) 절대 저장 금지
    signed_at   = models.DateTimeField(null=True, blank=True, verbose_name='서명일시')
    ip_address  = models.GenericIPAddressField(null=True, blank=True, verbose_name='서명 IP')
    user_agent  = models.TextField(blank=True, default='', verbose_name='User-Agent')
    session_key = models.CharField(
        max_length=40, blank=True, default='',
        verbose_name='세션 키 스냅샷',
    )

    # 서명 당시 PASS 인증 상태 스냅샷 (Phase 2 연동 전까지 null)
    pass_verified_at_sign = models.DateTimeField(
        null=True, blank=True,
        verbose_name='PASS 인증일시 스냅샷',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('request', 'signer')
        verbose_name = '서명 참여자'
        verbose_name_plural = '서명 참여자 목록'
        ordering = ['created_at']

    def __str__(self):
        return (
            f"{self.request_id} - {self.signer_id}"
            f" ({self.get_role_display()})"
            f" {'✅' if self.signed_at else '⏳'}"
        )

    @property
    def is_signed(self):
        return self.signed_at is not None