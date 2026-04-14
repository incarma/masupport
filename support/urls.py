# django_ma/support/urls.py

from django.urls import path

from .views import industry_info, mark_click, save_preference

app_name = "support"

urlpatterns = [
    # -------------------------------------------------------------------------
    # 레거시 업계정보 진입점
    # - 실제 화면은 board:industry_info 로 redirect
    # -------------------------------------------------------------------------
    path("", industry_info, name="industry_info"),

    # -------------------------------------------------------------------------
    # 레거시 액션 API
    # - 실제 구현은 board.views.industry_info 로 위임
    # -------------------------------------------------------------------------
    path("api/articles/<int:article_id>/preference/", save_preference, name="api_preference"),
    path("api/articles/<int:article_id>/click/", mark_click, name="api_click"),
]