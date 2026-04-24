# django_ma/dash/viewmods/__init__.py
from .pages import redirect_to_sales, dash_sales, dash_recruit, dash_retention, dash_goals
from .api_upload import upload_sales_excel
from .api_forecast import dash_forecast_api
from .api_retention_upload import upload_retention_excel
from .api_retention import retention_api

__all__ = [
    "redirect_to_sales",
    "dash_sales",
    "dash_recruit",
    "dash_retention",
    "dash_goals",
    "upload_sales_excel",
    "dash_forecast_api",
    "upload_retention_excel",
    "retention_api",
]