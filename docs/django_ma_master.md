# django_ma Master Guide

> **목적**: 외부 LLM이 처음 이 프로젝트를 읽을 때 "전체 맥락 → 앱별 상세" 순으로 파악할 수 있도록 통합한 단일 참조 문서.  
> **기준 커밋**: develop 브랜치 (2026-05-03)  
> **상세 문서 위치**: `docs/apps/guide_<앱명>.md`, `docs/common/frontend_guide.md`, `docs/common/infra_guide.md`

---

## 목차 (TOC)

1. [프로젝트 개요](#1-프로젝트-개요)
2. [앱 구성 한눈에 보기](#2-앱-구성-한눈에-보기)
3. [Grade 등급 체계 (전체 공통)](#3-grade-등급-체계-전체-공통)
4. [공통 아키텍처 원칙](#4-공통-아키텍처-원칙)
5. [공통 보안 정책 SSOT](#5-공통-보안-정책-ssot)
6. [인프라 요약](#6-인프라-요약)
7. [Frontend 공통 요약](#7-frontend-공통-요약)
8. [앱 간 의존 관계 지도](#8-앱-간-의존-관계-지도)
9. [앱별 요약](#9-앱별-요약)
   - [accounts](#91-accounts)
   - [board](#92-board)
   - [commission](#93-commission)
   - [dash](#94-dash)
   - [manual](#95-manual)
   - [partner](#96-partner)
10. [신규 기능 추가 시 공통 체크리스트](#10-신규-기능-추가-시-공통-체크리스트)
11. [LLM 공통 함정 포인트](#11-llm-공통-함정-포인트)

---

## 1. 프로젝트 개요

**django_ma**는 보험 GA(General Agency) 조직을 위한 내부 운영 플랫폼이다.

| 항목 | 값 |
|---|---|
| 프레임워크 | Django 5.2 / Python 3.13 |
| DB | PostgreSQL 16 |
| 캐시/메시지 브로커 | Redis |
| 비동기 태스크 | Celery + Celery Beat |
| ML | scikit-learn, LightGBM (dash 앱) |
| 배포 | Docker Compose (nginx + gunicorn + uvicorn) |
| 정적 파일 | WhiteNoise (prod), Django 기본 서빙 (dev) |

### 1-1. 로그인 식별자

`USERNAME_FIELD = "id"` — 사원번호(7자리)가 PK이자 로그인 식별자다.  
`request.user.username`은 존재하지 않는다. 반드시 `request.user.id`를 사용한다.

---

## 2. 앱 구성 한눈에 보기

| 앱 | 역할 | 주요 모델 | 상세 가이드 |
|---|---|---|---|
| `accounts` | CustomUser 모델, 인증, 계정 잠금, 강제 비밀번호 변경, 엑셀 대량 업로드 | `CustomUser` | `docs/apps/guide_accounts.md` |
| `board` | 업무요청(Post), 직원업무(Task), 개인업무관리(WorkTask), 담보평가, 업계정보 | `Post`, `Task`, `WorkTask`, `CollateralEval`, `IndustryArticle` | `docs/apps/guide_board.md`, `docs/apps/board_worktask_guide.md` |
| `commission` | 채권현황(Deposit), 수수료 결재(Approval), 환수관리(Collect) | `DepositSummary`, `CollectRecord`, `CollectFeedback` | `docs/apps/guide_commission.md` |
| `dash` | 매출 현황/예측 대시보드, 유지율 대시보드 | `SalesRecord`, `SalesDailyAgg`, `SalesForecast`, `RetentionRecord` | `docs/apps/guide_dash.md` |
| `manual` | Quill 기반 업무 매뉴얼 지식 관리 | `Manual`, `ManualSection`, `ManualBlock`, `ManualBlockAttachment` | `docs/apps/guide_manual.md` |
| `partner` | 편제변경, 요율변경, 지점효율, 권한관리, 전자서명 | `RateChange`, `StructureChange`, `EfficiencyChange`, `SubAdminTemp`, `EfficiencySignRequest` | `docs/apps/guide_partner.md` |
| `audit` | 요청 로깅 및 감사 추적 | `AuditLog` | (별도 가이드 없음) |
| `home`, `join` | 랜딩/회원가입 | — | — |

---

## 3. Grade 등급 체계 (전체 공통)

**SSOT**: `accounts/models.py` `GRADE_CHOICES`

| grade | 설명 | is_active | 로그인 | Django Admin |
|---|---|---|---|---|
| `superuser` | 시스템 최고 관리자 | True | 가능 | ✅ (CustomAdminSite) |
| `head` | 파트너별 최상위 관리자 | True | 가능 | ❌ |
| `leader` | 파트너별 중간 관리자 | True | 가능 | ❌ |
| `basic` | 일반 사용자(설계사) | True | 가능 | ❌ |
| `resign` | 퇴사자 | True | 가능(기능 제한) | ❌ |
| `inactive` | 비활성 | **False 강제** | **불가** | ❌ |

### Grade별 주요 기능 접근 범위

| 기능 | superuser | head | leader | basic | resign | inactive |
|---|---|---|---|---|---|---|
| 사용자 검색 | 전체 | 본인 지점 | 팀 범위 | 자신만 | 자신만 | 자신만(로그인 불가) |
| Board Post 조회 | 전체 | 본인+지점 | 본인만 | 본인만 | 본인만 | 차단 |
| WorkTask | ✅ (본인 소유) | ❌ | ❌ | ❌ | ❌ | ❌ |
| Manual 편집 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Manual 조회(공개) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Partner 관리 | ✅ | ✅ (본인 지점) | ✅ (팀 범위) | ❌ | ❌ | ❌ |
| dash 대시보드 | ✅ | ✅ (본인 지점) | ❌ | ❌ | ❌ | ❌ |
| commission Collect | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |

### 운영 정책 ⚠️

```python
# accounts/models.py CustomUser.save() 오버라이드
# grade="inactive" 저장 시 is_active=False 자동 강제
user.grade = "inactive"
user.save()  # is_active=False 자동 설정

# ❌ 금지: bulk update는 save()를 우회하므로 is_active 동기화 안 됨
CustomUser.objects.filter(...).update(grade="inactive")
```

---

## 4. 공통 아키텍처 원칙

### 4-1. 레이어 구조

```
Browser → Template + Vanilla JS
       → View / API Wrapper
       → Service Layer (도메인 로직)
       → Policy / Rule Layer (SSOT)
       → Model → PostgreSQL / Redis
```

- **View**: HTTP 처리만 담당. 비즈니스 로직은 service로 분리.
- **Service layer**: ORM 조작·도메인 규칙 집중. 뷰에서 ORM 직접 접근 금지.
- **Policy**: 권한 판단 로직의 단일 진실 소스. 인라인 grade 비교 금지.

### 4-2. View 패키지 구조

앱 규모가 크면 `views/` 패키지로 분리하고 `__init__.py`에서 re-export:

```
board/views/__init__.py  # urls.py 호환용 re-export (__all__ 포함)
board/views/posts.py
board/views/worktasks.py
...
```

### 4-3. JSON 응답 형식 — 앱별 차이 ⚠️

| 앱 | 성공 응답 | 실패 응답 |
|---|---|---|
| `board`, `manual`, `accounts`, `commission`, `dash` | `{"ok": true, ...}` | `{"ok": false, "message": "..."}` |
| `partner` | `{"status": "success", ...}` | `{"status": "error", "message": "..."}` |

**JS에서 partner 응답을 `result.ok`로 판단하거나, board 응답을 `result.status === "success"`로 판단하면 안 된다.**

### 4-4. URL 네임스페이스

| 앱 | namespace | prefix |
|---|---|---|
| `accounts` | `accounts` | `/accounts/` |
| `board` | `board` | `/board/` |
| `board` WorkTask | `board:worktasks` (중첩) | `/board/worktasks/` |
| `commission` | `commission` | `/commission/` |
| `dash` | `dash` | `/dash/` |
| `manual` | `manual` | `/manual/` |
| `partner` | `partner` | `/partner/` |
| 로그인 | (네임스페이스 없음) | `/login/` |

> ⚠️ `{% url 'login' %}` — `accounts:login`이 아님. `web_ma/urls.py`에서 직접 등록됨.

---

## 5. 공통 보안 정책 SSOT

**자세한 내용**: `docs/common/security_guide.md`

### 5-1. 뷰 접근 제어 — `grade_required`

```python
# SSOT: accounts/decorators.py
from accounts.decorators import grade_required

@grade_required("head")                      # 단일
@grade_required("head", "leader")           # 복수
@grade_required("superuser", forbidden_template=None)  # AJAX 뷰 — 403 반환
```

- 내부적으로 `@login_required`가 먼저 적용된다.
- `forbidden_template` 기본값: `"no_permission_popup.html"` (HTML 응답) → AJAX 뷰에서는 `forbidden_template=None` 필수.

### 5-2. 파일 다운로드 보안 ⚠️

```html
<!-- ❌ 금지: storage URL 직접 노출 -->
<a href="{{ att.file.url }}">

<!-- ✅ 올바른 방법: 다운로드 뷰 경유 -->
<a href="{% url 'board:post_attachment_download' att.id %}">
<a href="{% url 'board:task_attachment_download' att.id %}">
<a href="{% url 'board:worktasks:worktask_att_download' att.id %}">
<a href="{% url 'manual:manual_attachment_download' att.id %}">
<a href="{% url 'partner:efficiency_confirm_attachment_download' att.id %}">
```

**다운로드 뷰 내부 SSOT**: `board/services/attachments.py:open_fileresponse_from_fieldfile()` — RFC5987 한글 파일명, 핸들 close 보장.

### 5-3. 사용자 검색 권한 스코프 ⚠️

**SSOT**: `accounts/search_api.py:search_users_for_api(request)`

```python
# ❌ 금지: 권한 스코프 없음
CustomUser.objects.filter(name__icontains=q)

# ✅ 올바른 방법
from accounts.search_api import search_users_for_api
result = search_users_for_api(request)
# 또는 JS에서 {% url 'accounts:api_search_user' %} 호출
```

### 5-4. 감사(Audit) 로그 ⚠️

**로그를 남겨야 하는 행위**: 로그인/로그아웃, 파일 업로드/다운로드, grade 변경, 비밀번호 변경, Post/Task/Manual/Partner CRUD 전체

```python
from audit.services import log_action
from audit.constants import ACTION

# log_action 실패가 사용자 동작을 막으면 안 된다 → try/except 필수
try:
    log_action(request, ACTION.BOARD_ATTACHMENT_DOWNLOAD, obj=att, success=True)
except Exception:
    pass
```

### 5-5. Post/Task 권한 정책 SSOT

**board 앱 전용**: `board/policies.py`

| 함수 | 정책 |
|---|---|
| `can_view_post(user, post)` | superuser: 전체 / head: 본인+지점 / leader: 본인만 |
| `can_edit_post(user, post)` | superuser + 작성자만 |
| `can_download_post_attachment(user, att)` | `can_view_post` 결과와 동일 |
| `can_download_task_attachment(user, att)` | superuser 전용 |

뷰에서 직접 grade를 비교해 board 조회 정책을 구현하면 안 된다.

### 5-6. Manual 접근 정책 SSOT

**manual 앱 전용**: `manual/utils/permissions.py`

| 함수 | 역할 |
|---|---|
| `filter_manuals_for_user(qs, user)` | 목록 노출 정책 — 반드시 경유 |
| `manual_accessible_or_denied(request, manual)` | 상세 접근 정책 — 반드시 경유 |

```python
# ❌ 금지: admin_only 필터 누락
qs = Manual.objects.filter(is_published=True)

# ✅ 올바른 방법
qs = filter_manuals_for_user(Manual.objects.all(), request.user)
```

---

## 6. 인프라 요약

**상세 문서**: `docs/common/infra_guide.md`

### 6-1. 환경 분리

```python
IS_PROD = APP_ENV in ("prod", "production") and not DEBUG
```

- dev: `.env.dev`, `LocMemCache`, DEBUG=True
- prod: `docker/.env.prod`, `RedisCache`, `CompressedManifestStaticFilesStorage`

**Fail-fast Rails**: `prod+DEBUG=True`, `dev+runserver+DEBUG=False`, `dev+host=db`, `DEBUG=True+prod DB URL` → 즉시 `RuntimeError`.

### 6-2. 정적 파일

```bash
# 배포 전 반드시 실행 (코드 변경 후 매번)
python manage.py collectstatic --noinput
```

prod에서 `staticfiles.json` manifest가 없으면 서버 기동 실패.  
개발 시 `?v={% now 'U' %}`로 캐시 버스팅 (manifest hash 우회 금지).

### 6-3. Celery Beat Schedule

**SSOT**: `web_ma/celery.py`

| 태스크 | 주기 |
|---|---|
| `board.tasks.industry_info.collect_board_industry_news` | 6시간 |
| `board.tasks.industry_info.cleanup_old_industry_articles` | 매일 03:00 |
| `board.tasks.generate_monthly_worktasks` | 매달 1일 00:10 |
| `board.tasks.notify_due_worktasks` | 매일 08:00 |
| `dash.tasks.build_sales_aggs_hourly` | 매시 :10 |
| `dash.tasks.build_sales_forecasts_daily` | 매일 02:10 |
| `dash.tasks.build_sales_forecasts_hourly` | 매시 :20 |

**중요 규칙**:
- `beat_schedule`의 `"task"` 값은 `@shared_task(name=...)` 등록명과 **정확히 일치**해야 함 (불일치 시 에러 없이 묵묵히 실패)
- `CELERY_TASK_ACKS_LATE=True` → at-least-once, 모든 태스크는 멱등성 보장 필요
- `board/tasks/`는 패키지 구조 → `autodiscover_tasks(["board.tasks"])` 명시적 호출 필수

### 6-4. Celery 진행률 캐시 계약

Celery 태스크에서 진행률을 캐시에 쓸 때:

```python
cache.set(f"upload_progress:{task_id}", percent)   # int 0~100
cache.set(f"upload_status:{task_id}", status)       # "PROGRESS"/"SUCCESS"/"FAILURE"
cache.set(f"upload_error:{task_id}", error_msg)     # 실패 메시지
cache.set(f"upload_result_path:{task_id}", path)    # 결과 파일 경로
```

**개발 환경 주의**: `LocMemCache`는 프로세스 공유가 안 되므로 Celery worker가 쓴 캐시를 Django dev server에서 읽지 못한다. 진행률 폴링은 prod(Redis) 또는 별도 Redis 연결 환경에서만 정상 동작한다.

---

## 7. Frontend 공통 요약

**상세 문서**: `docs/common/frontend_guide.md`

### 7-1. CSS 스코핑 원칙 ⚠️

- 모든 앱 전용 CSS는 **반드시 앱 루트 선택자 하위**에서만 동작하도록 스코핑
- `base.css` 수정 금지 — 전역 오염 발생

| 앱 | CSS 파일 | 루트 선택자 |
|---|---|---|
| board | `apps/board.css` | `.board-scope` |
| partner | `apps/partner.css` | `#manage-structure`, `#manage-rate`, `#manage-efficiency`, `#esign-confirm`, `#manage-grades`, `#manage-table` |
| commission | `apps/commission.css` | `#deposit-home`, `#collect-home`, `#approval-home` |
| dash | `apps/dash.css` | `#dash-sales`, `.dash-retention-root` |
| manual | `apps/manual.css` | `#manual-detail`, `.manual-list-container` |

> ⚠️ board는 `base_board.html`이 `.board-scope` 래퍼를 자동 주입한다. 새 board 페이지는 반드시 `board/base_board.html`을 extends해야 한다.

### 7-2. JS URL 주입 원칙

**모든 AJAX URL은 template dataset으로 주입. JS 내 하드코딩 금지.**

```html
<div id="app-root"
     data-fetch-url="{% url 'app:api_view' %}"
     data-save-url="{% url 'app:save_view' %}"
     data-user-grade="{{ request.user.grade }}">
```

```javascript
const URLS = {
    fetch: root.dataset.fetchUrl,
    save: root.dataset.saveUrl,
};
```

### 7-3. BFCache 가드 패턴

페이지가 뒤로가기로 복원될 때 JS가 중복 초기화되지 않도록:

```javascript
// 방법 1: root dataset flag
if (root.dataset.inited === "1") return;
root.dataset.inited = "1";

// 방법 2: pageshow 이벤트 (collect_home.js, dash_retention_page.js 패턴)
window.addEventListener("pageshow", (e) => {
    if (e.persisted) root.dataset.inited = "";
});
```

### 7-4. 공통 CSRF 토큰

```javascript
// SSOT: static/js/common/manage/csrf.js
import { getCSRFToken } from "/static/js/common/manage/csrf.js";
// 우선순위: window.csrfToken → [name=csrfmiddlewaretoken] → csrftoken cookie
```

### 7-5. Partner 관리 페이지 공통 초기화

partner 관리 페이지는 `manage_boot.js`와 `part_branch_selector.js`가 협력한다:

```javascript
// partner 관리 페이지 index.js (type="module")
import { initManageBoot } from "/static/js/common/manage_boot.js";

const ctx = initManageBoot("efficiency"); // "structure" | "rate" | "efficiency" | "grades" | "table"
if (!ctx) return;
const { root } = ctx;
// superuser는 part_branch_selector.js에 위임됨 (자동)
// head/leader는 autoLoad payload 자동 준비
```

`initManageBoot`는 **fetch를 실행하지 않는다**. 실제 조회는 `window.__manageBootAutoPayload[ctxName]`을 읽어 index.js가 수행.

### 7-6. 공용 사용자 검색 모달

```html
<!-- 템플릿에 include -->
{% include 'components/search_user_modal.html' %}

<!-- data-search-url을 inject -->
<button data-search-url="{% url 'accounts:api_search_user' %}" class="btnOpenSearch">검색</button>
```

```javascript
// userSelected 이벤트 수신
document.addEventListener("userSelected", (e) => {
    const { id, name, branch } = e.detail;
    // 처리
});
```

> ⚠️ **`deposit-home` 예외**: `deposit-home` 루트에서는 `userSelected` 이벤트를 dispatch하지 않고 즉시 `location.href = /commission/deposit/?user=<id>`로 리다이렉트한다.

---

## 8. 앱 간 의존 관계 지도

```
accounts ←── (모든 앱) : CustomUser FK, grade_required, search_api
    ↑
    └── partner : SubAdminTemp (grade 변경 시 accounts.signals가 자동 동기화)

audit ←── board, manual, partner, commission, dash, accounts
         (log_action 호출)

board ──→ accounts (grade_required, search_api)
board ──→ audit (log_action)

manual ──→ accounts (grade_required, not_inactive_required)
manual ──→ audit (log_action)

partner ──→ accounts (grade_required, CustomUser FK)
partner ──→ audit (log_action)
accounts ──→ partner (SubAdminTemp — search_api에서 리더 팀 범위 조회)

commission ──→ accounts (grade_required, search_api URL)
commission ──→ audit (log_action)

dash ──→ accounts (grade_required, CustomUser FK)
dash ──→ audit (log_action)
```

### 핵심 의존 SSOT

| 기능 | SSOT 위치 |
|---|---|
| 사용자 등급 권한 | `accounts/decorators.py:grade_required` |
| 사용자 검색 범위 | `accounts/search_api.py:search_users_for_api` |
| board 첨부 다운로드 | `board/services/attachments.py:open_fileresponse_from_fieldfile` |
| board 조회/수정 권한 | `board/policies.py` |
| WorkTask 소유자 격리 | `board/services/worktasks.py:get_user_queryset`, `get_user_task` |
| manual 목록/상세 권한 | `manual/utils/permissions.py` |
| partner branch 스코프 | `partner/views/utils.py:resolve_branch_for_query`, `resolve_branch_for_write` |
| Collect 서비스 전체 | `commission/services/collect.py` |
| SalesDailyAgg 생성 | `dash/services/agg.py:build_daily_agg_for_month` |
| LightGBM 예측 모델 | `dash/ml/forecast.py` |
| Celery beat schedule | `web_ma/celery.py` |
| IS_PROD 판단 | `web_ma/settings.py:IS_PROD` |

---

## 9. 앱별 요약

### 9-1. accounts

**상세**: `docs/apps/guide_accounts.md`

#### 핵심 책임

- `CustomUser` 모델 (PK = 사원번호 `id`)
- 로그인(`SessionCloseLoginView`), 계정 잠금(`is_locked`), 강제 비밀번호 변경(`must_change_password`)
- 사용자 검색 SSOT (`search_api.py`)
- 엑셀 대량 업로드 → Celery (`process_users_excel_task`)

#### 주요 SSOT

| 파일 | 역할 |
|---|---|
| `accounts/models.py:CustomUser.save()` | `inactive → is_active=False` 자동 강제 |
| `accounts/decorators.py:grade_required` | 전체 앱의 뷰 접근 제어 |
| `accounts/search_api.py:search_users_for_api` | 사용자 검색 권한 스코프 |
| `accounts/policies/password_policy.py:should_enforce` | 강제 비밀번호 변경 미들웨어 판단 엔진 |
| `accounts/constants.py` | Lockout 상수(`LOGIN_FAIL_MAX_COUNT=5`), 캐시 키 접두어 |

#### 주요 함정

- `CustomUser.objects.filter().update(grade="inactive")` → `is_active` 동기화 안 됨 (반드시 인스턴스 `save()`)
- 로그인 URL name: `"login"` (NOT `"accounts:login"`)
- Admin은 `custom_admin_site.register()` 사용 (NOT `admin.site.register()`)

---

### 9-2. board

**상세**: `docs/apps/guide_board.md`, `docs/apps/board_worktask_guide.md`

#### 핵심 책임

5개 도메인 관리: **Post(업무요청)**, **Task(직원업무)**, **WorkTask(개인업무관리)**, **Collateral(담보평가)**, **Industry(업계정보)**

#### 도메인별 접근 등급

| 도메인 | 허용 등급 |
|---|---|
| Post, Support/States 폼 | `superuser`, `head`, `leader` |
| Task | `superuser` 전용 |
| WorkTask | `superuser` 전용 + **owner 격리** |
| Collateral 조회/계산 | 로그인 사용자 전체 |
| Industry | 로그인 사용자 전체 |

#### 주요 SSOT

| 파일 | 역할 |
|---|---|
| `board/policies.py` | Post 조회/수정/다운로드 권한 판단 SSOT |
| `board/services/attachments.py` | 첨부 검증·저장·다운로드 SSOT |
| `board/services/worktasks.py` | WorkTask 소유자 격리 SSOT (`get_user_queryset`, `get_user_task`) |
| `board/services/comments.py` | Post/Task 댓글 공용 처리 |
| `board/services/listing.py` | 목록 필터·검색·페이지네이션 공용 처리 |

#### 주요 함정

- **`BOARD_ALLOWED_GRADES`로 게시판 접근 ≠ 개별 Post 조회 가능**: leader는 게시판에 접근하지만 본인 글만 볼 수 있다 (`policies.py:can_view_post` 경유).
- **WorkTask URL은 중첩 네임스페이스**: `{% url 'board:worktasks:worktask_list' %}` (NOT `{% url 'board:worktask_list' %}`)
- **`Post.user_id`는 CharField 스냅샷**: `CustomUser` FK 아님. 비교는 `policies.py:is_post_author()` 경유.
- **board 템플릿은 반드시 `board/base_board.html`을 extends**: `.board-scope` 래퍼와 `board.css`가 자동 적용됨.
- **`[data-status]` 값 체계 혼재**: Post/Task는 한글값(`"확인중"`, `"진행중"`), WorkTask는 영문값(`"pending"`, `"done"`).
- **Celery 태스크 파일 위치**: WorkTask 태스크 2개는 `board/task.py`(복수형 없음), 업계정보 태스크는 `board/tasks/`(패키지).

---

### 9-3. commission

**상세**: `docs/apps/guide_commission.md`

#### 핵심 책임

3개 도메인: **Deposit(채권현황)**, **Approval/Efficiency(수수료 결재)**, **Collect(환수관리)**  
엑셀 업로드로 원장 데이터 갱신, 권한별 조회·피드백 제공

#### 모델 설계 특이점

| 모델 | 특이점 |
|---|---|
| `CollectRecord` | `emp_id`는 `CharField` (CustomUser FK 없음) — 퇴직자 기록 보존 목적 |
| `CollectDropdownFeedback` | `UniqueConstraint` 없음 — 의도적 이력 누적 설계 |
| `DepositSurety` / `DepositOther` | 재업로드 시 사번 단위 DELETE → bulk_create (UPDATE 패턴 아님) |

#### 주요 SSOT

| 파일 | 역할 |
|---|---|
| `commission/services/collect.py` | Collect 도메인 전체 비즈니스 로직 |
| `commission/upload_handlers/registry.py` | 업로드 타입 등록 SSOT |
| `commission/upload_utils/_convert.py:_norm_emp_id` | "1234567.0" → "1234567" 사번 정규화 |

#### 주요 함정

- `deposit_home`, `approval_home`의 `grade_required("staff", "admin", "superuser")` — `"staff"`, `"admin"`은 실제 존재하지 않는 등급. 동작 방식 검증 필요.
- `collect_home.html`은 `{% block content_wrapper %}` 사용 (다른 commission 페이지와 다름 — 86vw 와이드 레이아웃)
- `views/__init__.py` lazy import 패턴을 일반 import로 변경 금지 (순환 import 방지 목적)

---

### 9-4. dash

**상세**: `docs/apps/guide_dash.md`

#### 핵심 책임

- **매출 대시보드**: SalesRecord 엑셀 업로드 → Celery 집계(SalesDailyAgg) → LightGBM 예측(SalesForecast) → Chart.js 렌더링
- **유지율 대시보드**: RetentionRecord 엑셀 업로드 → RetentionAgg 집계

#### 모델 설계 특이점

| 모델 | 특이점 |
|---|---|
| `SalesRecord` | `policy_no`가 PK. `user`는 null 허용 — snapshot 컬럼으로 집계 보완 |
| `SalesDailyAgg` | `unique_together = (ym, day, scope_type, scope_key, category)` — upsert 키 |
| `SalesForecast` | `model_ver` SSOT = `viewmods/constants.py:FORECAST_MODEL_VER = "lgbm_v1"` |

#### 주요 SSOT

| 파일 | 역할 |
|---|---|
| `dash/services/agg.py:build_daily_agg_for_month` | SalesDailyAgg 생성 SSOT |
| `dash/ml/forecast.py` | LightGBM 학습/저장/로드/예측 SSOT |
| `dash/task_runtime.py` | Celery 태스크 실구현 (tasks.py는 re-export만) |
| `dash/viewmods/constants.py:FORECAST_MODEL_VER` | 예측 모델 버전 SSOT |
| `dash/viewmods/utils/sales_filters.py:apply_head_scope_to_salesrecord_qs` | head 등급 강제 스코프 |

#### head 등급 강제 스코프

head 사용자가 `scope=all`을 요청해도 서버에서 `scope_type="branch"`, `scope_key=user.branch`로 덮어쓴다. 프론트에서 필터 UI를 숨기는 것만으로는 충분하지 않다.

#### 주요 함정

- `FORECAST_MODEL_VER` 변경 시 기존 DB의 모든 `SalesForecast` 레코드와 불일치 → 예측이 모두 빈 결과
- `tasks.py`는 re-export만. 실구현은 `task_runtime.py`에 있음.
- 모델 파일 경로: `var/dash_models/` (Docker 볼륨 마운트 경로) — 변경 시 컨테이너 재시작 후 모델 파일 유실
- `dash_sales.html` TOP10 테이블은 서버 사이드 렌더링 (JS API 호출 아님)
- `dash_retention.html`은 `{% block content_wrapper %}` 사용

---

### 9-5. manual

**상세**: `docs/apps/guide_manual.md`

#### 핵심 책임

Quill WYSIWYG 기반 업무 매뉴얼 지식 관리.  
`Manual → ManualSection → ManualBlock` 3단 계층 구조. 섹션·블록 SortableJS 드래그 정렬.

#### 권한 구조

- **편집** (생성/수정/삭제/정렬): `superuser` 전용
- **조회**: `admin_only=False`, `is_published=True` → inactive 외 전체 / `admin_only=True` → superuser/head 이상 / `is_published=False` → superuser 전용

#### 주요 SSOT

| 파일 | 역할 |
|---|---|
| `manual/utils/permissions.py:filter_manuals_for_user` | 목록 노출 정책 SSOT |
| `manual/utils/permissions.py:manual_accessible_or_denied` | 상세 접근 정책 SSOT |
| `manual/utils/sanitize.py:sanitize_quill_html` | Quill HTML bleach 살균 SSOT |
| `manual/utils/serializers.py:attachment_to_dict` | 첨부 JSON 직렬화 SSOT (quill.js 계약) |
| `static/js/manual/_shared.js:ManualShared` | 모든 manual JS의 AJAX·유틸 공용 객체 |

#### 주요 함정

- `ManualBlock.save()`에서 `sanitize_quill_html()` 자동 실행 → 뷰에서 별도 호출 불필요 (이중 호출 무해하나 불필요)
- `Manual.content`는 레거시 필드 — 실제 콘텐츠는 `ManualBlock.content` 체계
- `attachment_to_dict()` 반환 키(`id`, `name`, `url`, `download_url`, `size`) 변경 금지 — `quill.js`가 의존
- `ensure_superuser_or_403()` 반환값 무시 금지 — `if resp: return resp` 패턴 필수
- 섹션 삭제 후 `ensure_default_section(manual)` 호출 필수 (섹션 0개 방지)

---

### 9-6. partner

**상세**: `docs/apps/guide_partner.md`

#### 핵심 책임

5개 도메인: **편제변경(StructureChange)**, **요율변경(RateChange)**, **지점효율(EfficiencyChange)**, **권한관리(SubAdminTemp)**, **전자서명(EfficiencySignRequest)**

#### 모델 관계 핵심

```
CustomUser
  ├── SubAdminTemp (OneToOne) ← accounts.signals가 grade 변경 시 자동 동기화
  └── EfficiencySignRequest.created_by
        └── EfficiencyConfirmSign (서명 참여자, unique_together=(request, signer))

EfficiencyConfirmGroup (1)
  ├── EfficiencyConfirmAttachment (N) [PROTECT — 그룹 삭제 전 첨부 먼저 삭제]
  ├── EfficiencyChange (N) [PROTECT]
  └── EfficiencySignRequest (1)
        └── EfficiencyConfirmSign (N)
```

#### 주요 SSOT

| 파일 | 역할 |
|---|---|
| `partner/views/utils.py:resolve_branch_for_query` | GET 요청 branch 스코프 결정 SSOT |
| `partner/views/utils.py:resolve_branch_for_write` | POST 쓰기 branch 스코프 결정 SSOT |
| `partner/services/esign_service.py:create_sign_request` | 전자서명 요청 생성 SSOT (참여자 자동 생성) |
| `partner/services/esign_service.py:mark_sign_completed` | 전자서명 완료 처리 SSOT (PDF 생성 trigger) |
| `partner/views/responses.py:json_ok/json_err` | partner 앱 응답 형식 SSOT (`{"status":"success"/"error"}`) |

#### 주요 함정

- **응답 형식**: `{"status": "success"/"error"}` (board/manual의 `{"ok":true}` 아님)
- **`resolve_branch_for_query()` 없이 쿼리 작성 금지**: head 사용자가 타 지점 데이터를 조회하게 됨
- **`SubAdminTemp` 직접 생성 금지**: `accounts.signals`가 grade 변경 시 자동 실행되므로 충돌 위험
- **`EfficiencySignRequest` 직접 생성 금지**: `create_sign_request()`를 통해야 `EfficiencyConfirmSign` 참여자가 자동 생성됨
- **`EfficiencyConfirmGroup` 직접 삭제 금지**: PROTECT 제약으로 IntegrityError 발생. `efficiency_delete_group()` 경유 필요
- **`SubAdminTemp.db_table="partner_subadmin_temp"`**: `accounts/search_api.py`가 직접 의존 — 테이블명 변경 시 사용자 검색 파손

---

## 10. 신규 기능 추가 시 공통 체크리스트

### 새 뷰/API 추가

- [ ] `@login_required` 또는 `@grade_required` 적용
- [ ] `inactive` grade 사용자 차단 여부 검토 (`@not_inactive_required` 또는 grade 목록에서 제외)
- [ ] JSON API 뷰라면 `forbidden_template=None` 명시
- [ ] 파일 다운로드 뷰라면 `open_fileresponse_from_fieldfile()` 경유
- [ ] 사용자 검색이 필요하면 `search_users_for_api(request)` 또는 `{% url 'accounts:api_search_user' %}` 경유
- [ ] 민감 행위에 `log_action()` 호출 (+ `try/except` 래핑)
- [ ] `grade="inactive"` 저장 시 인스턴스 `user.save()` 경유 (bulk update 금지)

### 새 board 도메인 페이지 추가

- [ ] 템플릿: `{% extends 'board/base_board.html' %}` 필수 (`.board-scope` + `board.css` 자동 적용)
- [ ] CSS: `.board-scope` 하위로 스코핑
- [ ] JS boot div: `data-*-url`로 URL 주입 (하드코딩 금지)
- [ ] 첨부 다운로드: `board:post_attachment_download` / `board:task_attachment_download` / `board:worktasks:worktask_att_download` 경유

### 새 Celery 태스크 추가

- [ ] `@shared_task(name="앱명.tasks.태스크명")` 등록
- [ ] `web_ma/celery.py`의 `beat_schedule`에 동일 name으로 등록
- [ ] `board/tasks/`에 추가할 경우 `__init__.py` re-export 추가
- [ ] 태스크는 멱등성 보장 (`CELERY_TASK_ACKS_LATE=True`)

### 새 앱 CSS 추가

- [ ] `static/css/apps/<앱명>.css` 신규 생성
- [ ] 앱 전용 루트 id/class 하위로만 스코핑
- [ ] 해당 템플릿의 `{% block app_css %}` 블록에서 로드 (`?v={% now 'U' %}`)
- [ ] `base.css` 수정 금지

---

## 11. LLM 공통 함정 포인트

### 전체 앱 공통

1. **`request.user.username` 없음** — `request.user.id`(사원번호) 사용
2. **`bulk update`로 grade 변경 금지** — `is_active` 동기화 안 됨
3. **파일 URL 직접 노출 금지** — 반드시 다운로드 뷰 경유
4. **사용자 검색 직접 ORM 금지** — `search_users_for_api(request)` 경유
5. **log_action 실패가 사용자 동작을 막으면 안 됨** — `try/except` 필수
6. **개발환경 진행률 폴링 미동작** — `LocMemCache`는 Celery worker와 프로세스 공유 안 됨

### board 앱

7. **BOARD_ALLOWED_GRADES ≠ 모든 Post 조회 가능** — 개별 Post는 `policies.can_view_post()` 추가 검사
8. **WorkTask URL**: `board:worktasks:worktask_list` (중첩 네임스페이스)
9. **`Post.user_id`는 CharField** — `CustomUser.objects.get(id=post.user_id)` 금지
10. **board/base_board.html의 블록**: `{% block content_wrapper %}`가 `.board-scope` 주입. 하위 페이지는 `{% block content %}`로 내용 작성.

### partner 앱

11. **partner 응답 형식**: `{"status": "success"/"error"}` — `{"ok":true/false}` 아님
12. **`resolve_branch_for_query()` 없이 쿼리 금지** — 타 지점 데이터 유출
13. **`EfficiencySignRequest` 직접 생성 금지** — 참여자 자동 생성 누락

### dash 앱

14. **`FORECAST_MODEL_VER` 변경 시 기존 SalesForecast 전체 무효화**
15. **`tasks.py`는 re-export만** — 실구현은 `task_runtime.py`
16. **`SalesRecord.user=NULL`이어도 집계에서 누락 안 됨** — snapshot fallback 로직

### commission 앱

17. **`CollectRecord.emp_id`는 CharField** — CustomUser FK 아님, 퇴직자 사번 저장 목적
18. **`CollectDropdownFeedback` UniqueConstraint 추가 금지** — 이력 누적 설계
19. **Deposit 페이지 `grade="staff","admin"`** — 공식 등급이 아님, 동작 검증 필요

### manual 앱

20. **`Manual.content`는 레거시** — 실제 내용은 `ManualBlock.content` 체계
21. **`ensure_superuser_or_403()` 반환값 무시 금지** — `if resp: return resp` 패턴
22. **섹션 삭제 후 `ensure_default_section()` 호출** — 빈 매뉴얼 상태 방지

---

*이 문서는 각 앱 개발 가이드의 요약이다. 구현 세부 사항, 모델 전체 필드, 회귀 체크리스트는 각 앱별 상세 가이드를 참조한다.*
