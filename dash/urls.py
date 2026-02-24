from django.urls import path
from dash import viewmods as views

app_name = "dash"

urlpatterns = [
    path("", views.redirect_to_sales, name="dash_home"),
    path("sales/", views.dash_sales, name="dash_sales"),

    # ✅ 템플릿에서 사용(Upload modal)
    path("sales/upload/", views.upload_sales_excel, name="dash_sales_upload"),

    path("recruit/", views.dash_recruit, name="dash_recruit"),
    path("retention/", views.dash_retention, name="dash_retention"),
    path("goals/", views.dash_goals, name="dash_goals"),

    # ✅ API(기존 호환 유지)
    path("api/upload/", views.upload_sales_excel, name="dash_upload_sales_excel"),
    path("api/forecast/", views.dash_forecast_api, name="dash_forecast_api"),

    # (선택) 프론트가 /sales/forecast/ 를 쓰는 경우 대비 alias
    path("sales/forecast/", views.dash_forecast_api, name="dash_sales_forecast"),
]
