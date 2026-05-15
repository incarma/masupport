# django_ma/manual/apps.py

from django.apps import AppConfig


class ManualConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "manual"
    verbose_name = "업무 매뉴얼"
