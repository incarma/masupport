# django_ma/support/models.py

from django.conf import settings
from django.db import models

from .constants import SOURCE_CHOICES, SOURCE_DIRECT, TOPIC_CHOICES


class TimeStampedModel(models.Model):
    """
    공통 생성/수정 시각 추상 모델
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SupportArticle(TimeStampedModel):
    """
    업계정보 기사 메타데이터 SSOT

    설계 원칙:
    - 원문 전문 저장보다 메타데이터 중심
    - 페이지에서는 이 테이블만 읽음
    - 외부 뉴스 API는 배치 수집 후 이 테이블에 적재
    """

    source_portal = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_DIRECT,
    )
    source_name = models.CharField(max_length=120, blank=True)
    external_id = models.CharField(max_length=255, blank=True)

    title = models.CharField(max_length=300)
    summary = models.TextField(blank=True)

    original_url = models.URLField(max_length=1000, blank=True)
    portal_url = models.URLField(max_length=1000, blank=True)

    published_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)

    keyword_query = models.CharField(max_length=120, blank=True)
    topic = models.CharField(max_length=50, choices=TOPIC_CHOICES, blank=True)
    tags_json = models.JSONField(default=list, blank=True)

    # 중복 제거용 해시
    normalized_hash = models.CharField(max_length=64, unique=True, db_index=True)

    # 운영 노출 제어
    is_active = models.BooleanField(default=True)
    is_hidden = models.BooleanField(default=False)

    # 디버깅/운영 확인용 원본 payload 최소 보관
    raw_payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "support_article"
        ordering = ["-published_at", "-id"]
        indexes = [
            models.Index(fields=["-published_at"], name="support_art_pub_idx"),
            models.Index(fields=["topic"], name="support_art_topic_idx"),
            models.Index(fields=["source_name"], name="support_art_source_idx"),
            models.Index(fields=["is_active", "is_hidden"], name="support_art_vis_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def display_url(self) -> str:
        """
        사용자에게 열어줄 링크
        - 원문 링크 우선
        - 원문이 없으면 포털 링크 fallback
        """
        return self.original_url or self.portal_url


class SupportUserPreference(TimeStampedModel):
    """
    사용자별 기사 선호도

    포함 항목:
    - 평점
    - 북마크
    - 관심없음(숨김)
    - 읽음/클릭 기록
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_preferences",
    )
    article = models.ForeignKey(
        SupportArticle,
        on_delete=models.CASCADE,
        related_name="preferences",
    )

    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    is_bookmarked = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)

    is_read = models.BooleanField(default=False)
    clicked_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    dwell_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "support_user_preference"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "article"],
                name="uq_support_user_article",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "updated_at"], name="support_pref_user_idx"),
            models.Index(fields=["article"], name="support_pref_article_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.article}"


class SupportRecommendation(TimeStampedModel):
    """
    추천 결과 스냅샷

    현재 MVP에서는 실시간 추천이 중심이지만,
    추후 저장형 추천/배치형 추천으로 확장할 수 있도록 모델을 먼저 둡니다.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_recommendations",
    )
    article = models.ForeignKey(
        SupportArticle,
        on_delete=models.CASCADE,
        related_name="recommendations",
    )

    score = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    reason_code = models.CharField(max_length=50, blank=True)
    reason_text = models.CharField(max_length=255, blank=True)
    model_version = models.CharField(max_length=50, blank=True)
    batch_key = models.CharField(max_length=50, blank=True)

    clicked = models.BooleanField(default=False)
    clicked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "support_recommendation"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="support_rec_user_idx"),
            models.Index(fields=["model_version"], name="support_rec_model_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.article} ({self.score})"


class SupportCollectJobLog(TimeStampedModel):
    """
    기사 수집 작업 로그

    운영자가 확인할 수 있도록 수집 성공/실패와 처리 건수를 기록합니다.
    """

    STATUS_READY = "ready"
    STATUS_SUCCESS = "success"
    STATUS_FAIL = "fail"

    STATUS_CHOICES = [
        (STATUS_READY, "준비"),
        (STATUS_SUCCESS, "성공"),
        (STATUS_FAIL, "실패"),
    ]

    source = models.CharField(max_length=20, blank=True)
    query = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_READY)

    fetched_count = models.PositiveIntegerField(default=0)
    inserted_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    requested_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_collect_jobs",
    )

    message = models.TextField(blank=True)
    meta_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "support_collect_job_log"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.source}:{self.query} [{self.status}]"