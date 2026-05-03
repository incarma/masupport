# Frontend 공통 가이드

> **대상 독자**: 이 프로젝트에서 새 페이지를 만들거나 기존 페이지를 수정하는 개발자 (LLM 포함)
> **목적**: 공통 유틸을 중복 구현하거나, id/dataset을 잘못 변경해 전체가 깨지는 사고를 예방한다.

---

## 1. 공통 JS 파일 목록 및 역할

### 1-1. `static/js/common/` 루트

| 파일 | 타입 | 역할 |
|---|---|---|
| `manage_boot.js` | ESM (`type="module"`) | Partner 관리 페이지 공통 초기화 — YM select, autoLoad payload, superuser 셀렉터 위임 |
| `part_branch_selector.js` | IIFE (non-module) | 부문/부서/지점 연쇄 select 로더 (2단/3단). `window.loadPartsAndBranches` 노출 |
| `search_user_modal.js` | IIFE (non-module) | `#searchUserModal` 공통 대상자 검색 모달 바인딩 |
| `json_boot_bridge.js` | IIFE (non-module) | `json_script` 태그 → `window[name]` 전역 연결 (CSP inline 제거 대응) |
| `csrf_window.js` | IIFE (non-module) | `window.csrfToken` 주입 (레거시 호환 유지용) |
| `prevent_form_submit.js` | 이벤트 위임 | `data-prevent-submit="true"` form의 Enter/submit 차단 |
| `auto_submit_controls.js` | 이벤트 위임 | `data-auto-submit="true"` select 변경 시 form 자동 submit |
| `confirm_submit.js` | 이벤트 위임 | `data-confirm-submit` form submit 전 confirm 다이얼로그 |
| `redirect_buttons.js` | 이벤트 위임 | `data-redirect-url` 버튼 클릭 시 페이지 이동 |
| `approval_upload_validation.js` | 특수 목적 | `#approvalUploadForm` Bootstrap 유효성 표시 (commission 전용) |

### 1-2. `static/js/common/manage/` (ESM 모듈, `manage_boot.js`와 페이지 index.js에서 import)

| 파일 | 주요 export |
|---|---|
| `csrf.js` | `getCSRFToken()` — CSRF 토큰 3단계 우선순위 조회 |
| `dataset.js` | `ds(rootEl, key, fallback)`, `getDatasetUrl(rootEl, keys[])` |
| `loading.js` | `showLoading(msg?)`, `hideLoading()` — `#loadingOverlay` 제어 |
| `ym.js` | `pad2(n)`, `selectedYM(yearEl, monthEl)`, `normalizeYM(ym)` |
| `http.js` | `readJsonOrThrow(res, fallback?)`, `isSuccessJson(data)` |
| `datatables.js` | `canUseDataTables(el)`, `destroyDataTableIfExists(el)`, `safeAdjust(dt)` |

### 1-3. `static/js/common/forms/` (ESM 모듈)

| 파일 | 주요 export |
|---|---|
| `dom.js` | `qs(sel, root?)`, `qsa(sel, root?)`, `safeOn(el, ev, fn)`, `show(el)`, `hide(el)` |
| `premium.js` | `bindPremiumInputs({ formEl, inputSelector?, removeCommaOnSubmit? })` |
| `rows.js` | `initRowController({ rowSelector, addBtnId, resetBtnId, removeBtnClass, ... })` |

---

## 2. `manage_boot.js` 사용 패턴

### 2-1. initManageBoot(contextName) 호출 규약

```javascript
// partner 관리 페이지 index.js (type="module")
import { initManageBoot } from "/static/js/common/manage_boot.js";

const ctx = initManageBoot("structure"); // contextName 문자열 전달
if (!ctx) return; // root 없으면 null 반환 — 진행 중단 필수

const { root, boot, user } = ctx;
// 이후 fetch 등은 index.js가 직접 수행
```

`initManageBoot`는 **fetch를 실행하지 않는다**. YM select 초기화와 autoLoad payload 준비만 담당하며, 실제 데이터 요청은 각 페이지의 `index.js`가 `window.__manageBootAutoPayload[ctxName]`을 읽어 수행한다.

### 2-2. contextName → rootId 매핑 전체

| contextName | rootId (DOM id) | Boot 전역 변수 |
|---|---|---|
| `"structure"` | `manage-structure` | `window.ManageStructureBoot` |
| `"rate"` | `manage-rate` | `window.ManageRateBoot` |
| `"efficiency"` | `manage-efficiency` | `window.ManageEfficiencyBoot` |
| `"grades"` | `manage-grades` | `window.ManageGradesBoot` |
| `"table"` | `manage-table` | `window.ManageTableBoot` |

Boot 전역 변수는 `json_boot_bridge.js`로 주입된다 (아래 §5 참조).

### 2-3. autoLoad 조건 (grade별)

| grade | 동작 |
|---|---|
| `head`, `leader` | `autoLoad=true` → `window.__manageBootAutoPayload[ctxName]` 자동 준비, `showSections()` 호출 |
| `superuser` | autoLoad payload **건너뜀**. 대신 `part_branch_selector.js`에 셀렉터 로딩 위임 |
| 기타 | `boot.autoLoad` 값에 따름 (명시 없으면 skip) |

```javascript
// autoLoad payload 사용 패턴 (index.js)
const payload = window.__manageBootAutoPayload?.["structure"];
if (payload?.ym && payload?.branch) {
  await fetchData(payload.ym, payload.branch);
}
```

### 2-4. BFCache 가드 패턴

`manage_boot.js`는 `window.__manageBootInited[rootGuardKey]` 플래그로 중복 초기화를 막는다. 각 페이지 `index.js`도 별도의 1회 가드를 두어야 한다.

```javascript
// index.js 권장 패턴
const root = document.getElementById("manage-structure");
if (!root || root.dataset.indexInited === "1") return;
root.dataset.indexInited = "1";

window.addEventListener("pageshow", (e) => {
  if (e.persisted) {
    // BFCache 복귀 시에도 재호출 방지됨
  }
});
```

### 2-5. bindEllipsisTooltips (옵션 유틸)

```javascript
import { bindEllipsisTooltips } from "/static/js/common/manage_boot.js";
// #inputTable 내 input/select의 말줄임 + hover title 동기화
bindEllipsisTooltips(root); // root 없으면 document 기준
```

---

## 3. `part_branch_selector.js` 사용 패턴

### 3-1. 2단(part→branch) vs 3단(channel→part→branch) 분기 조건

`#channelSelect` DOM 요소의 존재 여부로 **자동 판별**한다. 별도 설정 불필요.

| DOM 구성 | 동작 모드 |
|---|---|
| `#partSelect` + `#branchSelect` | 2단 (Mode B) |
| `#channelSelect` + `#partSelect` + `#branchSelect` | 3단 (Mode A) |

### 3-2. window.loadPartsAndBranches(root) 위임 규약

```javascript
// manage_boot.js에서 superuser 한정 자동 호출됨
// 직접 호출이 필요한 경우:
await window.loadPartsAndBranches("manage-structure"); // rootId 문자열
await window.loadPartsAndBranches(rootElement);        // 또는 DOM 요소
```

- `part_branch_selector.js`가 `DOMContentLoaded` 이전에 로드되지 않아도, `manage_boot.js`가 최대 12회(250ms 간격) 폴링하며 함수 노출을 기다린다.
- `root.dataset.partBranchBound === "1"` 가드로 중복 바인딩을 방지한다.

### 3-3. ROOT_IDS 목록 (변경 시 영향 범위)

```javascript
const ROOT_IDS = [
  "manage-structure",
  "manage-rate",
  "manage-table",
  "manage-efficiency",
  "manage-grades",
];
```

**주의**: 이 목록에 없는 id를 가진 페이지에서는 `part_branch_selector.js`의 `autoInit()`이 동작하지 않는다. 새 관리 페이지를 추가할 때 이 목록도 함께 업데이트해야 한다.

### 3-4. 초기값 복원 방법

URL 파라미터 또는 hidden input으로 초기 선택값을 전달한다.

```html
<!-- hidden input 방식 (서버 render) -->
<input type="hidden" id="selectedChannelInit" value="{{ selected_channel }}">
<input type="hidden" id="selectedPartInit" value="{{ selected_part }}">
<input type="hidden" id="selectedBranchInit" value="{{ selected_branch }}">

<!-- URL 파라미터 방식 -->
/partner/manage/?channel=채널명&part=부서명&branch=지점명
```

### 3-5. API 엔드포인트 우선순위

```html
<!-- dataset으로 override 가능 -->
<div id="manage-structure"
     data-fetch-channels-url="{% url 'partner:fetch_channels' %}"
     data-fetch-parts-url="{% url 'partner:fetch_parts' %}"
     data-fetch-branches-url="{% url 'partner:fetch_branches' %}">
```

미지정 시 fallback: `/partner/ajax/fetch-channels/`, `/partner/ajax/fetch-parts/`, `/partner/ajax/fetch-branches/`

### 3-6. 검색 버튼 자동 비활성화

`#btnSearchPeriod` 또는 `#btnSearch` (우선순위 순)를 자동으로 찾아 `branchSelect` 값이 없으면 `disabled=true`로 설정한다.

---

## 4. `search_user_modal.js` 사용 패턴

### 4-1. 필수 DOM 구조

```html
<!-- 공용 컴포넌트 include -->
{% include 'components/search_user_modal.html' %}

<!-- 검색 모달 열기 버튼 (tr.input-row 안에 위치해야 row 자동 매핑됨) -->
<button type="button" class="btnOpenSearch btn btn-sm btn-outline-secondary">검색</button>
```

### 4-2. search_url dataset 주입

```html
<!-- 방법 1: 모달 요소에 직접 -->
<div id="searchUserModal" data-search-url="{% url 'board:search_user' %}">

<!-- 방법 2: 페이지 루트에 -->
<div id="manage-structure" data-search-user-url="{% url 'board:search_user' %}">
```

URL 우선순위: `modalEl.dataset.searchUrl` → `root.dataset.searchUserUrl` → fallback `/board/search-user/` → `/api/accounts/search-user/`

### 4-3. userSelected 이벤트 계약

사용자 선택 시 `document`와 `window` 양쪽으로 `CustomEvent("userSelected")` 발행된다.

```javascript
document.addEventListener("userSelected", (e) => {
  const { id, name, branch, affiliation_display, rank, part,
          team_a, team_b, team_c, regist, enter, quit } = e.detail;
  // 처리
});
```

### 4-4. Row 자동 채우기 (일반 페이지)

`.btnOpenSearch`를 클릭한 시점의 `tr.input-row`를 `activeRow`로 기억한 뒤, 검색 결과 선택 시 해당 행의 필드에 자동 채운다.

| 필드 키 우선순위 | 채워지는 값 |
|---|---|
| `tg_name` > `target_name` | 이름 |
| `tg_id` > `target_id` | 사번 |
| `tg_branch` > `target_branch` | `affiliation_display` 또는 branch/팀 조합 |
| `tg_rank` > `rank` | 직급 |
| `tg_part` > `target_part` | 부서 |
| `.tg_display` > `.target_display` | `이름(사번)` 형식 표시용 |

### 4-5. 페이지별 예외 동작

| 페이지 root id | 동작 |
|---|---|
| `collect-home` | Row 채우기 없음. `userSelected` 이벤트만 발행. 검색 모달만 닫음 (피드백 모달 유지) |
| `deposit-home` | **이벤트 발행 금지**. 모달 닫고 `/commission/deposit/?user=<id>` 로 즉시 이동 |
| 그 외 | Row 자동 채우기 + `userSelected` 이벤트 발행 |

> **주의**: `deposit-home`에서 `userSelected` 이벤트를 발행하면 진행 중인 fetch가 중단되어 "Failed to fetch" 오류가 발생한다. 이 예외 분기는 의도적이다.

### 4-6. 검색 scope

| 페이지 root id | scope |
|---|---|
| `manage-structure`, `manage-rate`, `manage-efficiency`, `manage-calculate`, `support-form` | `branch` (지점 필터링) |
| 그 외 | `default` (전체) |

`scope=branch`이고 `superuser` grade인 경우, `branchSelect` 값이 없으면 검색 실행을 차단하고 안내 메시지를 표시한다.

---

## 5. 소형 공통 유틸 사용 규약

### 5-1. `manage/dataset.js`

```javascript
import { ds, getDatasetUrl } from "/static/js/common/manage/dataset.js";

// 단일 키 조회
const ym = ds(root, "selectedYm", ""); // root.dataset.selectedYm, 없으면 ""

// 여러 키 후보 중 첫 번째 유효값
const url = getDatasetUrl(root, ["fetchUrl", "apiUrl", "dataUrl"]);
```

### 5-2. `manage/csrf.js`

```javascript
import { getCSRFToken } from "/static/js/common/manage/csrf.js";

// 우선순위: window.csrfToken → [name=csrfmiddlewaretoken] → csrftoken cookie
const token = getCSRFToken();

// POST 요청 예시
fetch(url, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-CSRFToken": getCSRFToken(),
  },
  body: JSON.stringify(payload),
});
```

**신규 코드에서는 `csrf_window.js`의 `window.csrfToken`을 직접 참조하지 말고 `getCSRFToken()`을 사용한다.**

### 5-3. `manage/loading.js`

```javascript
import { showLoading, hideLoading } from "/static/js/common/manage/loading.js";

// 반드시 #loadingOverlay 요소가 DOM에 존재해야 동작함
showLoading("데이터 저장 중...");
try {
  await doSomething();
} finally {
  hideLoading();
}
```

HTML 구조 (템플릿에 포함 필요):
```html
<div id="loadingOverlay" hidden
     style="position:fixed;inset:0;background:rgba(255,255,255,.6);z-index:9999;
            display:flex;align-items:center;justify-content:center;">
  <div class="spinner-border text-primary" role="status"></div>
  <p class="mt-2 ms-2 mb-0">처리 중...</p>
</div>
```

### 5-4. `manage/ym.js`

```javascript
import { pad2, selectedYM, normalizeYM } from "/static/js/common/manage/ym.js";

pad2(5)          // → "05"
pad2(12)         // → "12"

selectedYM(yearEl, monthEl)  // → "2026-05" (요소 value 기반, 없으면 "")

normalizeYM("202605")        // → "2026-05"
normalizeYM("2026-05")       // → "2026-05" (이미 정규형)
normalizeYM("2026/05")       // → "2026-05"
```

### 5-5. `manage/http.js`

```javascript
import { readJsonOrThrow, isSuccessJson } from "/static/js/common/manage/http.js";

const res = await fetch(url, options);
const data = await readJsonOrThrow(res); // 비-JSON 응답(로그인 만료 등) 자동 방어
// ok=false면 data.message로 throw

if (!isSuccessJson(data)) throw new Error(data.message || "실패");
```

`readJsonOrThrow`는 응답이 HTML(로그인 리다이렉트, 서버 에러 페이지)인 경우 상태 코드에 따라 명확한 한국어 에러 메시지를 던진다.

### 5-6. `json_boot_bridge.js` 사용 패턴

```html
<!-- 템플릿: json_script로 데이터 렌더링 -->
{{ boot_data|json_script:"boot-efficiency" }}

<!-- json_boot_bridge로 window 전역에 연결 (inline script 대체) -->
<script src="{% static 'js/common/json_boot_bridge.js' %}?v={% now 'U' %}"
        data-json-id="boot-efficiency"
        data-window-name="ManageefficiencyBoot"></script>
```

`data-json-id`: DOM의 `json_script` 요소 id  
`data-window-name`: 노출할 `window` 프로퍼티 이름

### 5-7. `csrf_window.js` 사용 패턴

```html
<!-- base.html에 이미 로드됨. 페이지별 추가 불필요 -->
<!-- 목적: window.csrfToken 주입 (레거시 JS 호환) -->
<!-- 신규 코드는 manage/csrf.js의 getCSRFToken() 사용 권장 -->
```

### 5-8. 이벤트 위임 유틸 3종

아래 3개 파일은 `base.html`에서 전역으로 로드된다. 별도 import 불필요.

```html
<!-- prevent_form_submit.js -->
<form id="controlsForm" data-prevent-submit="true">
  <!-- Enter 키로 인한 의도치 않은 reload 방지 -->
</form>

<!-- auto_submit_controls.js -->
<select name="year" data-auto-submit="true">
  <!-- 변경 즉시 폼 submit -->
</select>

<!-- confirm_submit.js -->
<form method="post" data-confirm-submit="정말 삭제하시겠습니까?">
  <!-- submit 전 confirm 표시 -->
</form>

<!-- redirect_buttons.js -->
<button type="button" data-redirect-url="{% url 'board:post_list' %}">
  목록으로
</button>
```

---

## 6. CSS 계층 구조

### 6-1. 파일별 역할

| 파일 | 로드 위치 | 역할 |
|---|---|---|
| `static/css/base.css` | `base.html` `<head>` 항상 | 전역 토큰(`:root`), 공통 컴포넌트(navbar/button/form/card), 전역 유틸 클래스 |
| `static/css/fixes.css` | `base.html` 맨 마지막 | 전역 최소 fix — `#mainSheet min-width`, `#manage-efficiency` 테이블 fix, `.privacy-watermark` |
| `static/css/plugins/datatables.css` | 필요한 페이지만 | DataTables 버튼 스킨 |
| `static/css/apps/<앱>.css` | 각 앱 템플릿 `app_css` 블록 | 앱 전용 스타일 (스코프 루트 하위에서만 동작) |

### 6-2. 로드 순서 (base.html 기준)

```
base.css → (plugins/datatables.css) → [앱별 app_css 블록] → fixes.css
```

`fixes.css`는 **항상 마지막**에 로드되어 모든 앱 스타일을 덮을 수 있어야 한다.

### 6-3. 앱 CSS 로드 패턴

```html
{% block app_css %}
<link rel="stylesheet" href="{% static 'css/apps/board.css' %}?v={% now 'U' %}">
{% endblock %}
```

`base.html`에는 직접 넣지 않는다. 반드시 `app_css` 블록을 통해 해당 앱 베이스 템플릿에서만 로드한다.

### 6-4. base.css 수정 금지

전역 오염 방지 원칙: **`base.css`에 새 스타일을 추가하지 않는다**. 앱 전용 규칙은 반드시 `static/css/apps/<앱명>.css`에 작성하고 스코프 루트 선택자 안에 넣는다.

---

## 7. 앱별 CSS 스코프 루트 선택자 전체 목록

| 앱/파일 | 스코프 루트 선택자 | 방식 |
|---|---|---|
| `board.css` | `.board-scope` | class |
| `manual.css` | `#manual-detail` | ID (세부 페이지) |
| `partner.css` | `#manage-structure` | ID |
| `partner.css` | `#manage-rate` | ID |
| `partner.css` | `#manage-efficiency` | ID |
| `partner.css` | `#manage-table` | ID |
| `partner.css` | `#manage-grades` | ID |
| `partner.css` | `#esign-confirm` | ID |
| `dash.css` | `#dash-sales` | ID |
| `dash.css` | `.dash-retention-page` | class |
| `commission.css` | `#suretyTable`, `#otherTable` | ID (컴포넌트) |
| `commission.css` | `#collectTableHead`, `#collectTableBody` | ID (컴포넌트) |
| `support.css` | `.support-scope` | class |
| `index.css` | 전역 (`:root` 토큰 + section 클래스) | 랜딩 페이지 전용 |

### 7-1. CSS 변수 정의 위치 예시 (partner.css)

```css
#manage-structure {
  --ctl-w-ym: 90px;
  --ctl-w-org: 160px;
  --tbl-font-td: 13px;
  --tbl-font-th: 11.5px;
  --c-name: 120px;   /* 컬럼 폭은 각 ID 루트 안에 선언 */
}

/* 반드시 루트 하위에서만 사용 */
#manage-structure .c-name { width: var(--c-name); }
```

---

## 8. LLM 함정 포인트

### 8-1. "공통 유틸 있는데 새로 만드는" 패턴 방지

아래 기능은 **이미 공통 유틸로 존재한다**. 새로 구현하지 말 것.

| 하려는 것 | 사용해야 할 것 |
|---|---|
| CSRF 토큰 가져오기 | `manage/csrf.js` → `getCSRFToken()` |
| `#loadingOverlay` 표시/숨김 | `manage/loading.js` → `showLoading()` / `hideLoading()` |
| YYYY-MM 패딩, select에서 YM 읽기 | `manage/ym.js` → `pad2()`, `selectedYM()` |
| fetch 응답에서 JSON 안전하게 읽기 | `manage/http.js` → `readJsonOrThrow()` |
| dataset 키 안전하게 읽기 | `manage/dataset.js` → `ds()` |
| 사용자 검색 모달 | `search_user_modal.js` + `templates/components/search_user_modal.html` |
| 부문/부서/지점 select 연쇄 로딩 | `part_branch_selector.js` + `window.loadPartsAndBranches()` |
| form Enter 차단 | `prevent_form_submit.js` + `data-prevent-submit="true"` |
| select 변경 시 자동 submit | `auto_submit_controls.js` + `data-auto-submit="true"` |
| 버튼 클릭 시 URL 이동 | `redirect_buttons.js` + `data-redirect-url="..."` |
| submit 전 confirm | `confirm_submit.js` + `data-confirm-submit="메시지"` |
| `window[name]` = json_script 데이터 | `json_boot_bridge.js` + `data-json-id` / `data-window-name` |
| 보험료 입력 천단위 콤마 | `forms/premium.js` → `bindPremiumInputs()` |
| DOM querySelector 유틸 | `forms/dom.js` → `qs()`, `qsa()`, `safeOn()` |
| inputTable 행 추가/제거/초기화 | `forms/rows.js` → `initRowController()` |

### 8-2. id/data-* 변경 시 JS 전체가 깨지는 이유

아래 id와 data-* 속성은 **여러 JS 파일이 하드코딩으로 참조한다**. 변경하면 연결된 모든 JS가 동시에 깨진다.

#### 절대 변경 금지 — JS가 하드코딩으로 참조하는 id

| id | 참조하는 파일 |
|---|---|
| `manage-structure` | `manage_boot.js`, `part_branch_selector.js`, `search_user_modal.js` |
| `manage-rate` | 위와 동일 |
| `manage-efficiency` | 위와 동일 |
| `manage-grades` | `manage_boot.js`, `part_branch_selector.js` |
| `manage-table` | 위와 동일 |
| `channelSelect` | `part_branch_selector.js` (3단 모드 판별 기준) |
| `partSelect` | `part_branch_selector.js` |
| `branchSelect` | `part_branch_selector.js`, `search_user_modal.js` |
| `yearSelect` | `manage_boot.js` |
| `monthSelect` | `manage_boot.js` |
| `btnSearchPeriod`, `btnSearch` | `part_branch_selector.js` (검색 버튼 disabled 제어) |
| `inputSection` | `manage_boot.js` (autoLoad showSections) |
| `mainSheet` | `manage_boot.js` (autoLoad showSections) |
| `searchUserModal` | `search_user_modal.js` |
| `searchKeyword` | `search_user_modal.js` |
| `searchResults` | `search_user_modal.js` |
| `searchUserForm` | `search_user_modal.js` |
| `loadingOverlay` | `manage/loading.js` |
| `collect-home` | `search_user_modal.js` (예외 분기) |
| `deposit-home` | `search_user_modal.js` (예외 분기) |
| `support-form` | `search_user_modal.js` (scope 분기) |

#### dataset 키 계약 (변경 시 참조 JS 전체 확인 필요)

| dataset 키 | 사용처 |
|---|---|
| `data-user-grade` | `part_branch_selector.js`, `manage_boot.js`, `search_user_modal.js` |
| `data-fetch-channels-url` | `part_branch_selector.js` |
| `data-fetch-parts-url` | `part_branch_selector.js` |
| `data-fetch-branches-url` | `part_branch_selector.js` |
| `data-search-url` | `search_user_modal.js` (모달에 직접) |
| `data-search-user-url` | `search_user_modal.js` (페이지 루트에) |
| `data-part-branch-bound` | `part_branch_selector.js` (중복 바인딩 가드) |
| `data-json-id`, `data-window-name` | `json_boot_bridge.js` |
| `data-prevent-submit` | `prevent_form_submit.js` |
| `data-auto-submit` | `auto_submit_controls.js` |
| `data-confirm-submit` | `confirm_submit.js` |
| `data-redirect-url` | `redirect_buttons.js` |

### 8-3. IIFE vs ESM 혼용 주의

| 파일 | 타입 | 주의 |
|---|---|---|
| `manage_boot.js` | ESM | `<script type="module">` 또는 `import`로만 사용. `window.initManageBoot` 없음 |
| `part_branch_selector.js` | IIFE | `<script src="...">` 로드만으로 동작. import 불가 |
| `search_user_modal.js` | IIFE | 동상 |
| `manage/*.js`, `forms/*.js` | ESM | `import`로만 사용 |

`manage_boot.js`에서 `import { initManageBoot }` 하려면 해당 페이지의 script 태그가 `type="module"`이어야 한다.

### 8-4. superuser grade 관련 흔한 실수

- `superuser`는 `head`/`leader`처럼 자동으로 특정 지점의 데이터를 가지지 않는다.
- `manage_boot.js`는 `superuser`에게 autoLoad payload를 생성하지 않는다.
- `superuser`가 데이터를 조회하려면 반드시 `part_branch_selector.js`를 통해 지점을 선택해야 한다.
- `search_user_modal.js`에서 `superuser`가 `scope=branch`인 페이지에서 검색하려면 `branchSelect`에 값이 있어야 한다.

### 8-5. fixes.css는 전역 fix 전용

새 앱을 위해 `fixes.css`에 스타일을 추가하지 않는다. `fixes.css`는 정말 전역이어야 하는 최소한의 방어(현재 3개 규칙)만 포함한다.

---

## 9. 빠른 참조: 새 관리 페이지 체크리스트

새 Partner 관리 페이지 추가 시 확인할 항목:

- [ ] `part_branch_selector.js`의 `ROOT_IDS` 배열에 새 id 추가
- [ ] `manage_boot.js`의 `resolveRootId()` / `resolveBoot()` 에 새 contextName 추가
- [ ] `search_user_modal.js`의 `getActiveRoot()` 에 새 id 추가 (모달 사용 시)
- [ ] `partner.css`에 새 id 기준 스코프 섹션 추가
- [ ] `json_boot_bridge.js` + `json_script` 로 Boot 데이터 전달
- [ ] `id="yearSelect"`, `id="monthSelect"` 요소 포함 (manage_boot YM 초기화 대상)
- [ ] `id="loadingOverlay"` 요소 포함 (`showLoading` 사용 시)
