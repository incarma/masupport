# board/urls.py
#
# 변경 내용 (기존 코드 무변경):
#   - 기존 post_patterns / support_patterns / task_patterns /
#     collateral_patterns / industry_patterns 전부 그대로 유지
#   - 하단 urlpatterns 에 worktasks/ include 한 줄 추가
#
# =============================================================
# Board 앱 URL 설정
#
# ┌─ 그룹 구조 ─────────────────────────────────────────────┐
# │  post_patterns      업무요청 게시판(Post)                │
# │  support_patterns   서식/PDF (support_form, states_form) │
# │  task_patterns      직원업무 게시판 (superuser 전용)     │
# │  collateral_patterns 담보평가 계산기 (로그인 전체 허용)  │
# │  industry_patterns  업계정보 (로그인 전체 허용)          │
# │  worktask_patterns  개인 업무관리 (superuser 전용)       │
# └──────────────────────────────────────────────────────────┘
# =============================================================

from django.urls import include, path
from . import views

app_name = "board"


# ---------------------------------------------------------------
# Post (업무요청 게시판)
# ---------------------------------------------------------------
post_patterns = [
    path("", views.post_list, name="post_list"),
    path("posts/create/", views.post_create, name="post_create"),
    path("posts/<int:pk>/", views.post_detail, name="post_detail"),
    path("posts/<int:pk>/edit/", views.post_edit, name="post_edit"),
    # 인라인 업데이트 (목록 / 상세 공용)
    path(
        "ajax/update-post-field/",
        views.ajax_update_post_field,
        name="ajax_update_post_field",
    ),
    path(
        "ajax/posts/<int:pk>/update-field/",
        views.ajax_update_post_field_detail,
        name="ajax_update_post_field_detail",
    ),
    # 첨부 다운로드 (보안 경유 — FieldFile.url 직접 노출 금지)
    path(
        "posts/attachments/<int:att_id>/download/",
        views.post_attachment_download,
        name="post_attachment_download",
    ),
]


# ---------------------------------------------------------------
# Support / States Form + PDF
# ---------------------------------------------------------------
support_patterns = [
    path("support_form/", views.support_form, name="support_form"),
    path("states_form/", views.states_form, name="states_form"),
    path("generate-support/", views.generate_request_support, name="generate_request_support"),
    path("generate-states/", views.generate_request_states, name="generate_request_states"),
    path("search-user/", views.search_user, name="search_user"),
]


# ---------------------------------------------------------------
# Task (직원업무 게시판) — superuser only (뷰 레벨에서 강제)
# ---------------------------------------------------------------
task_patterns = [
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/create/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/edit/", views.task_edit, name="task_edit"),
    # 인라인 업데이트 (목록 / 상세 공용)
    path(
        "ajax/tasks/update-task-field/",
        views.ajax_update_task_field,
        name="ajax_update_task_field",
    ),
    path(
        "ajax/tasks/<int:pk>/update-field/",
        views.ajax_update_task_field_detail,
        name="ajax_update_task_field_detail",
    ),
    # 첨부 다운로드 (보안 경유)
    path(
        "tasks/attachments/<int:att_id>/download/",
        views.task_attachment_download,
        name="task_attachment_download",
    ),
]


# ---------------------------------------------------------------
# Collateral (담보평가) — 로그인 사용자 전체 허용 (뷰 레벨: login_required)
# ---------------------------------------------------------------
collateral_patterns = [
    path("collateral/", views.collateral_page, name="collateral"),
    path("collateral/calc/", views.collateral_calc, name="collateral_calc"),
    path("collateral/<int:eval_id>/delete/", views.collateral_delete, name="collateral_delete"),
]


# ---------------------------------------------------------------
# Industry Info (업계정보) — 로그인 사용자 전체 허용
# ---------------------------------------------------------------
industry_patterns = [
    path("industry-info/", views.industry_info, name="industry_info"),
    path("industry-info/bookmarks/", views.industry_bookmarks, name="industry_bookmarks"),
    path(
        "api/industry/articles/<int:article_id>/preference/",
        views.industry_save_preference,
        name="api_industry_preference",
    ),
    path(
        "api/industry/articles/<int:article_id>/click/",
        views.industry_mark_click,
        name="api_industry_click",
    ),
]


# ---------------------------------------------------------------
# URL 조합
# ---------------------------------------------------------------
urlpatterns = [
    *post_patterns,
    *support_patterns,
    *task_patterns,
    *collateral_patterns,
    *industry_patterns,

    # ----------------------------------------------------------
    # WorkTask 업무관리 (Phase 1 신규 추가)
    # 네임스페이스: board:worktasks
    # 기존 posts/, tasks/ URL 과 충돌 없음
    # ----------------------------------------------------------
    path(
        "worktasks/",
        include(("board.worktask_urls", "worktasks")),
    ),
]