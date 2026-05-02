# Generated manually for WorkTask family branches support.
# django_ma/board/migrations/0026_worktask_family_branches.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("board", "0025_priority_to_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="worktask",
            name="family_branches",
            field=models.JSONField(
                default=list,
                blank=True,
                verbose_name="영업가족",
                help_text="업무관리에서 선택한 영업가족 지점명 목록",
            ),
        ),
    ]