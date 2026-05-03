# django_ma/board/models.py

import mimetypes
import os

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.conf import settings

from .constants import STATUS_CHOICES_TUPLES


# =========================================================
# Choices
# =========================================================
TASK_STATUS_CHOICES = [
    ("시작전", "시작전"),
    ("진행중", "진행중"),
    ("보완필요", "보완필요"),
    ("완료", "완료"),
]


# =========================================================
# Post (업무요청)
# =========================================================
class Post(models.Model):
    """
    업무요청 게시글
    - 접수번호: YYYYMMDD### 자동 생성
    - status/handler 변경 시 status_updated_at 갱신
    """

    # 기본 정보
    receipt_number = models.CharField("접수번호", max_length=20, unique=True, blank=True)
    category = models.CharField("구분", max_length=10, blank=True, default="")
    fa = models.CharField("성명(대상자)", max_length=20, blank=True, default="")
    code = models.IntegerField(
        "사번(대상자)",
        validators=[MinValueValidator(1600000), MaxValueValidator(3000000)],
        null=True,
        blank=True,
    )

    # 본문
    title = models.CharField("제목", max_length=200)
    content = models.TextField("요청 내용")

    # 작성자 정보(스냅샷)
    user_id = models.CharField("사번(요청자)", max_length=30, blank=True)
    user_name = models.CharField("성명(요청자)", max_length=100, blank=True)
    user_branch = models.CharField("소속(요청자)", max_length=100, blank=True)

    created_at = models.DateTimeField("최초등록일", auto_now_add=True)

    # 담당자/상태
    handler = models.CharField("담당자", max_length=100, blank=True, default="")

    status = models.CharField("상태", max_length=20, choices=STATUS_CHOICES_TUPLES, default="확인중")
    status_updated_at = models.DateTimeField("상태변경일", blank=True, null=True)

    def save(self, *args, **kwargs):
        """
        - receipt_number 자동 생성
        - status/handler 변경 시 status_updated_at 갱신
        - update_fields 사용 시 status_updated_at 누락 방지
        """
        now = timezone.localtime()  # 표시/문자열용
        now_dt = timezone.now()     # 저장용(UTC-aware)
        update_fields = kwargs.get("update_fields")

        # None 방어
        if self.handler is None:
            self.handler = ""

        # 접수번호 자동 생성 (동시성 충돌 시 재시도)
        if not self.receipt_number:
            today = timezone.localdate()
            today_str = today.strftime("%Y%m%d")
            for _ in range(5):
                last = (
                    Post.objects.filter(created_at__date=today, receipt_number__startswith=today_str)
                    .order_by("-receipt_number")
                    .values_list("receipt_number", flat=True)
                    .first()
                )
                seq = int(last[-3:]) + 1 if (last and len(last) >= 11) else 1
                self.receipt_number = f"{today_str}{seq:03d}"
                try:
                    with transaction.atomic():
                        break
                except IntegrityError:
                        self.receipt_number = ""
            if not self.receipt_number:
                raise IntegrityError("Failed to generate unique receipt_number for Post")

        # 상태변경일 갱신 여부 판단
        touch = False
        if self.pk:
            prev = Post.objects.filter(pk=self.pk).only("status", "handler").first()
            if prev and (prev.status != self.status or prev.handler != self.handler):
                touch = True
        else:
            touch = True

        if touch:
            self.status_updated_at = timezone.localtime(now_dt)
            if update_fields is not None:
                uf = set(update_fields)
                uf.add("status_updated_at")
                if not self.pk:
                    uf.add("receipt_number")
                kwargs["update_fields"] = list(uf)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.receipt_number}] {self.title}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "업무요청 게시글"
        verbose_name_plural = "업무요청 게시글 목록"


# =========================================================
# Task (직원업무) - superuser만 접근(권한은 views에서)
# =========================================================
class Task(models.Model):
    """
    직원업무 게시글
    - 접수번호: YYYYMMDD### 자동 생성
    - status/handler 변경 시 status_updated_at 갱신
    """

    receipt_number = models.CharField("접수번호", max_length=20, unique=True, blank=True)
    category = models.CharField("구분", max_length=10, blank=True, default="")

    title = models.CharField("제목", max_length=200)
    content = models.TextField("요청 내용")

    user_id = models.CharField("사번(요청자)", max_length=30, blank=True, default="")
    user_name = models.CharField("성명(요청자)", max_length=100, blank=True, default="")
    user_branch = models.CharField("소속(요청자)", max_length=100, blank=True, default="")

    created_at = models.DateTimeField("최초등록일", auto_now_add=True)

    handler = models.CharField("담당자", max_length=100, blank=True, default="")
    status = models.CharField("상태", max_length=20, choices=TASK_STATUS_CHOICES, default="시작전")
    status_updated_at = models.DateTimeField("상태변경일", blank=True, null=True)

    def save(self, *args, **kwargs):
        now = timezone.localtime()
        now_dt = timezone.now()
        update_fields = kwargs.get("update_fields")

        # None 방어
        self.user_id = self.user_id or ""
        self.user_name = self.user_name or ""
        self.user_branch = self.user_branch or ""
        self.handler = self.handler or ""

        # 접수번호 생성
        if not self.receipt_number:
            today = timezone.localdate()
            today_str = today.strftime("%Y%m%d")
            for _ in range(5):
                last = (
                    Task.objects.filter(created_at__date=today, receipt_number__startswith=today_str)
                    .order_by("-receipt_number")
                    .values_list("receipt_number", flat=True)
                    .first()
                )
                seq = int(last[-3:]) + 1 if (last and len(last) >= 11) else 1
                self.receipt_number = f"{today_str}{seq:03d}"
                try:
                    with transaction.atomic():
                        break
                except IntegrityError:
                    self.receipt_number = ""
            if not self.receipt_number:
                raise IntegrityError("Failed to generate unique receipt_number for Task")

        # 상태변경일 갱신 여부 판단
        touch = False
        if self.pk:
            prev = Task.objects.filter(pk=self.pk).only("status", "handler").first()
            if prev and (prev.status != self.status or prev.handler != self.handler):
                touch = True
        else:
            touch = True

        if touch:
            self.status_updated_at = timezone.localtime(now_dt)
            if update_fields is not None:
                uf = set(update_fields)
                uf.add("status_updated_at")
                if not self.pk:
                    uf.add("receipt_number")
                kwargs["update_fields"] = list(uf)

        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "직원업무 게시글"
        verbose_name_plural = "직원업무 게시글 목록"


# =========================================================
# Attachments / Comments
# =========================================================
def attachment_upload_to(instance, filename):
    return f"attachments/{timezone.now():%Y/%m/%d}/{filename}"


class Attachment(models.Model):
    post = models.ForeignKey(Post, related_name="attachments", on_delete=models.CASCADE)
    file = models.FileField(upload_to=attachment_upload_to)

    original_name = models.CharField("원본 파일명", max_length=255, blank=True)
    size = models.PositiveBigIntegerField("파일 크기", default=0)
    content_type = models.CharField("MIME 타입", max_length=120, blank=True)
    uploaded_at = models.DateTimeField("업로드일", auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.file:
            raw = getattr(self.file, "name", self.original_name)
            self.original_name = os.path.basename(raw or "")
            self.size = getattr(self.file, "size", self.size)
            if not self.content_type:
                guessed, _ = mimetypes.guess_type(self.original_name or "")
                self.content_type = guessed or "application/octet-stream"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_name or getattr(self.file, "name", "")

    class Meta:
        verbose_name = "첨부파일"
        verbose_name_plural = "첨부파일 목록"


class Comment(models.Model):
    post = models.ForeignKey(Post, related_name="comments", on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField("댓글 내용", max_length=500)
    created_at = models.DateTimeField("작성일시", auto_now_add=True)

    def __str__(self):
        return f"{self.author} - {self.content[:20]}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "댓글"
        verbose_name_plural = "댓글 목록"


# ----------------- Task Attachments / Comments -----------------
def task_attachment_upload_to(instance, filename):
    return f"task_attachments/{timezone.now():%Y/%m/%d}/{filename}"


class TaskAttachment(models.Model):
    task = models.ForeignKey(Task, related_name="attachments", on_delete=models.CASCADE)
    file = models.FileField(upload_to=task_attachment_upload_to)

    original_name = models.CharField("원본 파일명", max_length=255, blank=True)
    size = models.PositiveBigIntegerField("파일 크기", default=0)
    content_type = models.CharField("MIME 타입", max_length=120, blank=True)
    uploaded_at = models.DateTimeField("업로드일", auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.file:
            raw = getattr(self.file, "name", self.original_name)
            self.original_name = os.path.basename(raw or "")
            self.size = getattr(self.file, "size", self.size)
            if not self.content_type:
                guessed, _ = mimetypes.guess_type(self.original_name or "")
                self.content_type = guessed or "application/octet-stream"
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "직원업무 첨부파일"
        verbose_name_plural = "직원업무 첨부파일 목록"


class TaskComment(models.Model):
    task = models.ForeignKey(Task, related_name="comments", on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField("댓글 내용", max_length=500)
    created_at = models.DateTimeField("작성일시", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "직원업무 댓글"
        verbose_name_plural = "직원업무 댓글 목록"


class CollateralEval(models.Model):
    """
    담보평가 이력 모델
    - 플래너(requester)가 고객 부동산의 채권담보 설정 가능 금액을 조회/저장
    - 1단계: 수동 입력 기반
    - 2단계: API 자동 조회 기반 (source 필드로 구분)
    """

    # ── 물건 유형 ──────────────────────────────────────────
    PROPERTY_TYPE_CHOICES = [
        ("apt",       "아파트"),
        ("villa_new", "빌라/다세대/오피스텔 (연식 20년 미만)"),
        ("villa_old", "빌라/다세대/오피스텔 (연식 20년 이상)"),
        ("house",     "주택/단독주택"),
        ("land",      "토지(대)"),
        ("etc",       "기타(계산불가)"),
    ]

    # ── 데이터 입력 방식 ────────────────────────────────────
    SOURCE_CHOICES = [
        ("manual", "수동 입력"),    # 1단계
        ("api",    "API 자동조회"), # 2단계
    ]

    # ── 소유자 관계 ────────────────────────────────────────
    OWNER_REL_CHOICES = [
        ("self",    "본인(FA)"),
        ("spouse",  "배우자"),
        ("lineal",  "직계존비속"),
        ("sibling", "형제자매"),
        ("third",   "기타 제3자 (근저당 설정 불가)"),
    ]

    # ── 관계 ───────────────────────────────────────────────
    requester     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="collateral_evals",
        verbose_name="조회자(플래너)",
    )

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collateral_evals_as_target",
        verbose_name="대상자",
    )

    # ── 물건 정보 ──────────────────────────────────────────
    property_type = models.CharField(
        max_length=20,
        choices=PROPERTY_TYPE_CHOICES,
        verbose_name="물건 유형",
    )
    address       = models.CharField(max_length=300, blank=True, verbose_name="주소")

    # ── 소유자 정보 ────────────────────────────────────────
    owner_rel     = models.CharField(
        max_length=10,
        choices=OWNER_REL_CHOICES,
        blank=True,
        default="self",
        verbose_name="소유자 관계",
    )
    owner_name    = models.CharField(max_length=50, blank=True, verbose_name="소유자 성명")
    owner_phone   = models.CharField(max_length=20, blank=True, verbose_name="소유자 연락처")
    
    # ── 핵심 금액 ──────────────────────────────────────────
    kb_price      = models.BigIntegerField(verbose_name="KB시세(원)")
    prior_debt    = models.BigIntegerField(default=0, verbose_name="기설정 채권최고액(원)")
    lease_deposit = models.BigIntegerField(default=0, verbose_name="임차보증금(원)")
    
    # ── 계산 결과 ──────────────────────────────────────────
    apply_rate    = models.DecimalField(
        max_digits=5, decimal_places=2,
        verbose_name="적용비율(%)",
    )  # 70.00 / 60.00 / 50.00 / 40.00
    max_collateral = models.BigIntegerField(verbose_name="담보설정 가능금액(원)")
    # = kb_price * apply_rate/100 - prior_debt
    # 음수면 0으로 저장
    
    # ── 메타 ───────────────────────────────────────────────
    source        = models.CharField(
        max_length=10,
        choices=SOURCE_CHOICES,
        default="manual",
        verbose_name="입력방식",
    )
    memo          = models.TextField(blank=True, verbose_name="메모")
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "담보평가"
        verbose_name_plural = "담보평가 이력"

    def __str__(self):
        return (
            f"[{self.get_property_type_display()}] "
            f"{self.address or '주소없음'} / "
            f"설정가능: {self.max_collateral:,}원 "
            f"({self.created_at:%Y-%m-%d})"
        )
    

# =========================================================
# Industry Info Models Import
# - board 앱의 업계정보 실체 모델을 app registry에 등록
# - Django는 board.models import 시 이 모델들도 함께 로드한다
# =========================================================
from .models_industry import (  # noqa: E402,F401
    IndustryArticle,
    IndustryUserPreference,
    IndustryRecommendation,
    IndustryCollectJobLog,
)


# =============================================================================
# WorkTask 업무관리 모델 (Phase 1)
# SSOT 문서: docs/02_apps/worktask.md
#
# 보안 원칙 요약:
#   - owner 필드가 모든 소유자 격리의 기준
#   - 뷰/템플릿에서 ORM 직접 호출 금지 → services/worktasks.py 경유 필수
#   - WorkTaskAttachment.file.url 직접 노출 금지 → worktask_att_download 뷰 경유
# =============================================================================


class WorkCategory(models.Model):
    """
    업무 분류 마스터.

    관리자가 Django Admin에서 등록·관리한다.
    is_active=False 이면 등록 폼에서 미노출.
    code 가 PK이므로 외부에서 코드값으로 직접 참조한다.
    """
    # ── 추가: worktask_create 폼에서 사용하는 구분 코드 7종 ──
    CODE_CHOICES = [
        ("commission",    "수수료 업무"),
        ("bond",          "채권·환수"),
        ("risk",          "리스크관리"),
        ("biz_dev",       "제휴영업"),
        ("misc",          "기타"),
        # 운영 등록 7종 (workcategory_initial.json fixture)
        ("fee_bond",      "수수료/채권"),
        ("risk_retention","리스크/유지율"),
        ("solicitation",  "위해촉"),
        ("it_system",     "전산"),
        ("meeting",       "회의/미팅"),
        ("lease",         "임대차"),
        ("sales_recruit", "영업/리쿠르팅"),
    ]

    code       = models.CharField(max_length=30, primary_key=True,
                                  choices=CODE_CHOICES, verbose_name="분류 코드")
    label      = models.CharField(max_length=50, verbose_name="표시명")
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name="정렬순서")
    is_active  = models.BooleanField(default=True, verbose_name="활성")

    class Meta:
        ordering       = ["sort_order", "code"]
        verbose_name   = "업무 분류"
        verbose_name_plural = "업무 분류"

    def __str__(self):
        return self.label


class WorkTask(models.Model):
    """
    개인 업무관리 핵심 모델.

    ⚠️ 소유자 격리 원칙 (worktask.md §2):
        모든 목록/상세 조회는 반드시 services/worktasks.py 경유.
        뷰에서 WorkTask.objects.* 직접 호출 금지.

    반복 구조:
        template_task=None + recurrence_type≠none → 반복 원본(템플릿)
        template_task=<pk>                        → 배치가 자동생성한 자식 레코드
    """
 
    # -------------------------------------------------------------------------
    # 반복 유형 상수 (worktask.md §3.2 recurrence_type 상수표)
    # -------------------------------------------------------------------------
    RECURRENCE_NONE         = "none"
    RECURRENCE_MONTHLY_OPEN = "monthly_open"
    RECURRENCE_MONTHLY_MID  = "monthly_mid"
    RECURRENCE_MONTHLY_END  = "monthly_end"
    RECURRENCE_DAILY        = "daily"
    RECURRENCE_CUSTOM       = "custom"

    RECURRENCE_CHOICES = [
        (RECURRENCE_NONE,         "반복 없음"),
        (RECURRENCE_MONTHLY_OPEN, "매달 월초 (1~10일)"),
        (RECURRENCE_MONTHLY_MID,  "매달 중순"),
        (RECURRENCE_MONTHLY_END,  "매달 말"),
        (RECURRENCE_DAILY,        "매일"),
        (RECURRENCE_CUSTOM,       "직접 지정"),
    ]

    # -------------------------------------------------------------------------
    # 상태 상수
    # -------------------------------------------------------------------------
    STATUS_PENDING     = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE        = "done"
    STATUS_SKIPPED     = "skipped"

    STATUS_CHOICES = [
        (STATUS_PENDING,     "대기"),
        (STATUS_IN_PROGRESS, "진행중"),
        (STATUS_DONE,        "완료"),
        (STATUS_SKIPPED,     "보류"),
    ]

    # -------------------------------------------------------------------------
    # 소유자 / 분류
    # -------------------------------------------------------------------------
    owner    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="worktasks",
        verbose_name="소유자",
        db_index=True,
    )
    category = models.ForeignKey(
        WorkCategory,
        on_delete=models.PROTECT,
        related_name="worktasks",
        verbose_name="업무 분류",
    )

    # -------------------------------------------------------------------------
    # 내용
    # -------------------------------------------------------------------------
    title       = models.CharField(max_length=200, verbose_name="업무명")
    description = models.TextField(blank=True, default="", verbose_name="메모")
    # 관련 인물 참조 메모 전용 — 권한 부여 없음 (worktask.md §3.2)
    related_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="related_worktasks",
        verbose_name="관련 인물",
    )

    # -------------------------------------------------------------------------
    # 일정 / 반복
    # -------------------------------------------------------------------------
    start_date      = models.DateField(null=True, blank=True, verbose_name="시작일")
    due_date        = models.DateField(null=True, blank=True, verbose_name="마감일")
    calendar_span_mode = models.BooleanField(
        default=False,
        verbose_name="캘린더 기간 막대 표시",
        help_text="체크 시 시작일부터 마감일까지 캘린더에 기간 막대로 표시합니다.",
    )
    recurrence_type = models.CharField(
        max_length=20, choices=RECURRENCE_CHOICES,
        default=RECURRENCE_NONE, verbose_name="반복 유형",
    )
    # custom 유형 전용 — 직접 지정 일자 (1~28)
    recurrence_day  = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="반복 일자(custom)",
    )
    # 반복 원본 참조 — None=원본(템플릿), 값=자동생성 자식
    template_task   = models.ForeignKey(
        "self",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_tasks",
        verbose_name="반복 원본",
    )
    # 귀속 월 ("2026-03" 형식) — 중복 생성 방지 키
    target_ym       = models.CharField(
        max_length=7, blank=True, default="", verbose_name="귀속 월",
    )

    # -------------------------------------------------------------------------
    # 상태 / 우선순위
    # -------------------------------------------------------------------------
    status   = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_PENDING, verbose_name="상태",
    )

    # -------------------------------------------------------------------------
    # 우선순위 상수
    # -------------------------------------------------------------------------
    PRIORITY_HIGH = "high"
    PRIORITY_MID  = "mid"
    PRIORITY_LOW  = "low"

    PRIORITY_CHOICES = [
        (PRIORITY_HIGH, "상"),
        (PRIORITY_MID,  "중"),
        (PRIORITY_LOW,  "하"),
    ]

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MID,
        verbose_name="우선순위",
    )

    # -------------------------------------------------------------------------
    # 알림
    # -------------------------------------------------------------------------
    notify_days_before = models.PositiveSmallIntegerField(
        default=3, verbose_name="알림 D-N일 전",
    )
    # True = 이미 발송 완료 → 중복 발송 방지 플래그 (worktask.md §11.3)
    is_notified = models.BooleanField(
        default=False, verbose_name="알림 발송 완료",
    )

    family_branches = models.JSONField(
        "영업가족",
        default=list,  # callable 유지 (OK)
        blank=True,
        null=False,
        help_text="업무관리에서 선택한 영업가족 지점명 목록",
    )

    # -------------------------------------------------------------------------
    # 감사
    # -------------------------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="등록일시")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="수정일시")

    class Meta:
        ordering = ["priority", "due_date", "-created_at"]
        verbose_name        = "업무 항목"
        verbose_name_plural = "업무 항목"
        indexes = [
            # 목록 조회 핵심 복합 인덱스 (worktask.md §3.2 DB 인덱스)
            models.Index(
                fields=["owner", "status", "due_date"],
                name="wt_owner_status_due_idx",
            ),
            # 반복 자동생성 배치 중복 방지 조회
            models.Index(
                fields=["template_task", "target_ym"],
                name="wt_template_ym_idx",
            ),
        ]

    def __str__(self):
        return f"[{self.category}] {self.title} ({self.owner_id})"

    # -------------------------------------------------------------------------
    # 프로퍼티 (worktask.md §3.2 주요 프로퍼티)
    # -------------------------------------------------------------------------

    @property
    def is_template(self) -> bool:
        """
       반복 원본(템플릿) 여부.
        template_task 가 None 이고 반복 유형이 설정된 경우 True.
        """
        return (
            self.template_task_id is None
            and self.recurrence_type != self.RECURRENCE_NONE
        )

    @property
    def is_overdue(self) -> bool:
        """
        마감 초과 여부.
        due_date 가 오늘 이전이고 완료/건너뜀 상태가 아닌 경우 True.
        """
        from django.utils import timezone
        if not self.due_date:
            return False
        return (
            self.due_date < timezone.localdate()
            and self.status not in (self.STATUS_DONE, self.STATUS_SKIPPED)
        )

    def get_status_display_label(self) -> str:
        """상태 한글 표시명 반환."""
        return dict(self.STATUS_CHOICES).get(self.status, self.status)


class WorkTaskAttachment(models.Model):
    """
    WorkTask 첨부파일.

    ⚠️ 보안 정책 (worktask.md §13.1):
        att.file.url 직접 노출 절대 금지.
        반드시 worktask_att_download 뷰 경유 → 소유자 검증 → FileResponse.

    original_name: 업로드 시 원본 파일명 저장 → RFC5987 한글 다운로드에 사용.
    """
 
    task          = models.ForeignKey(
        WorkTask, on_delete=models.CASCADE,
        related_name="attachments", verbose_name="업무 항목",
    )
    file          = models.FileField(
        upload_to="worktask_attachments/%Y/%m/", verbose_name="파일",
    )
    original_name = models.CharField(
        max_length=255, verbose_name="원본 파일명",
        help_text="RFC5987 Content-Disposition 헤더에 사용",
    )
    uploaded_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="업로더",
    )
    uploaded_at   = models.DateTimeField(auto_now_add=True, verbose_name="업로드일시")

    class Meta:
        ordering        = ["-uploaded_at"]
        verbose_name    = "업무 첨부파일"
        verbose_name_plural = "업무 첨부파일"

    def __str__(self):
        return f"{self.original_name} (task={self.task_id})"


class WorkTaskComment(models.Model):
    task = models.ForeignKey(WorkTask, related_name="comments", on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField("댓글 내용", max_length=500)
    created_at = models.DateTimeField("작성일시", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "업무관리 댓글"
        verbose_name_plural = "업무관리 댓글 목록"