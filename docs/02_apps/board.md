# django_ma/docs/02_apps/board.md

# Board 앱 가이드 (board.md)

------------------------------------------------------------------------

# 1. Board 앱 개요

board 앱은 **django_ma 내부 운영을 위한 업무 처리 중심 앱**이다.

일반 게시판이 아니라 다음 기능을 수행하는 **운영 업무 플랫폼** 역할을
한다.

### 주요 기능

-   업무요청(Post) 등록 / 처리 / 이력 관리
-   직원업무(Task) 내부 처리 (superuser 전용)
-   댓글 기반 커뮤니케이션
-   첨부파일 업로드 및 보안 다운로드
-   상태 / 담당자 인라인 업데이트 (AJAX)
-   업무요청서 / FA 소명서 PDF 출력

> ⚠️ Board 앱은 **운영 시스템 핵심 앱**이므로\
> **보안 / 권한 / 첨부 다운로드 / UX**가 설계의 핵심이다.

------------------------------------------------------------------------

# 2. 디렉터리 구조 (최종 기준)

    board/
    ├── models.py
    ├── urls.py
    │
    ├── views/
    │   ├── __init__.py
    │   ├── posts.py
    │   ├── tasks.py
    │   ├── forms.py
    │   └── attachments.py
    │
    ├── services/
    │   ├── listing.py
    │   ├── inline_update.py
    │   ├── comments.py
    │   └── attachments.py
    │
    ├── templates/
    │   └── board/
    │       ├── base_board.html
    │       ├── post_list.html
    │       ├── post_detail.html
    │       ├── post_create.html
    │       ├── post_edit.html
    │       ├── task_list.html
    │       ├── task_detail.html
    │       ├── task_create.html
    │       ├── task_edit.html
    │       ├── support_form.html
    │       ├── states_form.html
    │       └── includes/
    │           ├── _edit_form.html
    │           ├── _form_common.html
    │           ├── _comment_form.html
    │           ├── _comment_list.html
    │           ├── _inline_handler_status_list.html
    │           └── pagination.html
    │
    ├── static/
    │   ├── css/
    │   │   └── apps/
    │   │       └── board.css
    │   │
    │   └── js/
    │       ├── board/
    │       │   ├── post_list.js
    │       │   ├── post_detail.js
    │       │   ├── task_list.js
    │       │   ├── task_detail.js
    │       │   ├── states_form.js
    │       │   ├── support_form.js
    │       │   └── form_submit_lock.js
    │       │
    │       └── common/
    │           ├── status_ui.js
    │           ├── inline_update.js
    │           ├── detail_inline_update.js
    │           └── comment_edit.js
    │
    └── templatetags/
        ├── board_filters.py
        ├── querystring.py
        └── attachments.py

------------------------------------------------------------------------

# 3. URL 구조

## 3.1 Post (업무요청)

  URL                                                    설명
  ------------------------------------------------------ ---------------
  /board/posts/                                          업무요청 목록
  /board/posts/create/                                   요청 등록
  /board/posts/`<id>`{=html}/                            요청 상세
  /board/posts/`<id>`{=html}/edit/                       요청 수정
  /board/posts/attachments/`<att_id>`{=html}/download/   첨부 다운로드

------------------------------------------------------------------------

## 3.2 Task (직원업무)

  URL                                                    설명
  ------------------------------------------------------ ---------------
  /board/tasks/                                          직원업무 목록
  /board/tasks/create/                                   업무 등록
  /board/tasks/`<id>`{=html}/                            업무 상세
  /board/tasks/`<id>`{=html}/edit/                       업무 수정
  /board/tasks/attachments/`<att_id>`{=html}/download/   첨부 다운로드

> Task는 **superuser 전용 기능**

------------------------------------------------------------------------

## 3.3 서식 / PDF

  URL                        설명
  -------------------------- --------------
  /board/support-form/       업무요청서
  /board/states-form/        FA 소명서
  /board/support-form/pdf/   PDF 생성 API
  /board/states-form/pdf/    PDF 생성 API

------------------------------------------------------------------------

# 4. 템플릿 구조 및 상속 규칙

## 4.1 base_board.html

``` html
{% extends "base.html" %}
{% load static %}

{% block app_css %}
<link rel="stylesheet" href="{% static 'css/apps/board.css' %}">
{% endblock %}

{% block content_wrapper %}
<div class="board-scope">
  {{ block.super }}
</div>
{% endblock %}
```

------------------------------------------------------------------------

## 4.2 핵심 규칙

모든 board 템플릿은 반드시 다음을 상속해야 한다.

    {% extends "board/base_board.html" %}

CSS 정책

-   `.board-scope` 외부로 CSS 누수 금지
-   `board.css`는 base.html에서 직접 로드 금지

------------------------------------------------------------------------

# 5. JavaScript 구조

Board 앱은 **공용 모듈 + 페이지 모듈 구조**로 설계된다.

------------------------------------------------------------------------

## 5.1 공용 모듈

### status_ui.js

기능

-   상태값 → CSS 클래스 매핑
-   상태 badge / select 색상 자동 적용

적용 대상

    .status-select[data-status-ui="1"]

------------------------------------------------------------------------

### inline_update.js

목록 페이지 상태/담당자 AJAX 업데이트

특징

-   CSRF 자동 처리
-   busy 상태 중복 요청 방지
-   성공 시 UI 업데이트

------------------------------------------------------------------------

### detail_inline_update.js

상세 페이지 상태/담당자 업데이트

특징

-   update URL 없으면 자동 종료
-   상태 변경일 텍스트 갱신

------------------------------------------------------------------------

### comment_edit.js

댓글 인라인 수정

특징

-   delegation 이벤트
-   CSRF 자동 탐색

------------------------------------------------------------------------

## 5.2 제출 보호

### form_submit_lock.js

기능

-   폼 중복 제출 방지
-   파일 업로드 연동
-   BFCache 대응

------------------------------------------------------------------------

## 5.3 페이지 스크립트

  Script            대상
  ----------------- ---------------
  post_list.js      업무요청 목록
  post_detail.js    업무요청 상세
  task_list.js      직원업무 목록
  task_detail.js    직원업무 상세
  support_form.js   업무요청서
  states_form.js    FA 소명서

------------------------------------------------------------------------

# 6. CSS 설계 원칙

파일

    static/css/apps/board.css

------------------------------------------------------------------------

## No-Leak Policy

모든 selector는 반드시

    .board-scope ...

예

    .board-scope textarea[name="content"]

------------------------------------------------------------------------

## 주요 스타일 범위

-   리스트 테이블 말줄임
-   댓글 UI
-   첨부파일 UI
-   상태 badge
-   모바일 서식 스크롤

------------------------------------------------------------------------

# 7. 보안 설계

## 첨부 다운로드

❌ 금지

    <a href="{{ att.file.url }}">

✅ 허용

    <a href="{% url 'board:post_attachment_download' att.id %}">

정책

-   View 경유 다운로드
-   권한 검증
-   파일명 정규화
-   RFC5987 적용

------------------------------------------------------------------------

## CSRF 정책

-   모든 AJAX 요청 CSRF 필수

------------------------------------------------------------------------

## XSS 방지

절대 금지

    {{ post.content|safe }}

------------------------------------------------------------------------

## 권한 정책

  기능              권한
  ----------------- ---------------------------
  Post              로그인 사용자
  Task              superuser
  인라인 업데이트   superuser
  support_form      superuser / head / leader
  states_form       inactive 제외

------------------------------------------------------------------------

# 8. 운영 포인트

절대 수정 주의 파일

    services/attachments.py
    views/attachments.py
    base_board.html
    static/css/apps/board.css

------------------------------------------------------------------------

## 신규 기능 추가 패턴

  기능        위치
  ----------- ------------------------
  목록 검색   services/listing
  상태 변경   services/inline_update
  댓글        services/comments
  첨부        services/attachments

------------------------------------------------------------------------

# 9. 확장 설계 원칙

서비스 확장

    services/*

JS 확장

    static/js/common

CSS 확장

    .board-scope

------------------------------------------------------------------------

# 10. 요약

Board 앱은 django_ma에서 **운영 의존도가 가장 높은 앱**이다.

핵심 원칙

-   View는 얇게
-   Service는 공용화
-   CSS는 스코프 고립
-   첨부는 보안 경유
-   운영자 UX 최우선

이 원칙을 유지하면

-   장기 운영
-   인수인계
-   기능 확장

모두 안정적으로 유지할 수 있다.
