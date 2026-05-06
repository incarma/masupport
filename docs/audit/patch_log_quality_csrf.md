# 품질 패치 로그 — STEP 2 (CSRF SSOT 리팩토링)
> 날짜: 2026-05-06
> 커밋 기준: be12619
> 기준 문서: docs/harness/QUALITY_RULES.md (RULE-Q-01)
> 방침: 기능 변화 0 리팩토링 — CSRF 토큰 취득 경로만 SSOT로 교체

## 수정 파일 목록

### 유형 A — ESM import 추가

| JS 파일 | 조치 |
|---------|------|
| `static/js/commission/collect_home.js` | 파일 상단에 `import { getCSRFToken } from "../../common/manage/csrf.js"` 추가; `getCSRF()` 함수 삭제; 호출부 `getCSRF()` → `getCSRFToken()` |

> `states_form.js`, `support_form.js`: 이미 SSOT import 완료 — 수정 불필요

### 유형 B — csrf_window.js 템플릿 주입 + window.csrfToken 사용

| JS 파일 | 변경 내용 |
|---------|----------|
| `static/js/board/collateral.js` | `getCSRF()` 함수 삭제; 호출부 2곳 → `window.csrfToken`; 헤더 주석의 `csrfmiddlewaretoken` 언급 제거 |
| `static/js/dash/dash_retention_page.js` | `getCSRF()` 함수 삭제; 호출부 1곳 → `window.csrfToken` |
| `static/js/partner/esign_confirm/fetch.js` | `getCsrf()` 함수 삭제; 호출부 1곳 → `window.csrfToken` |
| `static/js/partner/esign_confirm/save.js` | `getCsrf()` 함수 삭제; 호출부 1곳 → `window.csrfToken` |
| `static/js/partner/esign_confirm/sign.js` | `getCsrf()` 함수 삭제; 호출부 2곳 → `window.csrfToken` |
| `static/js/partner/manage_grades/index.js` | `U.getCookie()` 삭제; `getCSRFToken()` 함수 삭제; `buildPostHeaders()` → `window.csrfToken` |
| `static/js/utils/file_upload_utils.js` | `getCookie()` + `getCSRFToken(form)` 삭제; 호출부 → `window.csrfToken` (직접 `buildHeaders()` 전달) |
| `static/js/excel_upload.js` | `getCSRF` arrow 함수 삭제; 호출부 1곳 → `window.csrfToken` |

### 유형 B 템플릿 수정 (csrf_window.js 추가)

| 템플릿 | 추가 위치 |
|--------|----------|
| `board/templates/board/collateral.html` | `search_user_modal.js` 앞 |
| `dash/templates/dash/dash_retention.html` | `dash_retention_page.js` 앞 |
| `partner/templates/partner/esign_confirm.html` | 공통 유틸 블록 첫 줄 (3개 esign JS 공유) |
| `partner/templates/partner/manage_grades.html` | `manage_grades/index.js` 앞 |
| `board/templates/board/post_create.html` | `file_upload_utils.js` 앞 |
| `board/templates/board/post_edit.html` | `file_upload_utils.js` 앞 |
| `board/templates/board/task_create.html` | `file_upload_utils.js` 앞 |
| `board/templates/board/task_edit.html` | `file_upload_utils.js` 앞 |
| `commission/templates/commission/collect_home.html` | `excel_upload.js` 앞 |
| `commission/templates/commission/deposit_home.html` | `excel_upload.js` 앞 |

## python manage.py check 결과
```
System check identified no issues (0 silenced).
```

## quality_lint.sh Q-01 결과 (패치 대상 파일)

패치 대상 11개 파일 전체 위반 해소 ✅

잔존 위반 10건 — 이번 패치 범위 외 (사전 존재, STEP 2 미포함):

| 파일 | 위반 패턴 |
|------|----------|
| `board/common/comment_edit.js` | `getCsrfToken()` 재구현 |
| `board/common/detail_inline_update.js` | `getCsrfFromForm()` 재구현 |
| `board/common/inline_update.js` | `getCsrfFromForm()` 재구현 |
| `commission/approval_excel_upload.js` | `csrfmiddlewaretoken` DOM 직접 읽기 |
| `commission/collect_notice.js` | `_getCSRFToken()` 재구현 |
| `dash/sales_upload.js` | `csrfmiddlewaretoken` DOM 직접 읽기 |
| `landing/index.js` | `getCsrfToken()` 재구현 |
| `manual/create_manual_modal.js` | `csrfmiddlewaretoken` DOM 직접 읽기 |
| `manual/_shared.js` | `csrfmiddlewaretoken` DOM 직접 읽기 |
| `partner/manage_table.js` | `getCSRFToken()` 재구현 |

## 회귀 점검 결과

| 항목 | 결과 |
|------|------|
| CSRF 기능 동작 | 이상 없음 — csrf_window.js가 `window.csrfToken`을 설정하며 동일한 값을 제공; 유형 A는 SSOT import로 동일 체인 사용 |
| URL / 네임스페이스 | 이상 없음 — URL 변경 없음 |
| 권한 스코프 | 이상 없음 — CSRF 취득 경로만 변경, 권한 로직 변경 없음 |
| 템플릿 DOM / dataset | 이상 없음 — JS 내 DOM 선택자 변경 없음; csrf_window.js 추가만 |

## 미완료 항목

| 항목 | 우선순위 | 설명 |
|------|---------|------|
| 잔존 10개 파일 Q-01 위반 | 중간 | STEP 3 별도 배치로 처리 예정 |
| Q-02a: CSS `:root` 전역 변수 | 낮음 | `index.css`, `manual.css` 별도 작업 필요 |
| Q-02b: commission.css 전역 클래스 | 낮음 | 대규모 CSS 스코핑 작업 필요 |
| Q-03: commission JSON 헬퍼 중복 | 낮음 | `utils_json.py` SSOT 통합 필요 |
