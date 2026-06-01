from django.urls import path

from . import views
from .oidc import CustomUserInfoView

app_name = "ai"

urlpatterns = [
    path("llm/", views.llm_redirect, name="llm_redirect"),
    # OIDC UserInfo 테스트 엔드포인트 (실제 OIDC 흐름은 /o/userinfo/ 사용)
    path("oidc/userinfo/", CustomUserInfoView.as_view(), name="oidc_userinfo"),
]
