# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**django_ma**는 보험 GA 조직을 위한 내부 운영 플랫폼이다. Django 5.2 / Python 3.13 / PostgreSQL / Redis / Celery 스택으로 구성된다.

## Common Commands

```bash
# 개발 서버
python manage.py runserver

# 마이그레이션
python manage.py makemigrations
python manage.py migrate

# 테스트 (전체)
python manage.py test

# 테스트 (단일 앱)
python manage.py test accounts
python manage.py test board.tests.SomeTestCase

# 정적 파일 수집
python manage.py collectstatic --noinput

# Celery worker (개발)
celery -A web_ma worker -l info

# Celery beat (스케줄러)
celery -A web_ma beat -l info

# 등록된 Celery 태스크 확인
celery -A web_ma inspect registered

# 빌드 (배포용)
bash build.sh
```

## Environment Setup

- 개발 환경: 프로젝트 루트의 `.env.dev` 파일 (`APP_ENV=dev` 자동 로드)
- 프로덕션: `docker/.env.prod`
- `APP_ENV` 환경변수로 환경 전환 (`dev` / `prod`)
- 인증 정보: `.env.dev`에 실제 값 포함 (커밋 금지)

Docker 전체 스택 실행:
```bash
docker-compose up
```
서비스: db(PostgreSQL 16), redis, web(gunicorn), celery worker, celery-beat, nginx

## Architecture

### 앱 구성

| 앱 | 역할 |
|---|---|
| `accounts` | CustomUser 모델, 사용자 관리, 엑셀 업/다운로드, 검색 API |
| `board` | 업무요청(Post), 직원업무(Task), WorkTask 월반복업무, PDF 서식 출력 |
| `commission` | 수수료/채권 관리 |
| `dash` | 매출 현황/예측 대시보드 (scikit-learn, LightGBM 사용) |
| `manual` | 업무 매뉴얼 지식 관리 (섹션/블록 구조, grade 기반 접근) |
| `partner` | 파트너/조직 관리 |
| `audit` | 요청 로깅 및 감사 추적 |
| `home`, `join` | 랜딩/회원가입 |
| `web_ma` | Django 프로젝트 설정 (`settings.py`, `celery.py`) |

### 레이어 구조

```
Browser → Template + Vanilla JS
       → View / API Wrapper
       → Service Layer (도메인 로직)
       → Policy / Rule Layer (SSOT)
       → Model → PostgreSQL / Redis
```

- **View**: HTTP 처리만 담당, 비즈니스 로직은 service로 분리
- **Service layer**: `board/services/`, `accounts/services/`에 공용 규칙 집중
- **SSOT 정책 위치**:
  - 사용자 검색: `accounts/search_api.py`
  - board 첨부 다운로드: `board/services/attachments.py`
  - manual 접근 권한: `manual/utils/permissions.py`
  - Celery 태스크명: `tasks.py`의 `@shared_task(name=)` 값이 SSOT

### View 패키지 구조 (manual, board)

앱 규모가 크면 `views/` 패키지로 분리하고 `__init__.py`에서 re-export한다:

```
manual/views/__init__.py  # urls.py 호환용 re-export (__all__ 포함)
manual/views/pages.py     # 화면 렌더링
manual/views/manual.py    # Manual AJAX
manual/views/section.py   # Section AJAX
manual/views/block.py     # Block AJAX
manual/views/attachment.py# Attachment AJAX
```

## User Grade System

| grade | 설명 | 로그인 |
|---|---|---|
| `superuser` | 시스템 최고 관리자 | 가능 |
| `head` | 파트너별 최상위 관리자 | 가능 |
| `leader` | 파트너별 중간 관리자 | 가능 |
| `basic` | 일반 사용자(설계사) | 가능 |
| `resign` | 퇴사자 | 가능(제한) |
| `inactive` | 비활성 | **불가** (`is_active=False` 강제) |

- 로그인 식별자: `USERNAME_FIELD = "id"` (사번)
- 권한 제어: `accounts/decorators.py`의 `grade_required` 데코레이터 사용

## Security Rules

1. **권한 판단은 항상 서버에서 최종 수행** — 템플릿/프론트엔드 체크는 참고용
2. **첨부 파일 URL 직접 노출 금지** — 반드시 다운로드 뷰를 경유해야 함
   - Post 첨부: `board:post_attachment_download`
   - Task 첨부: `board:task_attachment_download`
3. **사용자 검색 프론트 필터링 금지** — `accounts/search_api.py`를 통해서만 검색 결과 생성
4. **grade 변경 시 `inactive` → `is_active=False` 자동 반영** 확인 필요

## CSS Architecture

- `static/css/base.css`: 전역 토대/토큰/공통 UI
- `static/css/apps/board.css`: board 스코프 전용 (`.board-scope` 내부에서만 동작)
- `static/css/apps/manual.css`: manual 페이지 전용
- board CSS는 `board/templates/board/base_board.html`에서만 로드
- manual CSS는 `app_css` 템플릿 블록으로 해당 페이지에서만 로드
- 새 앱 CSS 추가 시 동일 패턴 준수

## Frontend Design Guidelines

새 페이지 제작 시 아래 패턴을 기준으로 한다. dash / partner / commission / manual 앱 분석을 기반으로 추출한 실제 컨벤션이다.

### 디자인 토큰 (base.css `:root`)

```css
--inka-blue: #005BAC       /* 브랜드 기본 파란색 */
--inka-blue2: #0074D9      /* 그라디언트용 */
--inka-blue-dark: #004B93

--bg-app: #f9fbfd          /* body 배경 */
--border-soft: #d2ddec     /* 일반 테두리 */

--shadow-card: 0 6px 15px rgba(0,0,0,0.1)
--shadow-soft: 0 2px 6px rgba(0,0,0,0.05)

--radius-card: 15px
--radius-soft: 10px
```

- 폰트: `Noto Sans KR`, base 16px
- body는 navbar(70px / 모바일 56px)만큼 `padding-top` 이미 적용됨

### 색상 팔레트 (앱 공통 관찰값)

| 용도 | 값 |
|---|---|
| 페이지 제목 / 섹션 제목 | `#003f7d` |
| 주요 링크 / active | `#005BAC` |
| 성공/완료 | `#198754` |
| 경고/주의 | `#b45309` |
| 위험/삭제/음수 | `#dc3545` |
| 테이블 헤더 배경 | `#f6f8fb` |
| 카드 배경 라이트 | `#f8f9fa` |
| 뮤트 텍스트 | `#6c757d` |
| 일반 테두리 | `#e9ecef` |

### 템플릿 기본 구조

```html
{% extends 'base.html' %}
{% load static %}

{% block title %}페이지명{% endblock %}

{% block app_css %}
<link rel="stylesheet" href="{% static 'css/apps/<앱명>.css' %}?v={% now 'U' %}">
{% endblock %}

{% block content %}
<div class="container my-4" id="<app>-root"
     data-fetch-url="{% url '<app>:<view>' %}"
     data-user-grade="{{ request.user.grade }}">

  <h3 class="fw-bold text-center mb-4" style="color:#003f7d">페이지 제목</h3>

  <!-- 1. 필터/컨트롤 카드 -->
  <!-- 2. 입력 섹션 (권한자 전용, 필요시) -->
  <!-- 3. 메인 데이터 섹션 -->

</div>
{% endblock %}

{% block extra_js %}
<script src="{% static 'js/<앱명>/<page>.js' %}?v={% now 'U' %}"></script>
{% endblock %}
```

- **`content_wrapper` 블록**: 와이드 레이아웃이 필요한 경우(`container-fluid` 직접 제어) 사용
- **URL / 권한은 `dataset`으로 주입** — JS 내 하드코딩 금지

### 카드 패턴

```html
<!-- 표준 카드 -->
<div class="card shadow p-3 border-0 rounded-4 mb-3">
  ...
</div>
```

`shadow p-3 border-0 rounded-4`가 전 앱 공통 스타일이다.

### 필터/컨트롤 카드 패턴

```html
<div class="card shadow p-3 border-0 rounded-4 mb-3">
  <form class="row g-2 align-items-end" id="controlsForm">
    <div class="col-6 col-md-2">
      <label class="form-label mb-1 fw-semibold">연도</label>
      <select class="form-select form-select-sm" id="yearSelect"></select>
    </div>
    <div class="col-6 col-md-2">
      <label class="form-label mb-1 fw-semibold">월</label>
      <select class="form-select form-select-sm" id="monthSelect"></select>
    </div>
    <div class="col-12 col-md-2 d-grid">
      <button type="button" class="btn btn-primary btn-sm" id="btnSearch">조회</button>
    </div>
  </form>
</div>
```

### 입력 섹션 헤더 패턴

```html
<div class="d-flex align-items-center mb-2">
  <h5 class="fw-bold mb-0" style="color:#003f7d">내용입력</h5>
  <div class="ms-auto d-flex gap-2">
    <button class="btn btn-outline-secondary btn-sm" id="btnReset">초기화</button>
    <button class="btn btn-success btn-sm" id="btnSave">저장</button>
  </div>
</div>
```

### 테이블 패턴

```html
<!-- 표준 데이터 테이블 -->
<div class="table-responsive">
  <table class="table table-sm table-bordered align-middle" id="mainTable">
    <colgroup>
      <col class="c-no">   <!-- width: 48px -->
      <col class="c-name"> <!-- width: 120px -->
      <col>                <!-- 나머지 -->
    </colgroup>
    <thead class="table-light">
      <tr><th>번호</th><th>이름</th><th>내용</th></tr>
    </thead>
    <tbody></tbody>
  </table>
</div>
```

- 컬럼 폭은 `colgroup`의 CSS 클래스로 제어 (`table-layout: fixed` 병행)
- 금액 컬럼: `class="text-end"` (우측 정렬) + `white-space: nowrap`
- 음수 금액: `class="text-end text-danger fw-semibold"`
- 긴 텍스트 컬럼: `overflow: hidden; text-overflow: ellipsis; white-space: nowrap`
- 가로 스크롤 래퍼: `<div class="table-responsive">` 또는 커스텀 클래스 `<앱명>-table-scroll`

### 버튼 사용 규칙

| 용도 | 클래스 |
|---|---|
| 주요 CTA (조회/저장) | `btn btn-primary` |
| 보조 액션 (초기화/취소) | `btn btn-outline-secondary` |
| 성공/완료 | `btn btn-success` |
| 삭제/위험 | `btn btn-outline-danger` 또는 `btn btn-danger` |
| 테이블 내 버튼 | `btn-sm` 필수 |
| 전체폭 버튼 | `d-grid` 래퍼 + `btn` |

### 모달 패턴

```html
<div class="modal fade" id="someModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered modal-lg">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title fw-bold">제목</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <!-- 내용 -->
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">취소</button>
        <button type="button" class="btn btn-primary btn-sm" id="btnModalSave">확인</button>
      </div>
    </div>
  </div>
</div>
```

### 로딩 오버레이 패턴

```html
<div id="loadingOverlay" hidden
     style="position:fixed;inset:0;background:rgba(255,255,255,.6);z-index:9999;display:flex;align-items:center;justify-content:center;">
  <div class="spinner-border text-primary" role="status"></div>
</div>
```

JS: `loadingOverlay.hidden = false` / `true`로 토글

### CSS 스코핑 규칙

```css
/* apps/<앱명>.css — 항상 루트 ID 하위로 스코핑 */
#<app>-root .my-component { ... }
#<app>-root .c-no { width: 48px; }

/* CSS 변수로 반복값 관리 */
#<app>-root {
  --tbl-font: 13px;
  --col-name: 160px;
}
```

- **전역 스타일 추가 금지** — `base.css`는 건드리지 않음
- 앱 전용 CSS는 반드시 `static/css/apps/<앱명>.css`에 작성
- `base.html`의 `:root` 토큰(`--inka-blue` 등)은 자유롭게 참조 가능

### CSS 클래스 네이밍

| 패턴 | 예시 | 용도 |
|---|---|---|
| 앱 접두어 | `dr-`, `rm-`, `eff-` | 앱/기능 스코프 |
| BEM 변형 | `component__element` | 구조적 하위 요소 |
| 상태 | `.is-open`, `.is-ok`, `.is-err` | JS 토글 상태 |
| JS 훅 | `.js<Name>` | JS가 선택하는 요소 |
| 컬럼 폭 | `.c-rank`, `.c-branch` | `colgroup` col 폭 |

### JavaScript 아키텍처

**기본 구조 (모든 JS는 전역 오염 방지):**

```javascript
// IIFE 패턴 (단일 파일, 소규모)
(function () {
  "use strict";
  const root = document.getElementById("<app>-root");
  if (!root) return;
  if (root.dataset.inited === "1") return; // BFCache 방지
  root.dataset.inited = "1";

  const URLS = {
    fetch: root.dataset.fetchUrl,
    save:  root.dataset.saveUrl,
  };

  // 이벤트 바인딩
  // ...
})();

// ESM 패턴 (복잡한 페이지, type="module")
// index.js → dom_refs.js, fetch.js, save.js 등으로 분리
```

**AJAX 표준 패턴:**

```javascript
// GET
const res = await fetch(URLS.fetch + "?" + new URLSearchParams(params), {
  credentials: "same-origin",
  headers: { "X-Requested-With": "XMLHttpRequest" },
});
const json = await res.json();
// 응답 형식: { ok: true|false, message: "...", data: {...} }

// POST
const res = await fetch(URLS.save, {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRFToken": getCsrf(),
  },
  body: JSON.stringify(payload),
});
```

**CSRF 토큰 읽기 (RULE-Q-01 — 반드시 공통 유틸 사용):**

```javascript
// ESM 파일 (type="module"):
import { getCSRFToken } from "../../common/manage/csrf.js";

// IIFE 파일 (일반 <script>):
const csrf = window.csrfToken || getCSRFToken();
// window.csrfToken은 csrf_window.js가 주입, getCSRFToken은 common/manage/csrf.js SSOT
```

> ⚠️ 위 패턴처럼 `getCsrf()` / `getCookie()` 를 파일마다 재구현하는 것은 **금지**다 (RULE-Q-01).

**이벤트 위임 (동적 요소 처리):**

```javascript
root.addEventListener("click", (e) => {
  const btn = e.target.closest(".btn-delete-row");
  if (!btn) return;
  // 처리
});
```

**숫자 포맷:**

```javascript
const comma = (v) => (v == null || v === "" ? "-" : Number(v).toLocaleString("ko-KR"));
const percent = (v) => (v == null ? "-" : Number(v).toFixed(1) + "%");
```

Django 템플릿에서는 `{{ value|intcomma }}`.

### 데이터 전달 패턴

서버 → JS 데이터 전달은 두 가지 방식을 사용한다:

```html
<!-- 방식 1: dataset 속성 (URL, grade, 단순값) -->
<div id="app-root"
     data-fetch-url="{% url 'app:api_view' %}"
     data-user-grade="{{ request.user.grade }}"
     data-user-branch="{{ request.user.branch }}">

<!-- 방식 2: json_script 태그 (초기 데이터 bulk) -->
{{ boot_data|json_script:"boot-data" }}
```

```javascript
// 방식 2 읽기
const bootData = JSON.parse(document.getElementById("boot-data").textContent || "{}");
```

### 반응형 Breakpoints

| 기준 | 내용 |
|---|---|
| `576px` 이하 | 모바일: 필터 wrap, 테이블 min-width 고정 후 가로 스크롤 |
| `768px` 이하 | 태블릿: 일부 카드 1열, 테이블 `table-layout: auto` |
| `1200px` 이상 | 데스크톱: 필터 가로 배치, 2열 그리드 |

### 권한별 UI 분기

```html
{# 템플릿: 입력 섹션 표시 여부 #}
{% if user.grade == 'superuser' or user.grade == 'head' %}
  <div id="inputSection">...</div>
{% endif %}
```

```javascript
// JS: dataset으로 추가 제어 (readonly 등)
if (root.dataset.userGrade === "basic") {
  document.getElementById("inputSection")?.remove();
}
```

### 금액/숫자 표시 규칙

- 금액 컬럼: 우측 정렬 `.text-end` + `white-space: nowrap`
- 음수: `color: #dc3545; font-weight: 600`
- 값 없음: `-` 표시 (빈 문자열 / null 모두 처리)
- Django 템플릿: `{{ amount|intcomma }}`
- JS 렌더링: `Number(v).toLocaleString("ko-KR")`

### 캐시 버스팅

```html
<link rel="stylesheet" href="{% static 'css/apps/<앱명>.css' %}?v={% now 'U' %}">
<script src="{% static 'js/<앱명>/<file>.js' %}?v={% now 'U' %}"></script>
```

고정 배포용은 `?v=YYYYMMDD-XX` 형식도 허용.

### 공용 컴포넌트 (재사용 가능)

| 컴포넌트 | 위치 | 용도 |
|---|---|---|
| 사용자 검색 모달 | `templates/components/search_user_modal.html` | 모든 앱에서 재사용 |
| 부서/지점 연쇄 선택 | `static/js/common/part_branch_selector.js` | 계층적 필터 |
| CSRF window 노출 | `static/js/common/csrf_window.js` | `window.csrfToken` |
| JSON boot bridge | `static/js/common/json_boot_bridge.js` | json_script → window 노출 |

## Celery Beat Schedule (SSOT: `web_ma/celery.py`)

| 태스크 | 주기 |
|---|---|
| `board.tasks.industry_info.collect_board_industry_news` | 6시간 (00:05, 06:05, 12:05, 18:05) |
| `board.tasks.industry_info.cleanup_old_industry_articles` | 매일 03:00 |
| `dash.tasks.build_sales_aggs_hourly` | 매시 :10 |
| `dash.tasks.build_sales_forecasts_daily` | 매일 02:10 |
| `dash.tasks.build_sales_forecasts_hourly` | 매시 :20 |
| `board.tasks.generate_monthly_worktasks` | 매달 1일 00:10 |
| `board.tasks.notify_due_worktasks` | 매일 08:00 |

- `board/tasks/`는 패키지 구조이므로 `celery.py`에서 명시적으로 `autodiscover_tasks(["board.tasks"])` 추가
- beat_schedule의 `"task"` 값은 `@shared_task(name=)` 등록명과 **정확히 일치**해야 함 (불일치 시 에러 없이 묵묵히 실패)

## Documentation

자세한 설계 결정 사항은 `/docs/`를 참조:
- `00_overview.md` — 프로젝트 목적, 앱 범위, 기술 스택
- `01_architecture.md` — 레이어 구조, 앱별 아키텍처 패턴
- `03_auth_and_permission.md` — 인증/권한 정책 상세
- `04_background_tasks.md` — Celery 작업 설명
- `05_deployment.md` — 배포 가이드
- `99_troubleshooting.md` — 트러블슈팅

---

## 0. 이 프로젝트에서 실제 발견된 위반 패턴 (NEVER DO)

> 출처: `docs/harness/NEVER_DO.md` | 기준 커밋: 5e7e7f1

- [ ] `partner/views/subadmin.py` 에서 `u.grade = "leader"` / `target.grade = "basic"` 저장 후 `log_action()` 미호출 금지 → `log_action(request, ACTION.PARTNER_LEADER_ADD/DELETE, obj=u)` 필수 (S-B-05)

- [ ] `accounts/tasks.py` 의 `process_users_excel_task()` 완료 분기에서 `log_action()` 미호출 금지 → `log_action(None, ACTION.ACCOUNTS_EXCEL_UPLOAD, meta={...})` 추가 (S-B-06)

- [ ] `commission/views/api_upload.py`, `commission/views/approval.py` 에서 `@csrf_exempt` 사용 금지 → 프론트엔드 JS에서 `X-CSRFToken` 헤더 또는 FormData `csrfmiddlewaretoken` 필드 포함으로 대체 (S-D-01)

- [ ] `audit/constants.py` 에 미정의된 `ACTION.XXX` 상수를 `log_action()` 인자로 전달 금지 → 상수를 먼저 `audit/constants.py` 에 추가하거나 기존 상수 재활용 (S-E-01 / S-E-04)

---

## 1. 작업 시작 전 필수 확인 파일

코드 작업 요청을 받으면, 아래 파일을 반드시 먼저 읽어라:

- `docs/harness/HARNESS_RULES.md` — 보안 규칙 (audit 로그, CSRF, ACTION 상수)
- `docs/harness/QUALITY_RULES.md` — 품질 규칙 (CSRF SSOT, CSS 스코핑, JSON 헬퍼 중복)
- 해당 앱의 `guide_*.md` — 앱별 규약 (존재하는 경우)

---

## 2. 작업 유형별 의무 체크리스트

### 2-A. 뷰 함수 추가/수정 시

- [ ] `@login_required` 또는 `@grade_required` 데코레이터 있는가
- [ ] AJAX 뷰는 `forbidden_template=None` 있는가
- [ ] 비즈니스 로직이 service 레이어에 있는가
- [ ] 파일 다운로드 뷰는 권한 검증 + `FileResponse`인가
- [ ] JSON 응답 형식이 해당 앱 규약(`ok`/`status`)과 일치하는가
- [ ] 감사 로그(`log_action`)가 필요한 행위인가 (grade 변경 · 엑셀 업로드 · 결재 등은 필수)

### 2-B. 엑셀 업로드 기능 추가/수정 시

- [ ] `save_attachments()` 또는 registry SSOT 경유하는가
- [ ] `_norm_emp_id()` 사번 정규화 적용하는가
- [ ] `bulk_create` / `update_or_create` 사용하는가 (row-by-row `save` 금지)
- [ ] `transaction.atomic()` 으로 감싸여 있는가
- [ ] 임시파일 `try/finally` 정리 있는가
- [ ] 완료 분기에 `log_action()` 호출이 있는가 (RULE-S-02)

### 2-C. JS 파일 추가/수정 시

- [ ] AJAX URL이 `dataset`에서 읽는가 (하드코딩 금지)
- [ ] BFCache 가드(`dataset.inited`) 있는가
- [ ] CSRF는 `common/manage/csrf.js` `getCSRFToken()` 사용하는가 (파일 내 재구현 금지 — RULE-Q-01)
- [ ] `fetch` 응답은 `common/manage/http.js` `readJsonOrThrow()` 사용하는가
- [ ] 중복 바인딩 방지 가드 있는가

### 2-D. CSS 추가/수정 시

- [ ] 해당 앱의 스코프 루트 선택자 하위에만 규칙이 있는가
- [ ] `base.css` 수정이 없는가
- [ ] `fixes.css`에 앱 전용 규칙을 추가하지 않았는가
- [ ] CSS 변수를 `:root` 전역이 아닌 앱 루트 ID 하위에 선언했는가 (RULE-Q-02)
- [ ] 스코프 없는 전역 클래스(`.info-table` 등)를 추가하지 않았는가 (RULE-Q-02)

### 2-E. Celery task 추가/수정 시

- [ ] `@shared_task(name="...")` 이름이 `beat_schedule` `"task"` 값과 **정확히** 일치하는가
- [ ] 멱등성 보장(`update_or_create` / unique key)되어 있는가
- [ ] `board/tasks/` 패키지면 `autodiscover_tasks(["board.tasks"])` 등록되어 있는가

---

## 3. 회귀 위험 자동 점검 (패치 후 반드시 실행)

코드 패치 후 아래 9가지를 명시적으로 점검하고 결과를 응답에 포함하라:

- [ ] 권한 스코프 변경 여부
- [ ] URL reverse / 네임스페이스 깨짐 여부
- [ ] 템플릿 `dataset` / DOM id 변경 여부
- [ ] 첨부 다운로드 정책 위반 여부
- [ ] 업로드 레지스트리/컬럼 탐지 영향 여부
- [ ] DataTables 정책 깨짐 여부
- [ ] CSS 스코프 누수 가능성
- [ ] 운영 환경(`Manifest` / `SECURE_SSL_REDIRECT`) 영향 여부
- [ ] JSON 응답 형식 앱 규약 준수 여부

> 기존 CLAUDE.md 내용과 충돌하는 경우 **더 엄격한 규칙**이 우선한다.
