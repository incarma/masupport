# Board 앱 지침서 (FINAL · SSOT)

> 본 문서는 django_ma 프로젝트의 **Board 앱 최종 기준(SSOT)**입니다.  
> 기능 추가/수정 시 본 지침을 기준으로 일관성을 유지해야 합니다.

---

## 0. 목적과 원칙

**목적**
- 운영 업무(요청/처리/이력/문서화)를 안정적으로 수행하는 핵심 앱

**핵심 원칙**
1. 보안 우선 (첨부/권한/CSRF)
2. 기능 변화 0 기본값 (리팩토링 시)
3. SSOT 재사용 (서비스/유틸/URL 네임)
4. View 얇게 · Service 두껍게
5. CSS No-Leak (스코프 격리)
6. 프론트 Boot 패턴 고정

---

## 1. 기능 범위

- Post(업무요청): 등록/상세/수정/목록/댓글/첨부
- Task(직원업무): superuser 전용 CRUD
- Inline Update: 상태/담당자 AJAX
- PDF: 업무요청서/FA소명서
- Industry Info: 업계기사 + 선호도/북마크/숨김

---

## 2. 디렉터리 구조 (FINAL)

```
board/
├── models.py
├── urls.py
├── views/
│   ├── __init__.py
│   ├── posts.py
│   ├── tasks.py
│   ├── forms.py
│   └── attachments.py
├── services/
│   ├── listing.py
│   ├── inline_update.py
│   ├── comments.py
│   └── attachments.py
├── templates/board/
│   ├── base_board.html
│   ├── post_*.html / task_*.html
│   ├── support_form.html / states_form.html
│   ├── includes/ (form/comment/inline/pagination)
│   └── partials/ (industry 카드/페이지네이션)
├── static/
│   ├── css/apps/board.css
│   └── js/
│       ├── board/*.js (entry)
│       └── common/*.js (공용)
└── templatetags/
```

---

## 3. URL 설계

### Post
- /board/posts/
- /board/posts/create/
- /board/posts/<id>/
- /board/posts/<id>/edit/
- /board/posts/attachments/<att_id>/download/

### Task (superuser)
- /board/tasks/...
- /board/tasks/attachments/<att_id>/download/

### Form/PDF
- /board/support-form/
- /board/states-form/
- /board/*/pdf/

---

## 4. 템플릿 규약

### 4.1 상속
```html
{% extends "board/base_board.html" %}
```

### 4.2 base_board.html
- base.html 상속
- board.css만 app_css 블록에서 로드
- 최상단에 `.board-scope` 필수

### 4.3 Include/Partial SSOT
- _form_common.html → 필드/첨부 UI
- _comment_form.html / _comment_list.html
- _inline_handler_status_list.html
- pagination.html
- industry partials

> 템플릿 주석은 반드시 `<!-- -->` 사용

---

## 5. 프론트엔드 규약

### 5.1 Boot 패턴
- root element + data-* 로 URL/권한 주입
- JS는 dataset만 사용

### 5.2 공용 모듈
- status_ui.js
- inline_update.js
- detail_inline_update.js
- comment_edit.js

### 5.3 엔트리 스크립트
- post_list/detail.js
- task_list/detail.js
- form_submit_lock.js (중복 제출 방지)
- industry_info.js (선호도/북마크)

### 5.4 필수 가드
- dataset.inited
- dataset.submitting
- BFCache pageshow reset

---

## 6. CSS 정책 (No-Leak)

파일: `static/css/apps/board.css`

- 모든 selector는 `.board-scope` 하위
- table: `table-layout: fixed + ellipsis`
- status UI: data-status 기반 색상
- comment UI: PC absolute / Mobile flow
- collateral/industry 전용 스코프 유지

---

## 7. 보안 설계 (CRITICAL)

### 7.1 첨부 다운로드
❌ 금지:
```html
<a href="{{ att.file.url }}">
```
✅ 필수:
```html
<a href="{% url 'board:post_attachment_download' att.id %}">
```
- View에서 권한 검증
- FileResponse
- RFC5987 파일명

### 7.2 업로드 정책
- 서버단 파일 크기 제한 필수
- 확장자 allowlist 권장
- 임시파일 정리

### 7.3 CSRF
- 모든 AJAX에 X-CSRFToken
- same-origin fetch

### 7.4 XSS
- |safe 금지
- 외부 URL 스킴 검증(http/https)

### 7.5 권한 정책
| 기능 | 권한 |
|------|------|
| Post | 로그인 |
| Task | superuser |
| Inline Update | superuser |
| support_form | superuser/head/leader |
| states_form | inactive 제외 |

---

## 8. 서비스 레이어 SSOT

| 기능 | 위치 |
|------|------|
| 목록/검색 | services/listing.py |
| 상태 변경 | services/inline_update.py |
| 댓글 | services/comments.py |
| 첨부 | services/attachments.py |

> View에서 비즈니스 로직 금지

---

## 9. 운영 체크리스트

- 첨부는 절대 direct URL 노출 금지
- media 전역 접근 정책 점검
- CSRF 쿠키 정상 발급
- 상태 변경 로그 추적 가능
- DataTables 정상 동작

---

## 10. 확장 원칙

- 기능 추가 → 기존 서비스 확장
- JS → common 모듈 재사용
- CSS → .board-scope 내부만
- URL name 유지 (reverse 깨짐 방지)

---

## 11. 회귀 위험 체크

- 권한 스코프 변경 여부
- 첨부 다운로드 정책 위반 여부
- dataset/DOM id 변경 여부
- JS 중복 바인딩 여부
- CSS 누수 여부

---

## 12. 최종 요약

Board 앱은 단순 게시판이 아니라 **운영 플랫폼**이다.

지켜야 할 5가지:

1. 첨부는 반드시 뷰 경유
2. View는 얇게, Service 중심
3. CSS는 완전 격리
4. JS는 Boot 패턴
5. 권한/보안은 절대 타협 금지

---

(END)
