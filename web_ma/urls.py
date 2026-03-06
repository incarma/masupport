"""
URL configuration for web_ma project.
"""

# django_ma/web_ma/urls.py

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.static import serve

from accounts import views as accounts_views
from accounts.custom_admin import custom_admin_site
from accounts.views import SessionCloseLoginView

import web_ma.views as web_views



# ✅ 500 에러 핸들러(운영에서 traceback 강제 로깅용)
handler500 = "web_ma.views.handler500"


def home_redirect(request):
    """홈(/) 접속 시 매뉴얼로 리다이렉트"""
    return redirect("manual:manual_list")


urlpatterns = [
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
    path("", home_redirect, name="home"),

    # ---------------------------------------------------------------------
    # Apps
    # ---------------------------------------------------------------------
    path("join/", include("join.urls")),
    path("board/", include("board.urls")),
    path("commission/", include("commission.urls")),
    path("dash/", include("dash.urls")),
    path("partner/", include(("partner.urls", "partner"), namespace="partner")),
    path("manual/", include("manual.urls")),
    path("ckeditor/", include("ckeditor_uploader.urls")),

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

# -------------------------------------------------------------------------
# Media serving
# - 운영에서도 접근이 필요하고, 인증 필요라면 login_required(serve) 유지
# - (주의) serve는 개발용에 가까움. 운영은 Nginx/S3/Cloudflare 권장
# -------------------------------------------------------------------------
urlpatterns += [
    re_path(
        r"^media/(?P<path>.*)$",
        login_required(serve),
        {"document_root": settings.MEDIA_ROOT},
    ),
]

# DEBUG일 때는 Django가 MEDIA_URL도 보조 서빙
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
