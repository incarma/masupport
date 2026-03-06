# django_ma/accounts/urls.py

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # ---------------------------------------------------------------------
    # Password change (로그인 사용자 비밀번호 변경)
    #
    # Phase 3(강제 비번변경) 미들웨어 whitelist가 다음 URL name을 참조합니다(SSOT):
    # - accounts:password_change
    # - accounts:password_change_done
    #
    # 사용처(대표):
    # - templates/base.html 네비게이션 "비번변경" 버튼
    #
    # Endpoints:
    # - GET/POST  /accounts/password-change/        (폼 표시/제출)
    # - GET       /accounts/password-change/done/   (완료 화면)
    # ---------------------------------------------------------------------
    path(
        "password-change/",
        views.password_change_view,
        name="password_change",
    ),
    path(
        "password-change/done/",
        views.password_change_done_view,
        name="password_change_done",
    ),

    # ---------------------------------------------------------------------
    # Excel Upload Progress (진행률 polling)
    #
    # 사용처(대표):
    # - accounts/admin 엑셀 업로드 UI
    # - task_id 기반 Celery 진행률/상태 조회
    #
    # GET /accounts/upload-progress/?task_id=...
    # ---------------------------------------------------------------------
    path(
        "upload-progress/",
        views.upload_progress_view,
        name="accounts_upload_progress",
    ),

    # ---------------------------------------------------------------------
    # Excel Upload Result Download (결과 파일 다운로드)
    #
    # - 업로드 완료 후 생성된 결과 파일(xlsx 등)을 다운로드
    # - 보안상 URL 직접 노출 대신, view에서 파일 존재/권한 확인 후 FileResponse 제공
    #
    # GET /accounts/upload-result/<task_id>/
    # ---------------------------------------------------------------------
    path(
        "upload-result/<str:task_id>/",
        views.upload_result_view,
        name="accounts_upload_result",
    ),


    # ---------------------------------------------------------------------
    # User search API (SSOT)
    #
    # ✅ 권장 엔드포인트
    #   GET /accounts/api/search-user/
    #     ?q=키워드
    #     &scope=branch|...
    #     [&branch=지점명]
    #
    # - 공통 검색 모달
    # - manage-structure / manage-rate / support-form 등 공용
    # ---------------------------------------------------------------------
    path(
        "api/search-user/",
        views.api_search_user,
        name="api_search_user",
    ),

    # ---------------------------------------------------------------------
    # Legacy alias (하위 호환)
    #
    # ❌ 신규 개발에서는 사용 비권장
    # - 내부적으로는 api_search_user와 동일 동작
    # - 점진적 제거를 위해 유지
    #
    # GET /accounts/search-user/
    # ---------------------------------------------------------------------
    path(
        "search-user/",
        views.search_user,  # alias → api_search_user
        name="search_user_legacy",
    ),
]
