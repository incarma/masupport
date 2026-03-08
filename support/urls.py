# django_ma/support/urls.py

from django.urls import path

from .views import industry_info, mark_click, save_preference

app_name = "support"

urlpatterns = [
    # -------------------------------------------------------------------------
    # 업계정보 메인 페이지
    # -------------------------------------------------------------------------
    path("", industry_info, name="industry_info"),

    # -------------------------------------------------------------------------
    # 사용자 액션 API
    # -------------------------------------------------------------------------
    path("api/articles/<int:article_id>/preference/", save_preference, name="api_preference"),
    path("api/articles/<int:article_id>/click/", mark_click, name="api_click"),
]