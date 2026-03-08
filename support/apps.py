# django_ma/support/apps.py

from django.apps import AppConfig


class SupportConfig(AppConfig):
    """
    영업지원(support) 앱 설정

    - verbose_name은 운영/admin 화면에서 한글 명칭으로 보이도록 유지합니다.
    - default_auto_field는 프로젝트 기본 PK 정책과 맞춥니다.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "support"
    verbose_name = "영업지원"