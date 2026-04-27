"""
URL configuration for web_ma project.
"""

# django_ma/web_ma/urls.py

from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.custom_admin import custom_admin_site
from accounts.views import SessionCloseLoginView
from web_ma.views import healthz, landing_view


# ✅ 500 에러 핸들러(운영에서 traceback 강제 로깅용)
handler500 = "web_ma.views.handler500"


urlpatterns = [
    # ---------------------------------------------------------------------
    # Healthcheck
    # ---------------------------------------------------------------------
    path("healthz", healthz, name="healthz"),

    # ---------------------------------------------------------------------
    # Auth
    # ---------------------------------------------------------------------
    path("login/", SessionCloseLoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Phase 3(강제 비번변경) whitelist(SSOT, URL name 기준):
    # - login
    # - logout
    # - accounts:password_change
    # - accounts:password_change_done

    # ---------------------------------------------------------------------
    # Admin (custom admin site)
    # ---------------------------------------------------------------------
    path("admin/", custom_admin_site.urls),

    # ---------------------------------------------------------------------
    # Home
    # ---------------------------------------------------------------------
    path("", landing_view, name="home"),

    # ---------------------------------------------------------------------
    # Apps
    # ---------------------------------------------------------------------
    path("join/", include("join.urls")),
    path("board/", include("board.urls")),
    path("commission/", include("commission.urls")),
    path("dash/", include("dash.urls")),
    path("partner/", include(("partner.urls", "partner"), namespace="partner")),
    path("manual/", include("manual.urls")),

    # ---------------------------------------------------------------------
    # Accounts APIs
    # ✅ accounts/urls.py에서:
    #   - upload-progress/
    #   - password-change/
    #   - password-change/done/
    #   - api/search-user/
    #   - search-user/ (legacy alias)
    # 를 관리하고 있으므로, 여기서는 prefix 1번만 붙여 위임합니다.
    # ---------------------------------------------------------------------
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
]


# /media/ 직접 서빙 금지.
# 파일 접근은 반드시 앱별 보호 view에서 권한 검증 후 FileResponse로 제공한다.
# DEBUG에서도 동일 원칙을 유지하여 운영/개발 동작 차이를 줄인다.
