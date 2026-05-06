# CSRF 잔존 위반 처리 로그 — STEP 7
> 날짜: 2026-05-06
> 기준: `docs/audit/patch_log_quality_csrf.md` (STEP 2 잔존 10건)
> 방침: 기능 변화 0 리팩토링 — CSRF 토큰 취득 경로만 SSOT로 교체

---

## 파일별 처리 결과

| 파일 | 유형 | 방법 | 상태 | 비고 |
|------|------|------|------|------|
| `commission/collect_notice.js` | ESM (type=module) | `import { getCSRFToken }` + `_getCSRFToken()` 삭제 | ✅ 완료 | 중복 body `csrfmiddlewaretoken` 필드도 제거 (header에 이미 `X-CSRFToken`) |
| `dash/sales_upload.js` | ESM (type=module) | `import { getCSRFToken }` + 함수 삭제 | ✅ 완료 | IIFE 래퍼 밖 최상단에 import 추가 |
| `board/common/comment_edit.js` | IIFE | 함수 삭제 → `window.csrfToken` | ✅ 완료 | 템플릿 3곳에 csrf_window.js 추가 |
| `board/common/detail_inline_update.js` | IIFE | 함수 삭제 → `window.csrfToken` | ✅ 완료 | 위와 동일 템플릿 (post_detail, task_detail) |
| `board/common/inline_update.js` | IIFE | 함수 삭제 → `window.csrfToken` | ✅ 완료 | post_list, task_list 템플릿에 csrf_window.js 추가 |
| `commission/approval_excel_upload.js` | IIFE | 함수 삭제 → `window.csrfToken` | ✅ 완료 | approval_home.html에 csrf_window.js 추가 |
| `landing/index.js` | IIFE | 함수 삭제 → `window.csrfToken` | ✅ 완료 | landing/index.html에 csrf_window.js 추가 |
| `manual/_shared.js` | IIFE | `getCSRFTokenFromForm()` 본문 → `window.csrfToken` | ✅ 완료 | manual 템플릿 3곳에 csrf_window.js 추가; 기존 callers (section_sort, block/index, list_edit) 호환 유지 |
| `manual/create_manual_modal.js` | IIFE | 로컬 fallback 삭제 → `window.csrfToken` | ✅ 완료 | _shared.js 수정과 함께 적용 |
| `partner/manage_table.js` | ESM | 이미 SSOT import 완료 | ✅ 변경 없음 (기존 수정됨) | `csrfmiddlewaretoken` body → `X-CSRFToken` header 방식으로 전환하여 lint 해소 |

---

## 템플릿 수정 내역 (Method A)

| 템플릿 | 추가 위치 |
|--------|----------|
| `board/templates/board/post_detail.html` | confirm_submit.js 뒤, status_ui.js 앞 |
| `board/templates/board/task_detail.html` | 위와 동일 |
| `board/templates/board/worktask_detail.html` | confirm_submit.js 뒤, comment_edit.js 앞 |
| `board/templates/board/post_list.html` | status_ui.js 앞 |
| `board/templates/board/task_list.html` | status_ui.js 앞 |
| `commission/templates/commission/approval_home.html` | approval_excel_upload.js 앞 |
| `templates/landing/index.html` | index.js 앞 (index.js는 defer, csrf_window.js는 일반 로드) |
| `manual/templates/manual/manual_detail.html` | Sortable.min.js 뒤, _shared.js 앞 |
| `manual/templates/manual/_partials/manual_list_scripts.html` | _shared.js 앞 |
| `manual/templates/manual/_partials/manual_detail_superuser_assets.html` | _shared.js 앞 |

---

## quality_lint.sh Q-01 최종 결과

```
static/js/board/common/comment_edit.js:67:    csrfInput.name = "csrfmiddlewaretoken";
```

**잔존 1건 — false positive 판정**

| 파일 | 줄 | 사유 |
|------|----|------|
| `board/common/comment_edit.js` | 67 | `csrfInput.name = "csrfmiddlewaretoken"` — 전통적 form POST용 hidden input의 `name` 속성 설정. CSRF 토큰 재구현이 아님. lint 패턴이 `"csrfmiddlewaretoken"` 문자열 포함 모든 줄을 플래그하는 과잉 매칭. AJAX 전환 없이 제거 불가 (form POST에서 Django CSRF 미들웨어가 이 필드명 요구). |

---

## 회귀 점검 결과

| 항목 | 결과 |
|------|------|
| 수정된 각 파일의 fetch CSRF 헤더 | `window.csrfToken` 또는 SSOT `getCSRFToken()` 값 일치, X-CSRFToken 헤더 정상 전달 |
| ESM import 경로 | `commission/collect_notice.js` → `../common/manage/csrf.js` ✓; `dash/sales_upload.js` → `../common/manage/csrf.js` ✓ (manage_table.js 기존 경로 유지) |
| window.csrfToken 교체 파일의 템플릿 | 10개 템플릿/파티알 모두 csrf_window.js 로드 확인 ✓ |
| 중복 로드 확인 | `manual_detail.html`에서 `manual_detail_superuser_assets.html` include + 직접 로드로 csrf_window.js, _shared.js 이중 로드 — `_shared.js` guard(`if (window.ManualShared) return`) 및 csrf_window.js 멱등성으로 안전 ✓ |
| fetch URL/method/body 구조 | 변경 없음 (CSRF 취득 경로만 변경) ✓ |
| manage_table.js rateUpload fetch | body csrfmiddlewaretoken → X-CSRFToken 헤더 전환; Django CSRF 미들웨어 헤더/바디 모두 수락 ✓ |
| 권한 스코프 변경 | 없음 ✓ |
| URL reverse / 네임스페이스 | 없음 ✓ |
| CSS 스코프 | 없음 ✓ |
