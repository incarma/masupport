# django_ma/board/migrations/0030_krholiday.py
# Generated manually for WorkTask KR holiday cache

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("board", "0029_worktask_calendar_span_mode"),
    ]

    operations = [
        migrations.CreateModel(
            name="KrHoliday",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True, unique=True, verbose_name="공휴일 날짜")),
                ("name", models.CharField(max_length=80, verbose_name="공휴일명")),
                ("is_holiday", models.BooleanField(db_index=True, default=True, verbose_name="휴일 여부")),
                ("is_temporary", models.BooleanField(default=False, verbose_name="임시공휴일 여부")),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("api", "API"),
                            ("manual", "수동등록"),
                            ("override", "수동보정"),
                        ],
                        default="api",
                        max_length=30,
                        verbose_name="출처",
                    ),
                ),
                ("source_event_id", models.CharField(blank=True, default="", max_length=80, verbose_name="원천 식별자")),
                ("raw_payload", models.JSONField(blank=True, default=dict, verbose_name="원본 응답")),
                ("fetched_at", models.DateTimeField(blank=True, null=True, verbose_name="마지막 수집시각")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="생성일시")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="수정일시")),
            ],
            options={
                "verbose_name": "대한민국 공휴일",
                "verbose_name_plural": "대한민국 공휴일",
                "ordering": ["date"],
            },
        ),
        migrations.AddIndex(
            model_name="krholiday",
            index=models.Index(fields=["date", "is_holiday"], name="krholiday_date_holiday_idx"),
        ),
    ]