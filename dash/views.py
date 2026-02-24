# django_ma/dash/views.py
"""
Dash views shim (Option A)
- 기존 import 경로(dash.views.*)를 깨지 않기 위해 유지
- 실제 구현은 dash/views/ 패키지로 분리
"""

from dash.viewmods import *  # noqa