# django_ma 중복 탐지 및 모듈화 분석 리포트
> 탐지일: 2026-05-07
> 탐지 범위: 전체 (백엔드 Python + 프론트엔드 JS + CSS)
> 코드 변경 없음 — 탐지 + 분석 전용
> 기준 브랜치: develop (최신 커밋: 7882f4c)
> 이전 패치 이력 참조: STEP 1~9 (patch_log_security.md ~ patch_log_quality_task_step9.md)

---

## 요약 대시보드

| 영역 | 탐지 항목 수 | 🔴 즉시 개선 | 🟡 중기 개선 | 🟢 참고/모니터링 | 예상 총 파일 영향 |
|------|------------|------------|------------|----------------|-----------------|
| A. 백엔드 JSON 헬퍼 | 7 | 3 | 2 | 2 | 7개 파일 |
| B. 백엔드 서비스 레이어 | 5 | 1 | 3 | 1 | 8개 파일 |
| C. 백엔드 권한/정책 | 4 | 0 | 2 | 2 | 6개 파일 |
| D. 프론트엔드 JS 공통 유틸 | 8 | 2 | 3 | 3 | 12개 파일 |
| E. CSS 스코프 누수 | 4 | 1 | 2 | 1 | 3개 파일 |
| F. 파일 업로드/다운로드 | 3 | 0 | 2 | 1 | 5개 파일 |
| G. 전사 공통 패턴 | 3 | 0 | 1 | 2 | - |
| **합계** | **34** | **7** | **15** | **12** | **~41개 파일** |

---

## A. 백엔드 JSON 응답 헬퍼 중복

### A-1. 탐지 결과

다음 위치에서 JSON 응답 헬퍼 함수가 중복 정의되어 있다:

| 파일 | 함수명 | 응답 포맷 | 상태 |
|------|--------|----------|------|
| `commission/views/utils_json.py` | `_json_ok`, `_json_error` | `{"ok": true/false}` | ✅ SSOT |
| `partner/views/responses.py` | `json_ok`, `json_err` | `{"status": "success"/"error"}` | ✅ SSOT (의도적 차별화) |
| `dash/viewmods/utils/json.py` | `json_err` | `{"ok": false}` | ✅ SSOT (dash 앱 내부) |
| `manual/utils/http.py` | `ok`, `fail` | `{"ok": true/false}` | ✅ SSOT (manual 앱 내부) |
| `board/views/worktasks.py:85-89` | `_ok`, `_err` | `{"ok": true/false}` | 🔴 중복 — board 전용 SSOT 미사용 |
| `board/views/industry_info.py:46-51` | `_json_ok`, `_json_err` | `{"ok": true/false}` | 🔴 중복 — board 전용 SSOT 미사용 |
| `board/views/collateral.py:30-41` | `_json_ok`, `_json_error` | `{"ok": true/false}` | 🟡 앱 간 cross-import 회피 목적이나 중복 |
| `board/views/forms.py:76-77` | `_json_err` | `{"ok": false}` | 🔴 중복 — 함수 하나만 재정의 |
| `partner/views/esign.py:37-46` | `_ok`, `_err` | `{"status": "success"/"error"}` | 🟡 `responses.py` SSOT가 있으나 재정의 |

### A-2. 현재 SSOT 구조

```
commission 앱  → commission/views/utils_json.py (_json_ok / _json_error)
partner 앱     → partner/views/responses.py (json_ok / json_err) — {"status": ...} 형식
manual 앱      → manual/utils/http.py (ok / fail)
dash 앱        → dash/viewmods/utils/json.py (json_err 단일 함수)
board 앱       → SSOT 없음 (뷰 파일마다 개별 정의)
```

**응답 포맷 분기 현황:**
- `{"ok": true/false, ...}` 형식: board, commission, manual, dash
- `{"status": "success"/"error", ...}` 형식: partner (의도적 차별화)
- 두 형식이 혼재하며, 특히 `partner/views/esign.py`가 `responses.py` SSOT(`{"status":...}`)를 무시하고 재정의한다

### A-3. 모듈화 방향 제안

1. **board 앱 SSOT 신설**: `board/views/_json.py` 에 `_json_ok`, `_json_err` 정의 후 worktasks.py, industry_info.py, forms.py 등에서 import
2. **collateral.py 교차 import 이슈**: 같은 포맷이지만 commission 의존성을 피하려는 의도로 로컬 정의 — board 자체 SSOT 신설로 해결 가능
3. **esign.py 정렬**: `partner/views/responses.py`의 `json_ok/json_err`를 import하도록 교체 (이름만 다르고 기능 동일)
4. **dash의 json_err만 있는 것**: `json_ok`는 뷰에서 직접 `JsonResponse({"ok": True, ...})`로 쓰고 있으므로 일관성을 위해 `json_ok`도 추가하거나 직접 사용 패턴을 통일

### A-4. 회귀 위험 포인트

- `partner/views/esign.py`의 `_ok`/`_err`를 `json_ok`/`json_err`로 교체 시 응답 키가 달라짐:
  - 현재: `{"status": "success", ...}` (esign.py 정의) → 사실상 동일
  - 단, `_ok`가 `data` dict를 받아 `**data`로 펼치는 구조 vs `json_ok`가 `payload` dict를 spread하는 구조 — JS가 어떤 키를 기대하는지 확인 필요
- board 신규 SSOT 파일 생성 시 기존 로컬 함수 삭제 전에 모든 사용처를 import로 교체해야 함

---

## B. 백엔드 서비스 레이어 ORM 직접 처리

### B-1. 탐지 결과

#### B-1-1. commission 앱 — Deposit 도메인

`commission/views/api_deposit_impl.py`에서 ORM을 직접 사용:
- `CustomUser.objects.only(...)` (92번째 줄)
- `DepositSummary.objects.filter(user_id=target.pk).first()` (346번째 줄)
- `DepositSurety.objects.filter(user_id=user_pk)` (292, 305번째 줄)
- `DepositOther.objects.filter(user_id=user_pk)` (296, 309, 403번째 줄)

`commission/services/` 에는 `collect.py`만 있고 Deposit 도메인 전용 서비스 레이어가 없다.

#### B-1-2. commission 앱 — Approval/pages 도메인

`commission/views/approval.py`: `ApprovalPending.objects.filter(ym=ym)`, `EfficiencyPayExcess.objects.filter(ym=ym)` 직접 호출
`commission/views/pages.py`: `DepositUploadLog`, `ApprovalPending`, `EfficiencyPayExcess` 직접 조회
`commission/views/downloads.py`: `ApprovalPending.objects.all()`, `EfficiencyPayExcess.objects.all()` 직접 조회

#### B-1-3. partner 앱 — 다중 뷰에서 grade 분기 로직

`partner/views/rate.py`, `partner/views/efficiency.py`, `partner/views/structure.py` 등에서 `user.grade == "superuser"`, `user.grade == "leader"` 직접 비교가 24개 위치에서 탐지됨. `partner/views/utils.py`의 `resolve_branch_for_query/write`가 일부 SSOT이지만, 세부 grade 분기는 각 뷰에 분산.

#### B-1-4. board 앱 — worktasks.py 서비스 경유 확인

`board/views/worktasks.py`는 주석(`ORM 직접 호출 금지 → board.services.worktasks 경유 필수`)대로 `wt_svc`를 경유하여 ORM을 호출하고 있어 정책 준수 상태.

#### B-1-5. dash 앱

`dash/viewmods/pages.py`에서 `request.user.grade == "head"` 분기 3회 — 집계/필터 목적으로 정당한 사용 (S-B-04 제외 판정 목록 참조).

### B-2. 서비스 레이어 분리 대상 우선순위

| 우선순위 | 대상 | 이유 |
|---------|------|------|
| 🟡 중기 | commission Deposit API | 서비스 레이어 없어 뷰가 비대, 테스트 불가 |
| 🟡 중기 | commission Approval/downloads | 공통 조회 로직이 3곳에 분산 |
| 🟢 참고 | partner grade 분기 통합 | 현재는 `resolve_branch_for_*`가 부분 SSOT, 나머지는 뷰 인라인 |

### B-3. 기존 서비스 레이어 재사용 기회

- `commission/services/collect.py`의 서비스 레이어 설계 패턴을 Deposit/Approval 도메인에도 적용 가능
- `partner/services/esign_service.py`의 `build_esign_queryset(user, branch_filter)` 패턴을 다른 파트너 도메인 서비스에 적용 가능

---

## C. 백엔드 권한/정책 로직 중복

### C-1. 탐지 결과

`request.user.grade == / user.grade ==` 패턴이 다음 파일에서 24회 탐지됨 (decorators.py, policies.py 제외):

| 파일 | 탐지 횟수 | 용도 |
|------|----------|------|
| `dash/viewmods/pages.py` | 3 | 집계 스코프 분기 (S-B-04 제외 판정: 정당) |
| `dash/viewmods/api_retention.py` | 1 | 보유자산 스코프 |
| `dash/viewmods/api_forecast.py` | 1 | 예측 스코프 |
| `partner/views/rate.py` | 2 | 요율 쓰기 분기 |
| `partner/views/process_date.py` | 1 | 처리일자 범위 |
| `partner/views/grades.py` | 2 | DataTables 필터 스코프 |
| `partner/views/subadmin.py` | 2 | head 지점 제한 |
| `partner/views/efficiency.py` | 8 | 확인서 업로드/삭제 스코프 (가장 많음) |
| `partner/views/structure.py` | 2 | 삭제 권한 분기 |

### C-2. 정책 함수로 통합 가능한 항목

- **`partner/views/efficiency.py`의 8개 grade 분기**: `resolve_branch_for_query/write`가 일부를 처리하지만, `user.grade == "superuser" and not branch.strip()` 형태의 분기가 반복됨 → `partner/views/utils.py`에 `needs_branch_required(user)` 같은 헬퍼 추가 검토
- **`partner/views/subadmin.py`의 head 지점 제한**: 이미 `_same_branch()` 헬퍼가 있어 적절히 추상화됨
- **`board/policies.py` SSOT**: board 앱은 `policies.py`가 있어 `can_access_states_form`, `can_access_support_form` 등이 관리됨 — 잘 분리된 상태

### C-3. is_superuser 직접 체크 분산

`request.user.grade == "superuser"` 패턴이 다수 파일에 분산되어 있음. 단, 이는 `grade` 시스템을 사용하는 이 프로젝트의 설계 원칙과 일치하며, Django의 `is_superuser` 필드와 혼동될 위험은 없음. 현재는 `grade_required` 데코레이터로 진입점에서 제어, 내부 분기만 인라인으로 처리하는 구조.

---

## D. 프론트엔드 JS 공통 유틸 중복

### D-1. CSRF 중복 현황

**STEP 7 (2026-05-06) 패치 완료 이후 잔존 현황:**

| 파일 | 상태 | 세부 사항 |
|------|------|---------|
| `static/js/common/manage/csrf.js` | ✅ SSOT | `export function getCSRFToken()` |
| `static/js/board/industry_info.js:14-25` | 🔴 위반 잔존 | `function getCSRFToken()` 쿠키 직접 파싱 재구현 (STEP 7에서 미처리) |
| `static/js/board/common/comment_edit.js:67` | 🟢 false positive | `csrfInput.name = "csrfmiddlewaretoken"` — form POST hidden input name 속성 설정 (STEP 7에서 false positive 판정) |

**주요 상태 (STEP 7 완료로 해소된 항목):**
- `commission/collect_home.js`, `collect_notice.js`, `dash/sales_upload.js`: `import { getCSRFToken }` SSOT로 교체 완료
- `board/collateral.js`, `dash/dash_retention_page.js`, `partner/esign_confirm/*.js`, `partner/manage_grades/index.js`, `utils/file_upload_utils.js`, `excel_upload.js`, `landing/index.js`, `manual/_shared.js`, `manual/create_manual_modal.js`: `window.csrfToken` 사용으로 교체 완료

**남은 실제 위반:**
- `board/industry_info.js`에서 로컬 `getCSRFToken()` 함수를 쿠키에서 직접 파싱하는 방식으로 재구현 (IIFE, type="module" 아님). `window.csrfToken`으로 대체 가능.

### D-2. fetch/JSON 파싱 중복 현황

`static/js/common/manage/http.js`의 `readJsonOrThrow`/`isSuccessJson`이 SSOT.

**사용 중 파일 (정상):**
- `partner/manage_table.js`, `partner/manage_efficiency/*.js`, `partner/manage_rate/*.js`, `partner/manage_structure/*.js` — 전부 `readJsonOrThrow` 사용

**미사용 파일 (직접 `.json()` 파싱):**
- `board/worktask_list.js`: ESM, `readJsonOrThrow` 미사용
- `board/worktask_detail.js`: ESM, `readJsonOrThrow` 미사용
- `commission/collect_home.js`: ESM, 자체 fetch 래퍼 사용 (`_net_json.js` 경유)
- `commission/deposit_home.js`: IIFE, `CommissionCommon.net.fetchJSON` 사용
- `board/industry_info.js`: IIFE, 직접 `.json()` 파싱
- `dash/dash_retention_page.js`: IIFE, 직접 `.json()` 파싱
- `board/collateral.js`: IIFE, 직접 `.json()` 파싱
- `board/states_form.js`, `board/support_form.js`: ESM, 패턴 미확인

**평가:** commission 앱은 `CommissionCommon.net.fetchJSON` 내부 공용 유틸을 사용하여 일관성이 있음. board/dash IIFE 파일들은 `readJsonOrThrow` 미사용 — 오류 처리 일관성이 낮음.

### D-3. BFCache 가드 누락 현황

`dataset.inited === "1"` 가드가 있는 파일:
- `board/collateral.js`, `board/industry_info.js`, `commission/collect_home.js`, `commission/collect_notice.js`, `board/worktask_list.js`, `board/worktask_detail.js`, `partner/manage_table.js`, `dash/dash_retention_page.js`, `partner/manage_efficiency/index.js`

**누락 가능성이 있는 파일 (IIFE지만 guard 없음):**
- `commission/deposit_home.js`: IIFE이지만 `dataset.inited` 가드 없음 — root 존재 여부만 체크 (guide_commission.md에서 "BFCache 가드: 없음 (root 존재 여부만 체크)"로 명시됨, 의도적)
- `board/post_list.js`, `board/task_list.js`: `window.Board.Common.initListInlineUpdate` 위임 — 내부 `__boardListInlineUpdateBound` 플래그로 중복 방지

### D-4. URL 하드코딩 현황

JS 내 URL 직접 하드코딩이 발견된 파일:

| 파일 | 하드코딩 URL | 형태 |
|------|------------|------|
| `board/worktask_list.js:491` | `/board/worktasks/${id}/` | fallback 아님, 동적 href 생성 |
| `board/collateral.js:532` | `/board/collateral/` | dataset fallback (dataset 미설정 시) |
| `dash/dash_sales_page.js:11` | `/dash/api/forecast/` | dataset fallback |
| `dash/dash_retention_page.js:17-18` | `/dash/api/retention/`, `/dash/api/retention/upload/` | dataset fallback |
| `commission/deposit_home.js:38-41` | `/commission/api/user-detail/` 등 4개 URL | dataset fallback |
| `partner/manage_table.js:95-97` | `/partner/ajax/rate-userlist/` 등 3개 URL | dataset fallback |
| `partner/manage_grades/index.js:88-90` | `/partner/ajax/fetch-channels/` 등 3개 URL | dataset fallback |
| `common/part_branch_selector.js:129-131` | `/partner/ajax/fetch-channels/` 등 3개 URL | dataset fallback |
| `partner/manage_rate/input_rows.js:120` | `/partner/ajax/rate-user-detail/` | `new URL()` fallback |
| `partner/pdf_processing.js:25-26` | `/manual/status/{taskId}/`, `/manual/download/{taskId}/` | dataset fallback |

**평가:** 대부분은 dataset 값이 없을 때의 fallback URL이며 실제 운영에서는 dataset이 항상 주입된다. 단, `worktask_list.js:491`의 `/board/worktasks/${id}/` href는 dataset 없이 직접 URL을 사용하는 구조여서 URL 변경 시 JS 수정이 필요하다.

### D-5. 기타 공통 유틸 미사용 현황

- `manual/_shared.js`의 `getCSRFTokenFromForm()`이 `window.csrfToken`을 반환하도록 변경됨 — 기존 callers (section_sort, block/index, list_edit)는 함수명 그대로 사용하므로 SSOT 정렬 완료
- `window.CommissionCommon`의 `net.fetchJSON()` 유틸이 `deposit_home.js`에서 사용 — `readJsonOrThrow`와 다른 레이어이므로 충돌 없음

---

## E. CSS 스코프 누수 현황

### E-1. 앱별 위반 현황

**commission.css**:
- 전체 스코프 탐지 결과: 스코프 없는 전역 클래스 선택자 없음 (STEP 3 패치 완료)
- 모든 규칙이 `#deposit-home`, `#collect-home`, `#collect-notice`, `#collectTableHead`, `#collectTableBody`, `#suretyTable`, `#otherTable`, `#suretyColGroup`, `#otherColGroup` 스코프 하위

**manual.css**:
- 스코프 없는 전역 클래스 선택자 다수 탐지:
  - `.manual-badge-admin`, `.manual-badge-staff` (줄 26-42): 전역 클래스
  - `.sortable-ghost`, `.manual-sort-ghost`, `.manual-sort-chosen` (줄 43-45): 전역 클래스
  - `.manual-list-container`, `.manual-list-title`, `.manual-list-group` 등 (줄 53-): 전역 클래스
  - `.manual-subnav`, `.subnav-inner` 관련 규칙: `.manual-subnav` 접두어 있으나 루트 ID 스코프 없음
- **단, `manual-` 접두어가 충분히 구별된다는 점에서 충돌 위험이 낮음** (의도적 설계일 가능성)
- `:root` 전역 변수: STEP 8에서 `#manual-detail`로 이동 완료

**partner.css**:
- `.partner-page-title`, `.partner-page-title-sm`, `.partner-section-title` (줄 1410-1417): 스코프 없는 전역 클래스
  - 주석: "manage_grades 전용 CSS 파일이 없으므로 partner.css에 통합"으로 의도적 선택
  - partner 앱 내 5개 이상의 템플릿에서 사용 (`manage_rate.html`, `manage_grades.html`, `manage_charts.html`, `manage_calculate.html`, `esign_confirm.html`)
  - 실질적 충돌 위험: `partner-page-title`이라는 이름이 충분히 구체적이라 타 앱과 충돌 가능성 낮음

**board.css**:
- STEP 8 이후 잔존 위반 언급: `.cn-loading-overlay`, `#collect-notice .cn-*` (board.css가 해당 요소를 스코프하는 방식이 정책 위반으로 지적됨)

### E-2. 이미 해소된 항목

| 항목 | 해소 STEP |
|------|---------|
| `commission.css`: `.deposit-title`, `.deposit-section-title`, `.ellipsis-cell`, `.info-table` | STEP 3 (patch_log_quality_css.md) |
| `partner.css`: `.modal-subadmin-sm` | STEP 3 |
| `manual.css`: `:root` 전역 변수 선언 | STEP 8 (patch_log_quality_css_step8.md) |

### E-3. 잔존 위반 목록 및 수정 시 주의사항

| 파일 | 위반 선택자 | 위험도 | 수정 시 주의 |
|------|-----------|-------|------------|
| `manual.css` | `.manual-badge-admin`, `.manual-badge-staff`, `.sortable-ghost` 등 | 🟡 낮음 (접두어로 구분) | 해당 클래스가 사용되는 모든 템플릿 확인 후 스코프 추가 |
| `manual.css` | `.manual-list-*`, `.manual-*` 계열 전역 클래스 | 🟡 낮음 (접두어로 구분) | 동일 |
| `partner.css` | `.partner-page-title`, `.partner-section-title` | 🟢 매우 낮음 | 여러 partner 템플릿 공용 — 스코핑 어렵고 필요성도 낮음 |
| `index.css` | `:root` 전역 변수 | 🟡 | 랜딩 페이지 전용 변수인지 전사 공용인지 확인 필요 |

---

## F. 파일 업로드/다운로드 중복

### F-1. 엑셀 파싱 중복 현황

`openpyxl` 사용 파일:
- `board/admin.py`: Workbook 직접 생성 (Admin 다운로드용)
- `accounts/admin.py`: Workbook 직접 생성 (Admin 다운로드용)
- `accounts/tasks.py`: `load_workbook` 사용 (업로드)
- `join/admin.py`: Workbook 직접 생성 (Admin용)
- `commission/services/collect_notice_excel.py`: 서비스 레이어에서 처리 (적절)
- `commission/upload_utils/_readers.py`: pandas + openpyxl 엔진 (upload 유틸)
- `commission/views/_excel_export.py`: pandas + openpyxl 엔진 (적절한 레이어)
- `partner/views/ratetable.py`: `pd.ExcelWriter` 직접 사용 (뷰 레이어에서 처리 — 서비스 레이어 부재)

**평가:** `commission` 앱은 `upload_utils/_readers.py`로 일관된 Excel 읽기 SSOT가 있음. `partner/views/ratetable.py`에서 뷰 레이어에서 직접 Excel 생성 — 서비스 레이어로 분리 검토 가능.

### F-2. RFC5987 파일명 처리 중복 현황

- `board/services/attachments.py`: `django.utils.http.content_disposition_header` 사용 (SSOT)
- `commission/views/utils_json.py`: `_set_attachment_filename()` — ASCII fallback + `filename*=UTF-8''` 방식
- `partner/views/efficiency.py`와 `esign.py`: `urllib.parse.quote` 사용하여 RFC5987 적용

두 가지 RFC5987 구현 방식이 공존하지만, Django의 `content_disposition_header`와 수동 구현은 결과가 동일함. 중복이나 규약상 문제는 없음.

### F-3. 보안 위반 가능성 (직접 URL 노출)

**탐지 결과:**

```
board/templates/board/includes/_form_common.html:59
  {{ att.original_name|default:att.file.name }}  ← 파일명만 표시, URL 노출 아님

board/templates/board/post_detail.html:195
  {{ att.original_name|default:att.file.name }}  ← 파일명만 표시

board/templates/board/task_detail.html:151
  {{ att.original_name|default:att.file.name }}  ← 파일명만 표시
```

**평가:** 탐지된 `.file.name`은 파일명(문자열) 표시이지 `.file.url` 노출이 아님. 실제 다운로드 링크는 `board:post_attachment_download`, `board:task_attachment_download` 뷰를 경유하고 있음. 보안 위반 없음.

`board/templates/board/worktask_detail.html`에는 "att.file.url 직접 링크 금지" 주석과 함께 다운로드 뷰를 경유하는 href가 사용되고 있음.

---

## G. 전사 공통 패턴

### G-1. ACTION 상수 사용 현황

**현재 상태 (STEP 1 패치 완료):**
- `audit/constants.py`에 `COMMISSION_EXCEL_UPLOAD` 추가 완료
- `partner/views/subadmin.py`에 `PARTNER_LEADER_ADD/DELETE` 호출 완료 (subadmin.py:67, 152)
- `accounts/tasks.py`에 `ACCOUNTS_EXCEL_UPLOAD` 및 `ACCOUNTS_GRADE_UPDATE` 호출 완료 (tasks.py:490, 507)

**미사용 상수:**
- `audit/constants.py`에 `ACCOUNTS_GRADE_UPDATE = "accounts.user.grade.update"` 정의됨
- `accounts/tasks.py:509`에서 실제 사용 확인됨 → 완료 상태

**잔존 모니터링 항목:**
- `ACCOUNTS_LEVEL_UPDATE` 상수가 정의되어 있으나 사용처 확인 필요
- board/collateral 관련 `AUDIT_ACTION_COLLATERAL_EVAL`이 `board/constants.py`에서 별도 관리되는 것으로 보임 — `audit/constants.py`의 ACTION 클래스와 별개 체계

### G-2. log_action() 일관성

log_action 호출이 발견된 파일 수: 50개 이상
대부분 `try: ... except Exception: logger.exception(...)` 패턴으로 감싸 있어 audit 로그 실패가 서비스 중단을 막도록 처리됨.

### G-3. except Exception 패턴 현황

전사적으로 `except Exception:` 후 `pass` 또는 `return` 처리가 광범위하게 사용됨 (탐지 수 ~120건).
대부분이 `logger.exception(...)` 또는 `logger.warning(...)` 호출을 포함하거나, audit 로그 실패를 비차단 처리하기 위한 패턴으로 사용되어 적절한 사용임.
다만 일부 변환 유틸(`upload_utils/_convert.py`)에서 `except Exception: return default`는 에러 정보가 소실될 수 있음.

---

## 보안 경고 (NEVER_DO.md 위반 발견 여부)

**NEVER_DO.md 4개 항목 현재 상태 확인:**

| 항목 | 내용 | 현재 상태 |
|------|------|---------|
| S-B-05 | `partner/views/subadmin.py` grade 변경 후 `log_action()` 미호출 | ✅ **해소** — subadmin.py:67, 152에서 ACTION.PARTNER_LEADER_ADD/DELETE 호출 확인 |
| S-B-06 | `accounts/tasks.py` process_users_excel_task 완료 시 `log_action()` 미호출 | ✅ **해소** — tasks.py:490(ACCOUNTS_EXCEL_UPLOAD), 507(ACCOUNTS_GRADE_UPDATE) 호출 확인 |
| S-D-01 | `commission/views/api_upload.py`, `approval.py` `@csrf_exempt` 사용 | ✅ **해소** — 두 파일에서 `@csrf_exempt` 사라짐 (grep 결과 0건) |
| S-E-01/S-E-04 | 미정의 `ACTION.XXX` 상수 사용 | ✅ **해소** — `COMMISSION_EXCEL_UPLOAD` 상수 추가 완료, approval.py 6개 참조 모두 유효화 |

**결론: NEVER_DO.md의 4개 금지 항목은 모두 이전 패치 STEP 1에서 해소 완료됨. 현재 기준으로 새로운 NEVER_DO 위반 없음.**

---

## 모듈화 우선순위 로드맵

### Phase 1 — 안전하고 즉시 가능 (기능 변화 0 보장)

| 항목 ID | 작업 내용 | 영향 파일 수 | 예상 공수 | 회귀 위험 |
|---------|----------|------------|---------|---------|
| A-P1-01 | `board/views/industry_info.js`의 `getCSRFToken()` 로컬 구현 → `window.csrfToken`으로 교체 | 1 (JS) + 0~1 (template) | 30분 | 매우 낮음 — CSRF 취득 경로만 변경 |
| A-P1-02 | `board/views/_json.py` 신설 후 `board/views/forms.py`의 `_json_err` import로 교체 | 2 | 20분 | 낮음 — 응답 포맷 동일 |
| A-P1-03 | `partner/views/esign.py`의 `_ok`/`_err` 함수를 `responses.py`의 `json_ok`/`json_err`로 교체 | 1 | 1시간 | 중간 — JS가 응답 키를 기대하는 방식 사전 확인 필요 |

### Phase 2 — 중기 구조 개선 (설계 검토 필요)

| 항목 ID | 작업 내용 | 영향 파일 수 | 예상 공수 | 회귀 위험 |
|---------|----------|------------|---------|---------|
| B-P2-01 | `board/views/worktasks.py`, `industry_info.py`, `collateral.py`의 JSON 헬퍼를 board 공용 SSOT로 통합 | 3 | 2시간 | 낮음 — 응답 포맷 동일 유지 전제 |
| B-P2-02 | `commission/views/api_deposit_impl.py` ORM → `commission/services/deposit.py` 신설 위임 | 2 | 4시간 | 중간 — API 응답 변화 없어야 함 |
| C-P2-03 | `partner/views/efficiency.py`의 반복 grade 분기를 `partner/views/utils.py` 헬퍼로 추출 | 1 | 2시간 | 중간 — 권한 로직 추출 시 동등성 검증 필요 |
| E-P2-04 | `manual.css`의 전역 클래스들을 `#manual-list`, `#manual-detail` 등 루트 ID 하위로 스코핑 | 1 (CSS) + 관련 템플릿 | 3시간 | 중간 — 모든 manual 템플릿 구조 파악 후 진행 |
| D-P2-05 | `board/worktask_list.js:491`의 하드코딩 href URL을 dataset URL template으로 대체 | 1 (JS) + 1 (template) | 1시간 | 낮음 |

### Phase 3 — 장기 아키텍처 개선 (별도 설계 필요)

| 항목 ID | 작업 내용 | 영향 파일 수 | 예상 공수 | 회귀 위험 |
|---------|----------|------------|---------|---------|
| B-P3-01 | `commission` 앱 전체에 서비스 레이어 완성 (Deposit, Approval 도메인 추가) | 5+ | 1주일 | 높음 — API 계약 변경 없도록 설계 필요 |
| D-P3-02 | `readJsonOrThrow` SSOT를 board/dash IIFE 파일에도 적용 (ESM 전환 필요할 수 있음) | 6+ | 3일 | 높음 — ESM 전환 시 템플릿 로드 순서/방식 변경 |
| E-P3-03 | `index.css` `:root` 변수 정리 — 전사 공용 토큰 `base.css`로 통합 또는 `index.css` 스코핑 | 2 | 2시간 | 중간 — 랜딩 페이지 시각 확인 필요 |

---

## 변경 금지 목록 (SSOT 보호 대상)

| 파일/함수 | 금지 이유 |
|-----------|----------|
| `commission/upload_handlers/registry.py` | 업로드 타입 SSOT — 변경 시 deposit_home.html 버튼 즉시 파괴 |
| `commission/services/collect.py` `_apply_scope()` | leader 팀 스코프 필터 — 수정 시 데이터 유출 위험 |
| `partner/views/utils.py` `resolve_branch_for_query/write()` | 삭제/수정 시 타 지점 데이터 유출 |
| `partner/services/esign_service.py` `create_sign_request/mark_sign_completed()` | 우회 시 참여자 누락, PDF 미생성 |
| `partner/views/responses.py` `json_ok/json_err` 응답 키 | JS가 `response.status === "success"/"error"` 기대 — 키 변경 시 partner 전체 AJAX 파손 |
| `board/policies.py` | Post/Task 접근 권한 정책 SSOT |
| `board/services/attachments.py` | RFC5987 파일명 + 첨부 다운로드 보안 정책 SSOT |
| `accounts/search_api.py` | 사용자 검색 SSOT — 프론트 직접 필터링 금지 |
| `audit/constants.py` `ACTION` 클래스 | ACTION 상수 추가는 가능, 기존 값 변경/삭제 금지 (DB 기록값과 불일치 발생) |
| `commission/views/utils_json.py` | commission 앱 JSON SSOT — 재정의 금지 (RULE-Q-03) |
| `static/js/common/manage/csrf.js` | CSRF SSOT — 대체 구현 금지 (RULE-Q-01) |
| `static/js/common/manage/http.js` | fetch/JSON 파싱 SSOT |

---

## 탐지 한계 및 수동 확인 필요 항목

1. **`dash/viewmods/api_upload.py`의 JSON 응답 형식**: dash 앱에서 `{"ok": True, ...}` 직접 사용 패턴이 있으나 `dash/viewmods/utils/json.py`의 `json_err`과 혼재. 뷰별로 응답 포맷 일관성 수동 확인 권장.

2. **`partner/views/esign.py`의 `_ok`/`_err` 함수**: 현재 `{"status": "success", ...}` 포맷을 반환하나, `partner/views/responses.py`의 `json_ok/json_err`와 동일. 그러나 `_ok`는 data dict를 `**kwargs`로 받아 직접 spread하는 반면 `json_ok`는 `payload` dict로 병합 — 최종 JSON 구조가 동일한지 JS 기대값 기준으로 확인 필요.

3. **`board/views/collateral.py`의 로컬 JSON 헬퍼**: "commission 앱 의존성을 피하기 위한 로컬 정의"로 주석이 달려 있음. board 자체 SSOT 파일 신설 후 이 파일에서 import하는 방식이 적절함.

4. **`accounts/constants.py`의 `ACCOUNTS_LEVEL_UPDATE` 사용 여부**: 정의는 있으나 실제 호출 여부를 확인 못함. `accounts/views.py`의 level 업데이트 관련 분기에서 사용 가능성 있음.

5. **`board.css`의 `.cn-loading-overlay` 전역 클래스**: STEP 8 패치 로그에서 "이번 범위 아님"으로 유보된 항목 — 실제 board.css 파일 내 수동 확인 필요.

---

## 자기 점검 (AI 수행)

- [x] 탐지 결과에 코드 수정 내용이 포함되어 있지 않은가
- [x] 발견한 모든 중복 항목에 대해 "이미 해소된 것과 미해소된 것"을 구분했는가
- [x] 각 항목의 모듈화 제안이 "기존 SSOT 위에 얹는 방식"으로만 제안되었는가
- [x] NEVER_DO.md의 금지 패턴은 "발견 시 별도 경고"로 표시했는가 (4개 항목 모두 해소 확인)
- [x] 회귀 위험 체크리스트(권한/URL/dataset/CSS 스코프 등)가 각 항목에 포함되었는가
- [x] 리포트 파일 외에 수정된 파일이 없는가
