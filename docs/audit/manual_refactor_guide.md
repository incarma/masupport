# manual 앱 리팩토링 지침서

> 생성일: 2026-05-14  
> 점검 기준 커밋: HEAD(develop)  
> 원칙: **기능 변화 0** — 코드 수정 없음, 점검 결과만 기록  

---

## 0. 점검 요약 대시보드

| 레이어 | 항목 | 🔴 위반 | 🟡 개선 권장 | ✅ 준수 | ➖ 해당없음 |
|---|---|---|---|---|---|
| Python | A-01 서비스 레이어 경유 | 0 | 0 | 1 | 0 |
| Python | A-02 ensure_superuser_or_403 반환값 | 0 | 0 | 1 | 0 |
| Python | A-03 json_body/ok/fail 일관성 | 0 | 0 | 1 | 0 |
| Python | A-04 감사 로그 누락 | 0 | 1 | 0 | 0 |
| Python | A-05 중복 구현 | 1 | 0 | 0 | 0 |
| Python | A-06 management commands 중복 | 1 | 1 | 0 | 0 |
| JavaScript | B-01 CSRF 중복 구현 | 1 | 0 | 0 | 0 |
| JavaScript | B-02 ManualShared 사용 일관성 | 1 | 0 | 0 | 0 |
| JavaScript | B-03 BFCache 가드 | 0 | 1 | 0 | 0 |
| JavaScript | B-04 URL 하드코딩 | 0 | 0 | 1 | 0 |
| JavaScript | B-05 중복 유틸 함수 | 1 | 0 | 0 | 0 |
| JavaScript | B-06 이벤트 리스너 정리 | 0 | 1 | 0 | 0 |
| CSS | C-01 :root 전역 변수 | 0 | 0 | 1 | 0 |
| CSS | C-02 스코프 없는 전역 클래스 | 1 | 0 | 0 | 0 |
| CSS | C-03 JS 의존 CSS 클래스 불일치 | 0 | 0 | 1 | 0 |
| Template | D-01 파일 URL 직접 노출 | 0 | 0 | 1 | 0 |
| Template | D-02 sanitize 필터 미적용 | 0 | 0 | 1 | 0 |
| Template | D-03 dataset 주입 일관성 | 0 | 1 | 0 | 0 |
| Template | D-04 partials include 구조 | 0 | 1 | 0 | 0 |

**집계: 🔴 위반 5건 / 🟡 개선 권장 6건**

---

## 1. Python 레이어 점검 결과

### A-01. 서비스 레이어 경유 원칙

✅ **준수**

`views/` 레이어는 ORM을 직접 호출하지만, 이는 이 프로젝트에서 `utils/` 레이어가 서비스 레이어 역할을 담당하는 구조이므로 허용 범위다. 비즈니스 판단 로직은 `utils/permissions.py`, `utils/rules.py`로 분리되어 있고, views는 HTTP 처리 + ORM 호출 + 응답 반환의 조합만 수행한다.

- `filter_manuals_for_user()` → `utils/permissions.py` (SSOT)
- `ensure_default_section()` → `utils/rules.py`
- `access_to_flags()` → `utils/rules.py`

직접 ORM 호출(`Manual.objects.create`, `ManualSection.objects.create` 등)은 views 레이어에 존재하지만, 각각 단순 CRUD이며 별도 service 레이어로 추출하지 않아도 되는 수준의 로직이다. 프로젝트의 현재 레이어 규약과 일치한다.

---

### A-02. `ensure_superuser_or_403()` 반환값 처리

✅ **준수**

모든 AJAX views에서 `denied = ensure_superuser_or_403(request); if denied: return denied` 패턴을 일관되게 사용한다. 반환값 무시 사례 없음.

```python
# views/manual.py:31-33 (공통 패턴)
denied = ensure_superuser_or_403(request)
if denied:
    return denied
```

`views/pages.py`의 page views는 `@grade_required("superuser")` 데코레이터를 사용하여 별도 패턴이지만 동일 목적을 달성한다. `manual_detail`, `manual_list`, `rules_home`은 `@not_inactive_required` 또는 데코레이터 없이 `manual_accessible_or_denied()`로 처리하며 정책상 올바르다.

---

### A-03. `json_body()` / `ok()` / `fail()` 사용 일관성

✅ **준수**

모든 AJAX views에서 `manual/utils/http.py`의 `json_body()`, `ok()`, `fail()`을 일관되게 사용한다.

- `JsonResponse()` 직접 생성 사례: 없음
- `request.POST` 직접 접근: 없음 (multipart의 경우 `request.POST.get()`은 허용 패턴임)
- `json.loads(request.body)` 직접 사용: 없음

`views/block.py`와 `views/attachment.py`는 multipart(FormData) 요청이므로 `request.POST.get()` / `request.FILES.get()`을 직접 사용하는데, 이는 JSON 바디가 아닌 multipart이므로 `json_body()` 비적용이 정상이다.

---

### A-04. 감사 로그(log_action) 누락 여부

🟡 **개선 권장** — 공수: 소

`views/pages.py`의 `manual_create()`와 `manual_edit()` (폼 기반 뷰)에 `log_action()` 호출이 없다.

```python
# views/pages.py:61-66
@grade_required("superuser")
def manual_create(request):
    """superuser 전용: 폼 기반 생성(관리용)"""
    if request.method == "POST":
        form = ManualForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.author = request.user
            obj.save()
            return redirect("manual:manual_detail", pk=obj.pk)
    # ← log_action(request, ACTION.MANUAL_CREATE, obj=obj, ...) 누락
```

```python
# views/pages.py:73-85
@grade_required("superuser")
def manual_edit(request, pk):
    ...
    if request.method == "POST":
        form = ManualForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return redirect("manual:manual_detail", pk=obj.pk)
    # ← log_action(request, ACTION.MANUAL_UPDATE, obj=obj, ...) 누락
```

**근거**: 이 두 뷰는 `urls.py`에 `/new/`와 `/<pk>/edit/`로 등록되어 있으며 실제로 관리용 폼 기반 생성/수정 경로다. AJAX 뷰(`manual_create_ajax`, `manual_update_title_ajax`, `manual_bulk_update_ajax`)는 모두 `log_action()`이 있으므로 폼 기반 뷰만 누락이다.

**개선 방법**: `form.save()` 이후 `log_action(request, ACTION.MANUAL_CREATE/MANUAL_UPDATE, obj=obj, ...)` 호출 추가.

`audit/constants.py`에 `ACTION.MANUAL_CREATE`, `ACTION.MANUAL_UPDATE` 모두 정의되어 있으므로 미정의 상수 사용 위험은 없다.

---

### A-05. 중복 구현 여부

🔴 **위반** — `views/block.py`에서 `sanitize_quill_html()` 이중 호출

```python
# views/block.py:29 (manual_block_add_ajax)
content = sanitize_quill_html(request.POST.get("content", ""))

# views/block.py:74 (manual_block_update_ajax)
content = sanitize_quill_html(request.POST.get("content", ""))
```

그런데 `ManualBlock.save()` 내에도 이미 호출이 있다:

```python
# models.py:146-149
def save(self, *args, **kwargs):
    from manual.utils.sanitize import sanitize_quill_html
    self.content = sanitize_quill_html(self.content)
    super().save(*args, **kwargs)
```

**영향**: view에서 1번, `ManualBlock.save()`에서 1번, 총 2번 sanitize가 실행된다. `sanitize_quill_html()`은 idempotent(멱등적)이므로 결과는 동일하지만, 성능 낭비 및 "SSOT 호출 위치"가 불명확해지는 문제가 있다.

**주의**: `ManualBlock.save()`의 sanitize 호출은 "절대 수정 금지" 항목이다. 따라서 view에서의 중복 호출 제거가 권장되나, 현재 view에서는 `content` 변수에 sanitized 값을 할당 후 곧바로 `ManualBlock.objects.create(... content=content ...)`에 전달하므로 model.save()에서 한 번 더 실행된다. 중복 sanitize는 동작에 영향을 주지 않는다.

**처리 방침**: view에서의 `sanitize_quill_html()` 호출을 제거하여 model의 SSOT 호출에 위임하는 것이 권장된다. 단, 기능 변화 0 원칙에 따라 현 점검 회차에서는 수정하지 않는다.

---

### A-06. management/commands 코드 중복

🔴 **위반** — `cleanup_missing_manual_images.py`가 `cleanup_manual_files.py`의 기능을 중복 구현

두 파일 모두 `ManualBlock.image` 누락 파일 참조를 점검하는 완전히 동일한 로직을 구현한다:

```python
# cleanup_missing_manual_images.py:21-41 (전체 handle 메서드)
qs = ManualBlock.objects.exclude(image="").exclude(image__isnull=True)
for b in qs.iterator(chunk_size=200):
    if not b.image.storage.exists(b.image.name):
        ...
        if apply_changes:
            b.image = None
            b.save(update_fields=["image"])

# cleanup_manual_files.py:101-128 (_cleanup_missing_block_images 메서드)
qs = ManualBlock.objects.exclude(image="").exclude(image__isnull=True)
for block in qs.iterator(chunk_size=200):
    if block.image.storage.exists(block.image.name):
        continue
    ...
    if apply_changes:
        block.image = None
        block.save(update_fields=["image"])
```

**차이점 유일**: `cleanup_manual_files.py`는 `ManualBlockAttachment` 누락 참조 정리 기능을 추가로 보유하며, 진입점도 더 정교하다(`--delete-missing-attachments`, `--force` 옵션 포함, `log_action()` 호출 포함).

🟡 **개선 권장** — `cleanup_missing_manual_images.py`는 `cleanup_manual_files.py`의 기능 서브셋  

`cleanup_missing_manual_images.py`는 `cleanup_manual_files.py`가 도입되기 이전의 레거시 명령으로 보인다. `cleanup_manual_files.py`는 `log_action()` 호출(감사 로깅)도 포함하고 더 안전한 `--force` 가드도 있어 운영 환경에서 선호돼야 한다.

**개선 방안**: `cleanup_missing_manual_images.py`를 deprecated 처리하거나 `cleanup_manual_files.py` 호출 래퍼로 교체. 단, 명령어 이름이 외부 스크립트/문서에서 참조될 수 있으므로 삭제 전 확인 필요.

---

## 2. JavaScript 레이어 점검 결과

### B-01. CSRF 토큰 조회 중복 구현 (RULE-Q-01)

🔴 **위반** — `create_manual_modal.js`에서 `window.csrfToken`을 직접 참조하며, `_shared.js`의 `postJson()`을 사용하지 않고 `fetch()`를 직접 구현

```javascript
// create_manual_modal.js:77
const csrf = window.csrfToken;

// create_manual_modal.js:83-93
const res = await fetch(createUrl, {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRFToken": csrf,
    "X-Requested-With": "XMLHttpRequest",
  },
  body: JSON.stringify({ title, access }),
});
```

`ManualShared.postJson()`이 `_shared.js`에 존재하고 완전히 동일한 기능을 제공함에도 직접 `fetch()` 구현을 한다. 또한 `window.csrfToken`을 직접 읽는 것은 `common/manage/csrf.js`의 `getCSRFToken()` SSOT를 우회한 것이다.

**부분 완화 요인**: `window.csrfToken`은 `csrf_window.js`가 주입하므로 동작은 하지만, RULE-Q-01은 "파일마다 재구현 금지"로 명시되어 있다. `_shared.js`의 `getCSRFTokenFromForm()`은 `window.csrfToken`을 반환하는 래퍼이므로 실질적으로 동일하나, `postJson()`을 통해 호출해야 한다.

**또한**: `create_manual_modal.js` 상단에 ManualShared 폴백 구현이 있다:

```javascript
// create_manual_modal.js:12-43
const toStr = S.toStr || ((v) => String(v ?? "").trim());
const setBtnLoading = S.setBtnLoading || ((btn, isLoading, loadingText, defaultText) => {
  // ... 전체 재구현
});
const showErrorBox = S.showErrorBox || ((errBox, msg) => { ... });
const clearErrorBox = S.clearErrorBox || ((errBox) => { ... });
const safeReadJson = S.safeReadJson || (async (res) => { ... });
```

이 폴백 구현 블록은 `_shared.js` 로드 실패를 방어하기 위한 것이나, 실제로는 매 파일에 함수를 재구현하는 패턴으로 RULE-Q-01 위반의 심도를 높인다.

---

### B-02. `ManualShared` (_shared.js) 사용 일관성

🔴 **위반** — `create_manual_modal.js`가 `ManualShared.postJson()`을 사용하지 않고 `fetch()`를 직접 구현

**`ManualShared` 함수별 사용 현황**:

| 함수 | manual_list_edit.js | manual_detail_section_sort.js | manual_detail_block/index.js | manual_detail_block/sort_blocks.js | create_manual_modal.js |
|---|---|---|---|---|---|
| `toStr` | ✅ | ✅ | ✅ | ✅ | 폴백 재구현 |
| `isDigits` | ✅ | ✅ | ✅ | ✅ | ➖ |
| `getCSRFTokenFromForm` | ✅ | ✅ | ✅ | ➖(인자수신) | ❌ 미사용 |
| `postJson` | ✅ | ✅ | ✅ | ✅ | ❌ 미사용(직접 fetch) |
| `postForm` | ➖ | ➖ | ✅ | ➖ | ➖ |
| `setBtnLoading` | ✅ | ➖ | ➖ | ➖ | 폴백 재구현 |
| `showErrorBox` | ➖ | ➖ | ✅ | ➖ | 폴백 재구현 |
| `clearErrorBox` | ➖ | ➖ | ✅ | ➖ | 폴백 재구현 |
| `safeReadJson` | ➖ | ➖ | ➖(내부사용) | ➖(내부사용) | 폴백 재구현 |
| `formatBytes` | ➖ | ➖ | ✅ | ➖ | ➖ |

`create_manual_modal.js` 외 모든 파일은 `ManualShared` API를 경유하며 일관되게 동작한다.

---

### B-03. BFCache 가드 패턴 일관성

🟡 **개선 권장** — 공수: 소

| 파일 | 타입 | BFCache 가드 |
|---|---|---|
| `_shared.js` | IIFE | `if (window.ManualShared) return;` ✅ |
| `create_manual_modal.js` | IIFE | `if (!modal || modal.dataset.bound) return;` ✅ |
| `manual_list_edit.js` | `type="module"`로 로드됨(partial) | `if (listEl.dataset.bound === "true") return;` ✅ |
| `manual_detail_subnav.js` | IIFE | 가드 없음 ⚠️ |
| `manual_detail_section_sort.js` | IIFE | `htmlEl.dataset.manualSectionSortBound === "true"` ✅ |
| `manual_detail_block/index.js` | ESM | `document.documentElement.dataset.manualDetailBound === "true"` ✅ |

`manual_detail_subnav.js`는 IIFE이고 BFCache 가드가 없다. `rebuildNow()`가 최초 1회 자동 실행되는데, 브라우저 BFCache로 페이지가 복원될 경우 `sectionsEl`이 있으면 다시 실행되어 Subnav가 중복 초기화될 수 있다. IntersectionObserver가 있을 경우 중복 observe 문제가 발생할 수 있다.

```javascript
// manual_detail_subnav.js:11-14
(() => {
  const subnavEl = document.getElementById("manualSubnav");
  const sectionsRoot = document.getElementById("manualSections");
  if (!subnavEl || !sectionsRoot) return;
  // ← dataset.inited 또는 pageshow 가드 없음
```

**개선 방법**: IIFE 시작 시 `if (subnavEl.dataset.inited === "1") return; subnavEl.dataset.inited = "1";` 추가.

---

### B-04. URL 하드코딩 여부

✅ **준수**

모든 AJAX URL이 HTML의 `data-*` dataset 또는 boot element의 dataset에서 읽힌다.

- `manual_list_edit.js`: `bootFromDom.reorderUrl`, `bootFromDom.deleteUrl`, `bootFromDom.bulkUpdateUrl`
- `manual_detail_block/index.js`: `bootEl.dataset.sectionTitleUpdateUrl` 등
- `create_manual_modal.js`: `modal.dataset.createUrl`
- `manual_detail_section_sort.js`: `sectionsEl.dataset.sectionReorderUrl`

JS 파일 내 `/manual/...` URL 하드코딩 사례: 없음.

---

### B-05. 중복 유틸 함수

🔴 **위반** — `create_manual_modal.js`에 `_shared.js` 함수 재구현

`create_manual_modal.js`는 `ManualShared`가 로드되지 않은 경우의 폴백으로 아래 함수를 재구현한다:

```javascript
// create_manual_modal.js:12-43 (폴백 블록)
const toStr = S.toStr || ((v) => String(v ?? "").trim());
const setBtnLoading = S.setBtnLoading || (...) => { /* 40줄 재구현 */ };
const showErrorBox = S.showErrorBox || (...) => { /* 재구현 */ };
const clearErrorBox = S.clearErrorBox || (...) => { /* 재구현 */ };
const safeReadJson = S.safeReadJson || (async (res) => { /* 재구현 */ });
```

이 코드들은 `_shared.js`의 공개 API와 완전히 동일한 기능을 하며, RULE-Q-01의 "파일마다 재구현 금지" 원칙을 위반한다.

**`_shared.js`로 이동 가능한 중복 함수 목록**:

| 함수 | 현재 위치 | _shared.js 상태 |
|---|---|---|
| `toStr` | create_manual_modal.js (폴백) | 이미 있음 (`window.ManualShared.toStr`) |
| `setBtnLoading` | create_manual_modal.js (폴백) | 이미 있음 |
| `showErrorBox` | create_manual_modal.js (폴백) | 이미 있음 |
| `clearErrorBox` | create_manual_modal.js (폴백) | 이미 있음 |
| `safeReadJson` | create_manual_modal.js (폴백) | 이미 있음 |

`section_subnav.js` 내 `rebuildSubnavFromDOM()` 함수와 `manual_detail_subnav.js`의 `rebuildNow()` 함수는 각각 다른 방식으로 Subnav DOM을 재구성하는 유사 로직이 있다. 기능적으로 동일 목적이나 구현이 다르므로 중복 위반으로 분류하지 않는다(커스텀 이벤트를 통해 연결함).

---

### B-06. `AbortController` / 이벤트 리스너 정리

🟡 **개선 권장** — 공수: 중

`manual_detail_block/section_subnav.js`의 `beginSectionTitleEdit()` 함수에서 인라인으로 생성되는 버튼들에 이벤트 리스너를 등록한다:

```javascript
// section_subnav.js:200-205
btnOk.addEventListener("click", save);
btnCancel.addEventListener("click", cleanup);
input.addEventListener("keydown", (e) => { ... });
```

`cleanup()` 함수가 `wrap.remove()`를 호출하므로 DOM에서 제거되면 GC 대상이 되어 실질적인 메모리 누수는 없다. 단, cleanup이 호출되지 않는 예외 경로가 있다면 누수 위험이 있다.

`manual_detail_subnav.js`의 IntersectionObserver는 `rebuildObserver()`에서 `disconnect() → null` 처리를 하므로 정리가 된다:

```javascript
// manual_detail_subnav.js:86-91
if (io) {
  try { io.disconnect(); } catch (_) {}
  io = null;
}
```

SortableJS 인스턴스(`manual_detail_section_sort.js`)는 destroy하지 않으나, 페이지 전체 수명과 일치하므로 문제없다.

**실질적 위험**: `AbortController` 미사용으로 인한 메모리 누수 패턴은 발견되지 않았으나, SPA 환경이나 동적 리렌더링 환경이라면 주의 필요.

---

## 3. CSS 레이어 점검 결과

### C-01. `:root` 전역 변수 선언 (RULE-Q-02)

✅ **준수**

`manual.css`에 `:root { ... }` 블록이 없다. CSS 변수(`--manual-wide-width`, `--manual-wide-max`)가 `#manual-detail` 스코프에 선언되어 있다:

```css
/* manual.css:13-20 */
#manual-detail{
  --manual-wide-width: 72vw;
  --manual-wide-max: 1200px;
  width: var(--manual-wide-width);
  max-width: var(--manual-wide-max);
  ...
}
```

`.manual-subnav .subnav-inner`에서 `var(--manual-wide-width)`를 참조하는데, `subnav-inner`는 `#manual-detail` 하위 DOM에 있으므로 변수 상속이 정상 동작한다.

---

### C-02. 스코프 없는 전역 클래스 선언

🔴 **위반** — 전역 영향을 줄 수 있는 클래스/규칙 5건 발견

다음 CSS 규칙들이 manual 전용 스코프 선택자 없이 선언되어 있다:

```css
/* manual.css:26-29 */
.manual-badge-admin{
  background: var(--inka-blue) !important;
  ...
}

/* manual.css:34-38 */
.manual-badge-staff{
  background: #dc3545 !important;
  ...
}

/* manual.css:43-44 */
.sortable-ghost { opacity: 0.6; }
.manual-sort-ghost { opacity: 0.5; }
.manual-sort-chosen { cursor: grabbing !important; }

/* manual.css:47 */
a.manual-item.manual-editing { background: #fbfdff; }

/* manual.css:53-55 */
.manual-list-container{ max-width: 800px; }
.manual-list-title{ color:#003f7d; }
.manual-list-group{ border-radius:14px; overflow:hidden; }
...

/* manual.css:143-146 (CRITICAL) */
.navbar .dropdown-menu{
  z-index: 1040 !important;
}
```

**`.navbar .dropdown-menu` 규칙이 특히 위험하다.** 이 규칙은 manual 페이지 전용 스타일임에도 스코프 없이 선언되어, 다른 앱 페이지에서도 manual.css가 로드되는 경우 navbar dropdown z-index에 영향을 준다. manual.css는 `app_css` 블록에서만 로드되므로 현재는 manual 페이지에서만 적용되지만, 스코프 선택자(`#manual-detail .navbar .dropdown-menu` 또는 `.manual-subnav ~ .navbar .dropdown-menu`)로 제한하는 것이 안전하다.

`.sortable-ghost`도 SortableJS가 사용하는 일반 클래스명으로, 다른 앱에서 SortableJS를 사용하면서 manual.css가 로드된 경우 ghost 스타일이 오염될 수 있다.

**영향 범위 제한 요인**: `app_css` 블록을 통해 manual 페이지에서만 로드되므로 현재 실제 오염은 없으나, 미래 다른 앱에서 manual.css를 import하거나 base.css로 이동 시 위험.

---

### C-03. JS 의존 CSS 클래스 변경 위험 포인트

✅ **준수**

JS에서 참조하는 클래스명과 CSS 정의가 일치한다.

| CSS 클래스 | JS 참조 위치 | 일치 여부 |
|---|---|---|
| `.manual-section` | `index.js:238`, `section_subnav.js:29`, `sort_blocks.js:79` | ✅ |
| `.manual-block` | `index.js:239`, `sort_blocks.js:30` | ✅ |
| `.jsBlockDragHandle` | `sort_blocks.js:88` | ✅ (CSS `cursor: grab` 없음, 클래스는 일치) |
| `.jsSectionDragHandle` | `manual_detail_section_sort.js:139` | ✅ |
| `.manual-sort-ghost` | `manual_detail_section_sort.js:140` | ✅ |
| `.manual-sort-chosen` | `manual_detail_section_sort.js:141` | ✅ |
| `.jsSubnavLink` | `manual_detail_subnav.js:58` | ✅ |
| `.manualBlocks` | `sort_blocks.js:79` | ✅ |
| `[data-role="secTitleText"]` | `manual_detail_subnav.js:139`, `section_subnav.js:115` | ✅ (CSS 아님, DOM 계약) |

**주의**: `.jsBlockDragHandle`은 CSS에 정의되어 있지 않다. SortableJS의 handle 선택자로만 사용된다. `sort_blocks.js:88`에서 `handle: ".jsBlockDragHandle"`로 사용되고, `index.js:256`의 buildBlockElement에서 버튼에 `class="... jsBlockDragHandle"`로 붙인다. CSS `cursor:grab` 이 없어 드래그 커서가 보이지 않는다. `.jsSectionDragHandle`에는 `cursor: grab`이 있다.

---

## 4. 템플릿 레이어 점검 결과

### D-01. 파일/이미지 URL 직접 노출 여부

✅ **준수**

`manual_detail.html`에서 이미지 URL이 뷰 경유로 올바르게 처리된다:

```html
<!-- manual_detail.html:114 -->
data-image-url="{% if b.image %}{% url 'manual:manual_block_image' b.id %}{% endif %}"

<!-- manual_detail.html:119 -->
<img src="{% url 'manual:manual_block_image' b.id %}"
```

`b.image.url` (스토리지 직접 URL)을 노출하는 곳 없음. `manual_block_image` 뷰에서 `manual_accessible_or_denied()` 권한 체크 후 FileResponse로 제공한다.

첨부파일도 `attachment_to_dict()`에서 `reverse("manual:manual_attachment_download", args=[a.id])`를 통해 다운로드 뷰 URL만 반환하므로 스토리지 직접 URL 노출 없음.

---

### D-02. `sanitize_manual_html` 필터 미적용 여부

✅ **준수**

`manual_detail.html` 상단에 `{% load manual_sanitize %}`가 있으며, 블록 content 렌더링 시 필터가 적용된다:

```html
<!-- manual_detail.html:5 -->
{% load manual_sanitize %}

<!-- manual_detail.html:128 -->
<div class="manual-block-text manual-block-content">
  {{ b.content|sanitize_manual_html }}
</div>
```

`{{ b.content|safe }}` 직접 렌더링 사례 없음. `manual_list.html`에는 block.content를 렌더링하지 않으므로 필터 로드 불필요(정상).

---

### D-03. dataset 주입 일관성

🟡 **개선 권장** — 공수: 소

`manual_detail_boot.html`에서 주입하는 URL 키와 JS(`index.js`)에서 읽는 키를 대조:

| dataset 키 (boot.html) | JS 읽기 위치 (index.js) | 일치 여부 |
|---|---|---|
| `data-section-title-update-url` | `bootEl.dataset.sectionTitleUpdateUrl` | ✅ |
| `data-section-delete-url` | `bootEl.dataset.sectionDeleteUrl` | ✅ |
| `data-block-delete-url` | `bootEl.dataset.blockDeleteUrl` | ✅ |
| `data-block-reorder-url` | `bootEl.dataset.blockReorderUrl` | ✅ |
| `data-block-move-url` | `bootEl.dataset.blockMoveUrl` | ✅ |

`index.js`가 boot URL에서 `blockAdd`, `blockUpdate`, `attachUpload` URL을 읽지 않는다. 이 URL들은 `#manualBlockModal` 요소의 dataset에서 읽는다:

```javascript
// index.js:402-403 (btnSave click handler)
const addUrl = toStr(modalEl.dataset.addUrl);
const updateUrl = toStr(modalEl.dataset.updateUrl);

// quill.js:89
const uploadUrl = toStr(modalEl.dataset.attachUploadUrl);
```

`manualDetailBoot`에서 주입하지 않고 `manualBlockModal` 요소에서 직접 읽는 구조로, 이 분리는 허용되지만 URL 주입 위치가 두 곳으로 분산되어 있다. `manual_detail_superuser_assets.html`의 모달 정의에 해당 URL들이 있다:

```html
<!-- manual_detail_superuser_assets.html:52-55 -->
data-add-url="{% url 'manual:manual_block_add_ajax' %}"
data-update-url="{% url 'manual:manual_block_update_ajax' %}"
data-attach-upload-url="{% url 'manual:manual_block_attachment_upload_ajax' %}"
```

**개선 권장**: block CRUD URL을 `manualDetailBoot`로 통합하거나, 현재처럼 modal 요소에 유지하되 boot.html 주석에 "block CRUD URL은 #manualBlockModal에서 주입됨"을 명시. 현재 동작에는 문제 없음.

---

### D-04. `_partials/` include 구조

🟡 **개선 권장** — 공수: 소

**`manual_detail_superuser_assets.html`에 혼재된 역할**:

현재 파일이 담당하는 내용:
1. CSRF form (`#manualBlockCsrfForm`)
2. 이미지 뷰어 모달 (`#manualImageViewer`)
3. 블록 추가/편집 모달 (`#manualBlockModal`) ← URL도 여기 주입
4. Quill CSS/JS 로드
5. `csrf_window.js`, `_shared.js` 로드 (중복 로드 가능성)

그런데 `manual_detail.html` 본체에도 같은 JS를 로드한다:

```html
<!-- manual_detail.html:214-218 -->
<script src="{% static 'js/common/csrf_window.js' %}?v={% now 'U' %}"></script>
<script src="{% static 'js/manual/_shared.js' %}"></script>
<script src="{% static 'js/manual/create_manual_modal.js' %}..."></script>
<script type="module" src="{% static 'js/manual/manual_detail_block/index.js' %}..."></script>
```

그리고 `manual_detail_superuser_assets.html`에도:

```html
<!-- manual_detail_superuser_assets.html:145-146 -->
<script src="{% static 'js/common/csrf_window.js' %}?v={% now 'U' %}"></script>
<script src="{% static 'js/manual/_shared.js' %}"></script>
```

**`csrf_window.js`와 `_shared.js`가 2번 로드된다.** `_shared.js`는 `if (window.ManualShared) return;` 가드가 있어 중복 초기화는 방어하지만, 불필요한 HTTP 요청이 발생한다.

**`manual_detail_boot.html`의 역할 경계**: 오직 URL 주입 `data-*` 컨테이너만 담당하며 명확하다.

**개선 권장**: `manual_detail_superuser_assets.html`에서 `csrf_window.js`, `_shared.js` 로드를 제거하고 `manual_detail.html` 본체의 `{% if user.grade == "superuser" %}` 블록에만 두어 단일 로드를 보장.

---

## 5. 공통 모듈화 가능 포인트

### Python 모듈화 후보

#### P-1. `cleanup_missing_manual_images.py` 통합 (우선순위: 높음)

| 항목 | 내용 |
|---|---|
| 현재 중복 위치 | `manual/management/commands/cleanup_missing_manual_images.py` (전체) |
| 이동 대상 | 파일 삭제 또는 `cleanup_manual_files.py --apply` 호출 래퍼로 교체 |
| 영향받는 파일 | 없음 (독립 명령) |
| 기능 변화 0 보장 | `cleanup_missing_manual_images.py`는 기존 명령어 이름으로 외부 cron/문서에서 참조될 수 있으므로 명령어 자체는 유지하되, 내부 구현을 `cleanup_manual_files.py`의 `_cleanup_missing_block_images()`를 직접 호출하도록 리팩토링 |

#### P-2. `views/block.py`의 `sanitize_quill_html()` 제거 (우선순위: 중)

| 항목 | 내용 |
|---|---|
| 현재 중복 위치 | `views/block.py:29`, `views/block.py:74` |
| 이동 대상 | `models.py`의 `ManualBlock.save()`가 이미 SSOT |
| 영향받는 파일 | `views/block.py` |
| 기능 변화 0 보장 | `sanitize_quill_html()`은 idempotent이므로 view에서 제거해도 동일 결과. view에서 content 변수를 unsanitized raw HTML로 받아 create/save에 전달하면 model.save()에서 처리됨 |

---

### JavaScript 모듈화 후보

#### J-1. `create_manual_modal.js`를 `ManualShared.postJson()` 경유로 전환 (우선순위: 높음)

| 항목 | 내용 |
|---|---|
| 현재 중복 위치 | `create_manual_modal.js:83-111` (fetch 직접 구현 + 폴백 함수 블록) |
| 이동 대상 | `_shared.js`의 `ManualShared.postJson()` 사용 |
| `ManualShared` API 변경 필요 여부 | 없음 (이미 `postJson(url, body, csrfToken)` 시그니처 존재) |
| BFCache 영향 | 없음 |
| CSRF 토큰 처리 | `window.csrfToken` 직접 참조 → `getCSRFTokenFromForm(null)` 또는 `window.csrfToken` 유지 (동일 결과) |

폴백 구현 블록(lines 12-43) 제거 후 `const S = window.ManualShared; if (!S) return;`으로 실패 시 조기 종료 처리.

#### J-2. `manual_detail_subnav.js` BFCache 가드 추가 (우선순위: 중)

| 항목 | 내용 |
|---|---|
| 현재 중복 위치 | `manual_detail_subnav.js:11-14` (IIFE 진입부) |
| `_shared.js` 이동 여부 | 해당 없음 (가드 추가만 필요) |
| API 시그니처 변경 | 없음 |
| BFCache 영향 | 개선됨 (중복 Observer 방지) |

```javascript
// 추가할 코드 (index.js 패턴 동일)
if (subnavEl.dataset.inited === "1") return;
subnavEl.dataset.inited = "1";
```

#### J-3. `section_subnav.js`와 `manual_detail_subnav.js`의 Subnav 재구성 로직 정리 (우선순위: 낮음)

| 항목 | 내용 |
|---|---|
| 현재 중복 위치 | `section_subnav.js:22-55`의 `rebuildSubnavFromDOM()`, `manual_detail_subnav.js:146-168`의 `rebuildNow()` |
| `_shared.js` 이동 여부 | 불필요 (두 함수는 의도적으로 다른 방식 사용) |
| 개선 방향 | 커스텀 이벤트 경유(`manual:subnavRebuilt`)로 이미 연결되어 있으므로 `section_subnav.js`에서 `rebuildSubnavFromDOM()` 대신 `window.ManualDetailSubnav.rebuild()` 직접 호출 |
| BFCache 영향 | 없음 |

---

### CSS 정리 후보

#### CSS-1. `.navbar .dropdown-menu` 스코프 추가 (우선순위: 높음)

| 항목 | 내용 |
|---|---|
| 현재 위치 | `manual.css:143-146` |
| 위반 패턴 | 전역 navbar 규칙 |
| 수정 방법 | `#manual-detail ~ .navbar .dropdown-menu` 또는 별도 주석으로 "manual 페이지 한정" 표시 |
| JS/템플릿 변경 필요 | 없음 |

**주의**: CSS 선택자 변경 시 navbar가 `#manual-detail`의 sibling이 아닌 경우(base.html 구조 의존) 적용되지 않을 수 있다. 가장 안전한 방법은 `.manual-page .navbar .dropdown-menu`처럼 body class 기반 스코핑이나, 현재 템플릿에 body class가 없다면 `manual_detail.html`의 `content_wrapper` 내 스타일 블록으로 이동.

#### CSS-2. `.sortable-ghost` 전역 클래스 스코핑 (우선순위: 낮음)

| 항목 | 내용 |
|---|---|
| 현재 위치 | `manual.css:43` |
| 위반 패턴 | SortableJS 공통 클래스명 전역 선언 |
| 수정 방법 | `#manualListGroup .sortable-ghost`, `#manualSections .sortable-ghost` 로 스코핑 |
| JS/템플릿 변경 필요 | 없음 (SortableJS의 ghostClass 설정은 변경 불필요) |

---

## 6. 절대 수정 금지 목록 현황 확인

| 항목 | 상태 |
|---|---|
| `manual/utils/permissions.py`: `filter_manuals_for_user()` | ✅ 이상 없음 — superuser: 전체, head: is_published=True 한정, leader/basic: admin_only=False 추가 필터 적용. 누락 없음 |
| `manual/utils/permissions.py`: `manual_accessible_or_denied()` | ✅ 이상 없음 — admin_only AND not head/superuser → deny, not is_published AND not superuser → deny. 비공개 매뉴얼 차단 유지 |
| `manual/utils/sanitize.py`: `sanitize_quill_html()` allowlist | ✅ 이상 없음 — `ALLOWED_TAGS`에 `script`, `iframe`, `form` 등 위험 태그 없음. `ALLOWED_ATTRIBUTES`에 `on*` 이벤트 없음. `javascript:` 프로토콜 정규식으로 제거 |
| `manual/utils/serializers.py`: `attachment_to_dict()` 반환 키 | ✅ 이상 없음 — `id`, `name`, `url`, `download_url`, `size` 5개 키 모두 반환. JS(`quill.js:73-74`)에서 `att.url`, `att.name`, `att.size` 사용 |
| `static/js/manual/_shared.js`: `ManualShared` 공개 API | ✅ 이상 없음 — `log`, `ready`, `toStr`, `isDigits`, `getCSRFTokenFromForm`, `setBtnLoading`, `showErrorBox`, `clearErrorBox`, `safeReadJson`, `postJson`, `postForm`, `formatBytes` 12개 함수 |
| `.manual-section[data-section-id]` DOM 계약 | ✅ 이상 없음 — `manual_detail.html`의 section div에 `data-section-id="{{ sec.id }}"` 주입. JS에서 `el.dataset.sectionId`로 읽음 |
| `.manual-block[data-block-id]` DOM 계약 | ✅ 이상 없음 — `manual_detail.html`의 block div에 `data-block-id="{{ b.id }}"` 주입. JS에서 `el.dataset.blockId`로 읽음 |
| `ManualBlock.save()` 내 `sanitize_quill_html()` 호출 | ✅ 이상 없음 — `models.py:146-149`에 유지됨 |

---

## 7. 회귀 위험 체크리스트 현황

- [x] `filter_manuals_for_user()` — head/leader/basic 필터 누락 없는지  
  ✅ 이상 없음. `grade != "superuser"` → `is_published=True` 필터, `grade not in ("superuser", "head")` → `admin_only=False` 필터. 정책 완전 구현됨

- [x] `manual_accessible_or_denied()` — 비공개 매뉴얼 접근 차단 유지  
  ✅ 이상 없음. `is_published=False`이면 superuser만 허용. 나머지 grade는 `no_permission_popup.html` 반환

- [x] `sanitize_quill_html()` allowlist — `<script>`, `on*` 이벤트 속성 없는지  
  ✅ 이상 없음. `ALLOWED_TAGS` 세트에 `script`, `iframe`, `object`, `embed` 없음. `ALLOWED_ATTRIBUTES` 딕셔너리에 이벤트 핸들러(`on*`) 없음. `_EVENT_HANDLER_RE` 정규식으로 추가 방어

- [x] `attachment_to_dict()` 반환 키 — JS 기대 키 일치 여부  
  ✅ 이상 없음. `quill.js`에서 `att.url`(링크 삽입), `att.name`, `att.size` 사용. 모두 `attachment_to_dict()`에서 반환됨. `url`과 `download_url`이 동일 값이나 JS는 `url`만 사용

- [x] `ensure_default_section()` — 섹션 삭제 후 호출 유지  
  ✅ 이상 없음. `views/section.py:119-122`에서 `manual.sections.count() == 0` 확인 후 `ensure_default_section(manual)` 호출. new_section을 JS에 반환하여 DOM에 추가

- [x] `manual_block_move_ajax` — `transaction.atomic()` 블록 유지  
  ✅ 이상 없음. `views/block.py:254-261`에서 `with transaction.atomic():` 내에서 section 업데이트와 양쪽 sort_order 업데이트를 수행

- [x] 이미지/첨부 URL 직접 노출 금지  
  ✅ 이상 없음. `manual_detail.html`에서 `{% url 'manual:manual_block_image' b.id %}` 경유. `attachment_to_dict()`에서 `reverse("manual:manual_attachment_download", ...)` 경유

- [x] Quill HTML 렌더링 필터 적용  
  ✅ 이상 없음. `manual_detail.html`에서 `{{ b.content|sanitize_manual_html }}` 적용. `{% load manual_sanitize %}` 상단에 있음

---

## 8. 2단계 패치 작업 순서 권장안

작업 위험도·공수를 기준으로 정렬. 기능 변화 0 원칙에 따라 1단계는 방어 코드 추가/중복 제거이며 2단계는 구조 정리다.

| 순서 | 작업 | 카테고리 | 위험도 | 공수 | 근거 |
|---|---|---|---|---|---|
| 1 | `create_manual_modal.js` 폴백 구현 블록 제거 + `ManualShared.postJson()` 경유 전환 | B-01/B-02/B-05 | 낮음 | 소 | RULE-Q-01 위반 해소. `_shared.js` 이미 로드된 상태이므로 위험 없음 |
| 2 | `manual_detail_subnav.js` BFCache 가드 추가 | B-03 | 낮음 | 소 | IIFE 진입부에 2줄 추가. 기능 변화 없음 |
| 3 | `manual_detail_superuser_assets.html`의 `csrf_window.js`, `_shared.js` 중복 로드 제거 | D-04 | 낮음 | 소 | `manual_detail.html` 본체에 이미 로드됨. `_shared.js`에 중복 방지 가드 있음 |
| 4 | `views/pages.py`의 `manual_create()`, `manual_edit()`에 `log_action()` 추가 | A-04 | 낮음 | 소 | 감사 로그 누락 보완. ACTION 상수 이미 정의됨 |
| 5 | `manual.css`의 `.navbar .dropdown-menu` 스코핑 추가 | C-02 | 낮음 | 소 | CSS 선택자 변경만. 기능 동일 |
| 6 | `views/block.py`의 `sanitize_quill_html()` 호출 제거 | A-05 | 낮음 | 소 | `ManualBlock.save()`가 SSOT. 결과 동일 |
| 7 | `cleanup_missing_manual_images.py` 내부 구현 → `cleanup_manual_files.py` 위임 리팩토링 | A-06 | 중간 | 중 | 명령어 이름 유지 필수. 외부 참조 여부 확인 후 진행 |
| 8 | `section_subnav.js`의 `rebuildSubnavFromDOM()` → `window.ManualDetailSubnav.rebuild()` 호출 전환 | J-3 | 중간 | 중 | 커스텀 이벤트 경유 구조 이미 있으나 직접 호출이 더 명확. 순환 참조 없음 확인 필요 |
| 9 | `manual.css`의 `.sortable-ghost` 클래스 스코핑 | C-02 | 낮음 | 소 | 다른 앱 SortableJS 도입 시 방어. 현재는 실제 오염 없음 |

---

*이 문서는 기능 수정 없이 점검 결과만을 기록한 것으로, 실제 패치는 별도 작업 회차에서 수행한다.*
