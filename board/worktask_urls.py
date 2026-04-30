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
    # AJAX: 삭제 처리 (POST only)
    # ⚠️ 소유자 격리: get_user_task → owner != request.user 이면 404
    # ------------------------------------------------------------------
    path("<int:pk>/delete/", wt_views.worktask_delete, name="worktask_delete"),

    # ------------------------------------------------------------------
    # AJAX: 상태 해제 — 완료/건너뜀 → 대기(pending) 복원 (POST only)
    # ------------------------------------------------------------------
    path("<int:pk>/reset/", wt_views.worktask_reset, name="worktask_reset"),

    # ------------------------------------------------------------------
    # AJAX: 인라인 필드 업데이트 — 목록 셀 편집 (POST only)
    # ------------------------------------------------------------------
    path("<int:pk>/inline-update/", wt_views.worktask_inline_update, name="worktask_inline_update"),

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