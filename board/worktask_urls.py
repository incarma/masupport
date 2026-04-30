# board/worktask_urls.py
"""
WorkTask URL 패턴.

board/urls.py 에서 아래와 같이 등록된다:
    path("worktasks/", include(("board.worktask_urls", "worktasks")))

중첩 네임스페이스: board:worktasks
    {% url 'board:worktasks:worktask_list' %}
    {% url 'board:worktasks:worktask_att_download' att.id %}

기존 /board/posts/, /board/tasks/ URL 과 완전 독립.
기존 urls.py(posts/tasks/forms) 는 무변경.
"""

from django.urls import path

from board.views import worktasks as wt_views

urlpatterns = [
    # ------------------------------------------------------------------
    # 목록 (필터: ym / status / category)
    # ------------------------------------------------------------------
    path("",          wt_views.worktask_list,   name="worktask_list"),

    # ------------------------------------------------------------------
    # 등록
    # ------------------------------------------------------------------
    path("create/",   wt_views.worktask_create, name="worktask_create"),

    # ------------------------------------------------------------------
    # 상세
    # ------------------------------------------------------------------
    path("<int:pk>/", wt_views.worktask_detail, name="worktask_detail"),

    # ------------------------------------------------------------------
    # 수정
    # ------------------------------------------------------------------
    path("<int:pk>/edit/", wt_views.worktask_edit, name="worktask_edit"),

    # ------------------------------------------------------------------
    # AJAX: 완료 처리 (POST only)
    # ------------------------------------------------------------------
    path("<int:pk>/done/", wt_views.worktask_done, name="worktask_done"),

    # ------------------------------------------------------------------
    # AJAX: 건너뜀 처리 (POST only)
    # ------------------------------------------------------------------
    path("<int:pk>/skip/", wt_views.worktask_skip, name="worktask_skip"),

    # ------------------------------------------------------------------
    # 첨부파일 보안 다운로드
    # ❌ att.file.url 직접 노출 금지
    # ✅ 이 URL 경유 → 소유자 검증 → FileResponse (worktask.md §13.1)
    # ------------------------------------------------------------------
    path(
        "attachments/<int:att_id>/download/",
        wt_views.worktask_att_download,
        name="worktask_att_download",
    ),

    # ------------------------------------------------------------------
    # 알림 폴링 API (GET)
    # ------------------------------------------------------------------
    path(
        "api/notify-check/",
        wt_views.worktask_notify_check,
        name="worktask_notify_check",
    ),
]