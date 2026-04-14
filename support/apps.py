# django_ma/support/apps.py

from django.apps import AppConfig


class SupportConfig(AppConfig):
    """
    영업지원(support) 앱 설정

    - verbose_name은 운영/admin 화면에서 한글 명칭으로 보이도록 유지합니다.
    - default_auto_field는 프로젝트 기본 PK 정책과 맞춥니다.
    - 업계정보 기능의 공식 운영 기준은 단계적 이관을 거쳐 board로 이동했습니다.
    - 현재 support 앱은 레거시 호환/기존 경로 유지 목적을 포함합니다.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "support"
    verbose_name = "영업지원(레거시)"