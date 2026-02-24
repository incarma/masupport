# django_ma/dash/models.py
from django.db import models
from django.utils import timezone
from django.conf import settings


class SalesRecord(models.Model):
    """
    업로드 엑셀의 '증권번호'를 PK로 사용하여 매월 파일이 재업로드 되어도 upsert 가능하도록 설계.
    """

    LIFE_NL_CHOICES = [
        ("손보", "손보"),
        ("생보", "생보"),
        ("자동차", "자동차"),
    ]

    policy_no = models.CharField("증권번호", max_length=60, primary_key=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_records",
        db_index=True,
        verbose_name="설계사",
    )

    part_snapshot = models.CharField("부서(스냅샷)", max_length=30, blank=True, null=True)
    branch_snapshot = models.CharField("지점(스냅샷)", max_length=100, blank=True, null=True)
    name_snapshot = models.CharField("성명(스냅샷)", max_length=100, blank=True, null=True)
    emp_id_snapshot = models.CharField("사원번호(스냅샷)", max_length=30, blank=True, null=True)

    insurer = models.CharField("보험사", max_length=60, db_index=True)
    contractor = models.CharField("계약자", max_length=100, blank=True, null=True)

    insured = models.CharField("피보험자", max_length=100, blank=True, null=True)

    ins_start = models.DateField("보험시작", blank=True, null=True)
    ins_end = models.DateField("보험종기", blank=True, null=True)

    pay_method = models.CharField("납입방법", max_length=30, blank=True, null=True)

    receipt_date = models.DateField("영수일자", blank=True, null=True, db_index=True)
    receipt_amount = models.BigIntegerField("영수금", blank=True, null=True)

    product_code = models.CharField("상품코드", max_length=60, blank=True, null=True)
    product_name = models.CharField("상품명", max_length=255, blank=True, null=True)

    # ✅ 자동차 파일에서 사용하는 차량번호
    vehicle_no = models.CharField("차량번호", max_length=40, blank=True, null=True, db_index=True)

    # ✅ 자동차 전용
    car_liability = models.BigIntegerField("책임", blank=True, null=True)
    car_optional = models.BigIntegerField("임의", blank=True, null=True)
    status = models.CharField("상태", max_length=40, blank=True, null=True)

    life_nl = models.CharField("손생", max_length=10, choices=LIFE_NL_CHOICES, default="손보", db_index=True)

    ym = models.CharField("월도(YYYY-MM)", max_length=7, db_index=True)

    updated_at = models.DateTimeField("업데이트", auto_now=True)
    created_at = models.DateTimeField("생성", auto_now_add=True)

    class Meta:
        db_table = "dash_sales_record"
        verbose_name = "매출레코드"
        verbose_name_plural = "매출레코드"
        indexes = [
            models.Index(fields=["ym", "insurer"]),
            models.Index(fields=["ym", "life_nl"]),
            models.Index(fields=["ym", "user"]),
            models.Index(fields=["ym", "vehicle_no"]),
        ]

    def __str__(self):
        return f"{self.policy_no} / {self.insurer} / {self.ym}"


class SalesDailyAgg(models.Model):
    """
    학습/예측 공용 집계 테이블 (일 단위)
    scope_type: all/part/branch
    scope_key: '*' or part/branch 문자열
    category: long(손생장기)/car/long_nonlife/long_life  (4개 차트 기준)
    """
    SCOPE_CHOICES = [("all", "all"), ("part", "part"), ("branch", "branch")]
    CAT_CHOICES = [
        ("long", "손생장기"),
        ("car", "자동차"),
        ("long_nonlife", "손보장기"),
        ("long_life", "생보장기"),
    ]

    ym = models.CharField(max_length=7, db_index=True)  # YYYY-MM
    day = models.PositiveSmallIntegerField(db_index=True)  # 1..31

    scope_type = models.CharField(max_length=10, choices=SCOPE_CHOICES, db_index=True)
    scope_key = models.CharField(max_length=100, db_index=True)  # '*' or value
    category = models.CharField(max_length=20, choices=CAT_CHOICES, db_index=True)

    amount = models.BigIntegerField(default=0)  # 해당 일자 매출 합계(영수금)
    cumsum = models.BigIntegerField(default=0)  # 월 1일부터 해당일까지 누적(서버에서 채움)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dash_sales_daily_agg"
        unique_together = [("ym", "day", "scope_type", "scope_key", "category")]
        indexes = [
            models.Index(fields=["ym", "scope_type", "scope_key", "category"]),
        ]


class SalesForecast(models.Model):
    """
    월말 총액 예측(분위수) + 메타
    같은 ym/scope/asof_day/category/model_ver는 1개로 upsert 가능
    """
    ym = models.CharField(max_length=7, db_index=True)
    asof_day = models.PositiveSmallIntegerField(db_index=True)

    scope_type = models.CharField(max_length=10, db_index=True)
    scope_key = models.CharField(max_length=100, db_index=True)
    category = models.CharField(max_length=20, db_index=True)

    model_ver = models.CharField(max_length=40, default="lgbm_v1", db_index=True)

    pred_total_p10 = models.BigIntegerField(null=True, blank=True)
    pred_total_p50 = models.BigIntegerField(null=True, blank=True)
    pred_total_p90 = models.BigIntegerField(null=True, blank=True)

    # 실제 asof 누적(디버그/검증용)
    actual_to_date = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "dash_sales_forecast"
        unique_together = [("ym", "asof_day", "scope_type", "scope_key", "category", "model_ver")]
        indexes = [
            models.Index(fields=["ym", "scope_type", "scope_key", "asof_day"]),
        ]


class SalesForecastDaily(models.Model):
    """
    일별 예측(분위수) - 차트에 바로 쓰기 좋게
    """
    forecast = models.ForeignKey(SalesForecast, on_delete=models.CASCADE, related_name="days")
    day = models.PositiveSmallIntegerField()

    pred_amount_p10 = models.BigIntegerField(null=True, blank=True)
    pred_amount_p50 = models.BigIntegerField(null=True, blank=True)
    pred_amount_p90 = models.BigIntegerField(null=True, blank=True)

    pred_cumsum_p10 = models.BigIntegerField(null=True, blank=True)
    pred_cumsum_p50 = models.BigIntegerField(null=True, blank=True)
    pred_cumsum_p90 = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "dash_sales_forecast_daily"
        unique_together = [("forecast", "day")]
        indexes = [models.Index(fields=["forecast", "day"])]
