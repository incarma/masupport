# partner 앱 코드 품질 점검 & 모듈화 가이드

> 작성일: 2026-05-14  
> 범위: `partner/` 앱 전체 (Python 뷰·모델·서비스, JS, CSS, 템플릿)  
> 원칙: **기능 변화 0** — 이 문서는 점검 보고서이며 코드를 수정하지 않는다.

---

## 요약 대시보드

| 구분 | 🔴 위반 | 🟡 개선 권장 | ✅ 준수 | ➖ 해당 없음 |
|---|---|---|---|---|
| A. Python 레이어 | 2 | 6 | 12 | 0 |
| B. JavaScript 레이어 | 0 | 5 | 14 | 1 |
| C. CSS 레이어 | 0 | 2 | 4 | 0 |
| D. 템플릿 레이어 | 0 | 1 | 8 | 1 |
| **합계** | **2** | **14** | **38** | **2** |

---

## A. Python 레이어

### A-01. 권한 데코레이터 (`@login_required` / `@grade_required`)

| 뷰 파일 | 상태 | 비고 |
|---|---|---|
| `rate.py` | ✅ | 모든 뷰에 적용 |
| `structure.py` | ✅ | 모든 뷰에 적용 |
| `efficiency.py` | ✅ | 모든 뷰에 적용 |
| `esign.py` | ✅ | 모든 뷰에 적용 |
| `grades.py` | ✅ | 모든 뷰에 적용 |
| `subadmin.py` | ✅ | 모든 뷰에 적용 |
| `process_date.py` | ✅ | 모든 뷰에 적용 |
| `ratetable.py` | ✅ | 모든 뷰에 적용 |
| `tablesettings.py` | ✅ | 모든 뷰에 적용 |

**판정: ✅ 전 파일 준수**

---

### A-02. 보안 SSOT — `resolve_branch_for_query` / `resolve_branch_for_write` 사용

이 두 함수는 `partner/views/utils.py`에 정의된 데이터 유출 방지 SSOT다. 절대 수정 금지.

```python
# utils.py SSOT
def resolve_branch_for_query(user, branch_param):
    if getattr(user, "grade", "") == "superuser":
        return branch_param
    return (getattr(user, "branch", "") or "").strip()

def resolve_branch_for_write(user, branch_payload):
    if getattr(user, "grade", "") == "superuser":
        return branch_payload or "-"
    return (getattr(user, "branch", "") or branch_payload or "-").strip()
```

| 뷰 파일 | query 사용 | write 사용 | 상태 |
|---|---|---|---|
| `rate.py` | `rate_fetch` ✅ | `rate_save` ✅ | ✅ |
| `structure.py` | `ajax_fetch` ✅ | `ajax_save` ✅ | ✅ |
| `efficiency.py` | `efficiency_fetch` ✅ | `efficiency_save` ✅ | ✅ |
| `esign.py` | `esign_fetch` ✅ | `esign_save` ✅ | ✅ |
| `grades.py` | N/A (DataTables) | N/A | ➖ |
| `process_date.py` | N/A | N/A (공통 헬퍼) | ➖ |

**판정: ✅ 보안 SSOT 전 적용 준수**

---

### A-03. JSON 응답 SSOT — `json_ok` / `json_err` / `parse_json_body`

`partner/views/responses.py`가 SSOT. 응답 형식 `{"status": "success"|"error", ...}`.

| 뷰 파일 | 상태 | 비고 |
|---|---|---|
| `rate.py` | ✅ | `json_ok`, `json_err`, `parse_json_body` 모두 정상 사용 |
| `structure.py` | ✅ | 동일 |
| `efficiency.py` | ✅ | 동일 |
| `esign.py` | 🟡 | `parse_json_body` 대신 자체 `_parse_json()` 사용 (중복 구현) |
| `grades.py` — `ajax_users_data` | 🟡 | `JsonResponse({...})` 직접 사용, DataTables 형식이어서 `json_ok`와 구조 다름 |
| `grades.py` — `ajax_update_level` | 🟡 | `JsonResponse({"success": True})` 직접 사용 — `{"status": "success"}` 아님 |
| `subadmin.py` | 🟡 | `JsonResponse({"ok": True/False, ...})` 직접 사용 — SSOT 불일치 |
| `process_date.py` | ✅ | `json_ok`, `json_err` 정상 사용 |
| `ratetable.py` | ✅ | `json_ok`, `json_err` 정상 사용 |
| `tablesettings.py` | ✅ | `json_ok`, `json_err` 정상 사용 |

**🟡 개선 권장 (3건)**: `esign.py`, `grades.py`(2개 뷰), `subadmin.py`에서 JSON SSOT 미준수. 기능에 영향은 없으나 응답 형식 불일치로 프론트 분기 코드가 복잡해짐.

---

### A-04. 감사 로그 (`log_action`)

**🔴 위반 1: `structure.py` — `ajax_save` / `ajax_delete` 감사 로그 없음**

```python
# structure.py (현황)
# ajax_save: PartnerChangeLog.objects.create(...) 만 있음
# ajax_delete: PartnerChangeLog.objects.create(...) 만 있음

# PartnerChangeLog는 partner 앱 내부 전용 로그이며,
# audit.services.log_action 호출이 없음 → 감사 시스템에 기록 안 됨
```

`audit/constants.py`에 `PARTNER_STRUCTURE_SAVE = "partner.structure.save"` 및 `PARTNER_STRUCTURE_DELETE = "partner.structure.delete"` 상수가 이미 정의되어 있으나 `structure.py`에서 전혀 임포트하지 않는다.

**🔴 위반 2: `grades.py` — `upload_grades_excel` 감사 로그 없음**

```python
# grades.py (현황)
def upload_grades_excel(request):
    ...
    messages.success(request, f"업로드 완료: 신규 {created}건, 수정 {updated}건 반영")
    # log_action() 호출 없음
```

`audit/constants.py`에 `PARTNER_GRADES_UPLOAD = "partner.grades.upload"` 상수가 이미 정의되어 있다.

| 뷰 | ACTION 상수 | log_action 호출 | 상태 |
|---|---|---|---|
| `rate.py::rate_save` | `PARTNER_RATE_SAVE` | ✅ (성공+실패 양쪽) | ✅ |
| `rate.py::rate_delete` | `PARTNER_RATE_DELETE` | ✅ (삭제 직전) | ✅ |
| `structure.py::ajax_save` | `PARTNER_STRUCTURE_SAVE` | 없음 | **🔴** |
| `structure.py::ajax_delete` | `PARTNER_STRUCTURE_DELETE` | 없음 | **🔴** |
| `efficiency.py::efficiency_save` | `PARTNER_EFFICIENCY_SAVE` | ✅ (`_audit_safe` 래퍼) | ✅ |
| `efficiency.py::efficiency_delete_row` | `PARTNER_EFFICIENCY_DELETE` | ✅ | ✅ |
| `efficiency.py::confirm_upload` | `PARTNER_EFFICIENCY_CONFIRM_UPLOAD` | ✅ | ✅ |
| `efficiency.py::confirm_download` | `PARTNER_EFFICIENCY_CONFIRM_DOWNLOAD` | ✅ | ✅ |
| `grades.py::upload_grades_excel` | `PARTNER_GRADES_UPLOAD` | 없음 | **🔴** |
| `subadmin.py::ajax_add_sub_admin` | `PARTNER_LEADER_ADD` | ✅ (기존 NEVER_DO 수정됨) | ✅ |
| `subadmin.py::ajax_delete_subadmin` | `PARTNER_LEADER_DELETE` | ✅ (기존 NEVER_DO 수정됨) | ✅ |
| `ratetable.py::ajax_rate_userlist_upload` | `PARTNER_RATE_UPLOAD` | ✅ | ✅ |
| `tablesettings.py::ajax_table_save` | `PARTNER_TABLE_SAVE` | ✅ | ✅ |
| `esign.py::esign_create` | `PARTNER_ESIGN_CREATE` | ✅ | ✅ |
| `esign.py::esign_sign` | `PARTNER_ESIGN_SIGN` | ✅ | ✅ |
| `esign.py::esign_delete_group` | `PARTNER_ESIGN_DELETE` | ✅ | ✅ |

**확인: NEVER_DO 이슈 (S-B-05) 해소 상태**  
`subadmin.py`에서 `log_action(request, ACTION.PARTNER_LEADER_ADD/DELETE)` 호출이 이미 포함되어 있다. 기존 NEVER_DO 이슈는 수정 완료.

---

### A-05. `action` 상수 사전 정의 확인

| ACTION 상수 | `audit/constants.py` 정의 | 실제 사용 뷰 | 상태 |
|---|---|---|---|
| `PARTNER_RATE_SAVE` | ✅ | `rate.py` | ✅ |
| `PARTNER_RATE_DELETE` | ✅ | `rate.py` | ✅ |
| `PARTNER_STRUCTURE_SAVE` | ✅ | `structure.py` (미사용) | 🟡 정의됨, 미사용 |
| `PARTNER_STRUCTURE_DELETE` | ✅ | `structure.py` (미사용) | 🟡 정의됨, 미사용 |
| `PARTNER_EFFICIENCY_SAVE` | ✅ | `efficiency.py` | ✅ |
| `PARTNER_EFFICIENCY_DELETE` | ✅ | `efficiency.py` | ✅ |
| `PARTNER_EFFICIENCY_CONFIRM_UPLOAD` | ✅ | `efficiency.py` | ✅ |
| `PARTNER_EFFICIENCY_CONFIRM_DOWNLOAD` | ✅ | `efficiency.py` | ✅ |
| `PARTNER_TABLE_SAVE` | ✅ | `tablesettings.py` | ✅ |
| `PARTNER_RATE_UPLOAD` | ✅ | `ratetable.py` | ✅ |
| `PARTNER_LEADER_ADD` | ✅ | `subadmin.py` | ✅ |
| `PARTNER_LEADER_DELETE` | ✅ | `subadmin.py` | ✅ |
| `PARTNER_GRADES_UPLOAD` | ✅ | `grades.py` (미사용) | 🟡 정의됨, 미사용 |
| `PARTNER_ESIGN_CREATE` | ✅ | `esign.py` | ✅ |
| `PARTNER_ESIGN_SIGN` | ✅ | `esign.py` | ✅ |
| `PARTNER_ESIGN_DELETE` | ✅ | `esign.py` | ✅ |
| `PARTNER_ESIGN_PDF_DL` | ✅ | `esign.py` | ✅ |
| `PARTNER_ESIGN_PROCESS_DATE_UPDATE` | ✅ | `esign.py` | ✅ |

**판정: ✅ 모든 사용 상수는 사전 정의됨.** 단, `PARTNER_STRUCTURE_SAVE/DELETE`와 `PARTNER_GRADES_UPLOAD`는 정의는 되어 있으나 해당 뷰에서 호출되지 않음 (A-04 위반과 연결).

---

### A-06. 로깅 (`logger.exception` vs `traceback.print_exc`)

| 파일 | 현황 | 상태 |
|---|---|---|
| `rate.py` | `logger = logging.getLogger(__name__)`, `logger.exception(...)` 사용 | ✅ |
| `structure.py` | `import traceback`, `traceback.print_exc()` 사용 (3곳) | 🟡 |
| `efficiency.py` | `logger.exception(...)` 사용 | ✅ |
| `esign.py` | `logger.exception(...)` 사용 | ✅ |
| `grades.py::upload_grades_excel` | `traceback.print_exc()` 사용 | 🟡 |
| `grades.py::ajax_users_data` | `traceback.print_exc()` 사용 | 🟡 |
| `ratetable.py` | `logger.exception(...)` 사용 (일부 `traceback.print_exc()` 혼재) | 🟡 |

**🟡 개선 권장**: `traceback.print_exc()`는 stdout에 출력되므로 운영 환경 로그 집계 시스템(`logging`)에 캡처되지 않는다. `logger.exception(...)` 또는 `logger.error(traceback.format_exc())`로 교체 권장.

---

### A-07. 중복 함수 / DRY 위반

**`_generate_confirm_group_id` 중복:**

`efficiency.py`와 `esign.py` 두 파일에 각각 동일한 이름의 함수가 있으나 구현이 미묘하게 다르다.

```python
# efficiency.py (line 85~95)
def _generate_confirm_group_id(*, uploader_id: str) -> str:
    now = timezone.localtime(timezone.now())
    prefix = now.strftime("%Y%m%d%H%M")
    base = f"{prefix}_{uploader_id}_"
    same_minute_qs = EfficiencyConfirmGroup.objects.select_for_update().filter(...)
    cnt = same_minute_qs.count()
    seq = min(cnt + 1, 99)
    return f"{base}{seq:02d}"

# esign.py — 유사하나 별도 구현 (세부 차이 있음)
```

또한 `esign.py`는 `parse_json_body` (responses.py SSOT) 대신 자체 `_parse_json()` 함수를 사용한다.

**🟡 개선 권장**: `_generate_confirm_group_id`를 `utils.py`로 이동하여 단일 SSOT로 관리. `esign.py`의 `_parse_json()`을 `parse_json_body`로 교체.

---

### A-08. 모델 / DB 안전성

| 항목 | 위치 | 상태 |
|---|---|---|
| `SubAdminTemp.db_table = "partner_subadmin_temp"` | `partner/models.py` | ✅ (고정됨, 변경 금지) |
| `EfficiencyChange.confirm_group on_delete=PROTECT` | `partner/models.py` | ✅ (cascade 차단) |
| `EfficiencyConfirmAttachment.group on_delete=CASCADE` | `partner/models.py` | ✅ (그룹 삭제 시 첨부도 삭제, 의도적) |
| `StructureDeadline.unique_together = ("branch", "month")` | `partner/models.py` | ✅ |
| `tablesettings.py select_for_update` | line 77 | ✅ 동시성 제어 적용 |
| `esign_service.py process_sign select_for_update` | `esign_service.py` | ✅ 중복 서명 방지 |
| `sync_subadmin_temp.py` 커맨드 | `management/commands/` | ✅ (단, `update_or_create` 내 `team_a/b/c` 필드 미보존 — 운영 주의) |

**🟡 개선 권장**: `sync_subadmin_temp.py`의 `update_or_create`는 `defaults`에 `team_a/b/c/position`이 없어 기존값을 보존하지만, `name/part/branch/grade` 덮어쓰기가 `grades.py` 정책(팀/직급 보존)과 다소 철학 충돌 가능. 주석으로 의도를 명시 권장.

---

## B. JavaScript 레이어

### B-01. CSRF 토큰 획득 SSOT (RULE-Q-01)

RULE-Q-01: CSRF 토큰은 `static/js/common/manage/csrf.js`의 `getCSRFToken()`을 통해서만 획득. 파일 내 재구현 금지.

| 파일 | CSRF 획득 방식 | 상태 |
|---|---|---|
| `manage_efficiency/utils.js` | `import { getCSRFToken } from "../../common/manage/csrf.js"` | ✅ |
| `manage_efficiency/delete.js` | `import { ..., getCSRFToken } from "./utils.js"` (utils.js 경유) | ✅ |
| `manage_efficiency/save.js` | `import { ..., getCSRFToken } from "./utils.js"` | ✅ |
| `manage_rate/utils.js` | `import { getCSRFToken } from "../../common/manage/csrf.js"` | ✅ |
| `manage_rate/fetch.js` | `import { getCSRFToken } from "../../common/manage/csrf.js"` | ✅ |
| `manage_rate/save.js` | `import { getCSRFToken } from "../../common/manage/csrf.js"` | ✅ |
| `manage_rate/delete.js` | `import { getCSRFToken } from "../../common/manage/csrf.js"` | ✅ |
| `manage_structure/utils.js` | `import { getCSRFToken } from "../../common/manage/csrf.js"` | ✅ |
| `manage_structure/fetch.js` | `import { ..., getCSRFToken, ... } from "./utils.js"` | ✅ |
| `manage_structure/save.js` | `import { ..., getCSRFToken, ... } from "./utils.js"` | ✅ |
| `manage_grades/index.js` | `window.csrfToken` 직접 참조 (line 191, `buildPostHeaders()`) | 🟡 |
| `esign_confirm/fetch.js` | `window.csrfToken` 직접 참조 (line 270) | 🟡 |
| `esign_confirm/save.js` | `window.csrfToken` 직접 참조 (line 308) | 🟡 |
| `esign_confirm/sign.js` | `window.csrfToken` 직접 참조 (line 125, 200) | 🟡 |

**🟡 개선 권장 (4파일)**: `manage_grades/index.js`, `esign_confirm/fetch.js`, `esign_confirm/save.js`, `esign_confirm/sign.js`에서 `window.csrfToken` 직접 참조가 RULE-Q-01 위반이다. `csrf_window.js`가 `window.csrfToken`을 주입하므로 현재 동작은 하지만, 공통 유틸 미경유라는 규칙 위반이다.

---

### B-02. HTTP 응답 처리 SSOT (`readJsonOrThrow` / `isSuccessJson`)

SSOT: `static/js/common/manage/http.js`

| 파일 | 준수 | 상태 |
|---|---|---|
| `manage_efficiency/delete.js` | `readJsonOrThrow`, `isSuccessJson` import | ✅ |
| `manage_efficiency/modal_search.js` | `readJsonOrThrow`, `isSuccessJson` import | ✅ |
| `manage_efficiency/save.js` | `readJsonOrThrow`, `isSuccessJson` import | ✅ |
| `manage_rate/fetch.js` | `readJsonOrThrow`, `isSuccessJson` import | ✅ |
| `manage_rate/save.js` | `readJsonOrThrow`, `isSuccessJson` import | ✅ |
| `manage_rate/delete.js` | `readJsonOrThrow`, `isSuccessJson` import | ✅ |
| `manage_structure/fetch.js` | `readJsonOrThrow`, `isSuccessJson` import | ✅ |
| `esign_confirm/fetch.js` | `res.json()` 직접 사용 (일부) | 🟡 |
| `esign_confirm/save.js` | `res.json()` 직접 사용 | 🟡 |
| `esign_confirm/sign.js` | `res.json()` 직접 사용 (일부) | 🟡 |

**🟡 개선 권장**: `esign_confirm/` 모듈 3개가 `res.json()` 직접 호출로 HTTP 오류 처리 SSOT 미준수. 응답 파싱 에러 핸들링 일관성 저하.

---

### B-03. BFCache 가드 (중복 바인딩 방지)

| 파일 | 가드 방식 | 상태 |
|---|---|---|
| `manage_efficiency/index.js` | `root.dataset.inited === "1"` | ✅ |
| `manage_rate/index.js` | `els.root.dataset[INIT_DATAKEY] === "1"` | ✅ |
| `manage_structure/index.js` | `window.__structureAutoLoaded` flag | 🟡 (dataset 아닌 window 변수) |
| `manage_grades/index.js` | `pageshow` 이벤트 핸들러 + BFCache 감지 | ✅ (pageshow 패턴) |
| `esign_confirm/index.js` | `root[GUARD_KEY] = true` (객체 프로퍼티) | 🟡 (dataset 아닌 객체 속성) |

**🟡 개선 권장**: `manage_structure`와 `esign_confirm`의 가드 방식이 `dataset.inited` 표준과 다름. 기능에는 문제없으나 코드베이스 일관성 저하.

---

### B-04. AJAX URL 하드코딩 금지 (dataset 경유)

| 파일 | 상태 | 비고 |
|---|---|---|
| `manage_efficiency/` 전체 | ✅ | `root.dataset.*` 경유 |
| `manage_rate/` 전체 | ✅ | `root.dataset.*` 경유 |
| `manage_structure/` 전체 | ✅ | `root.dataset.*` / `ManageStructureBoot` 경유 |
| `manage_grades/index.js` | ✅ | `root.dataset.*` 경유 |
| `esign_confirm/` 전체 | ✅ | `root.dataset.*` 경유 |
| `manage_efficiency/modal_search.js` | ✅ (fallback) | `els.root?.dataset?.searchUserUrl \|\| "/board/search-user/"` — fallback 하드코딩은 개발 편의상 허용 수준 |

**판정: ✅ 전체 준수**

---

### B-05. 이벤트 위임 및 중복 바인딩 방지

| 파일 | 중복 방지 | 이벤트 위임 | 상태 |
|---|---|---|---|
| `manage_efficiency/delete.js` | `container.dataset.effDeleteInited === "1"` | ✅ 컨테이너 기반 위임 | ✅ |
| `manage_efficiency/input_rows.js` | `W.__efficiencyInputRowsBound`, `W.__efficiencyAmountCommaBound` 등 | ✅ | ✅ |
| `manage_rate/delete.js` | `els.root.dataset[BOUND_KEY] === "1"` | ✅ | ✅ |
| `manage_rate/fetch.js` | `delegationBound` 모듈 변수 | ✅ | ✅ |
| `manage_structure/fetch.js` | `delegationBound` 모듈 변수 | ✅ | ✅ |
| `manage_grades/index.js` | 초기화 여부 내부 상태 | 일부 `document` 전역 | 🟡 |
| `esign_confirm/index.js` | `root[GUARD_KEY]` | ✅ | ✅ |

**판정: 대부분 준수. manage_grades 일부 개선 여지.**

---

### B-06. 숫자 포맷 규칙 (`toLocaleString("ko-KR")` / 콤마 등)

| 파일 | 포맷 방식 | 상태 |
|---|---|---|
| `manage_efficiency/input_rows.js` | 자체 `formatWithCommaFromDigits` (콤마 직접 구현) | ✅ (amount 입력 전용, 특수 요건으로 허용) |
| `manage_rate/fetch.js` | 금액 포맷 불필요 (요율 테이블) | ➖ |
| `manage_efficiency/` 전반 | `Number.toLocaleString("ko-KR")` 사용 | ✅ |

**판정: ✅ 준수**

---

### B-07. ESM vs IIFE 구조

| 모듈 | 타입 | BFCache | 상태 |
|---|---|---|---|
| `manage_efficiency/index.js` | ESM (`type="module"`) | ✅ dataset guard | ✅ |
| `manage_rate/index.js` | ESM (`type="module"`) | ✅ dataset guard | ✅ |
| `manage_structure/index.js` | ESM (`type="module"`) | 🟡 window 변수 | 🟡 |
| `manage_grades/index.js` | IIFE | ✅ pageshow | ✅ |
| `esign_confirm/index.js` | IIFE | 🟡 객체 프로퍼티 | 🟡 |

**판정: ✅ 구조 선택 자체는 적합. 가드 방식 불일치는 B-03에서 이미 기록.**

---

### B-08. `dom_refs.js` 패턴 일관성

| 파일 | 패턴 | 상태 |
|---|---|---|
| `manage_efficiency/dom_refs.js` | 정적 할당 (import 시 평가) | 🟡 BFCache 시 stale 위험 |
| `manage_rate/dom_refs.js` | `get` 접근자 (lazy) | ✅ |
| `manage_structure/dom_refs.js` | `get` 접근자 + alias | ✅ |
| `esign_confirm/dom_refs.js` | `window.EsignDom` IIFE + 함수 호출 (lazy) | ✅ |

**🟡 개선 권장**: `manage_efficiency/dom_refs.js`만 정적 할당 패턴을 사용하여 BFCache 복원 후 DOM 참조가 stale해질 수 있다. `get` 접근자 패턴으로 교체 권장.

---

## C. CSS 레이어

### C-01. CSS 스코프 규칙 (`#<app>-root` 하위 한정)

```css
/* partner.css 전체 스코프 확인 */
#manage-structure { ... }      /* ✅ */
#manage-rate { ... }           /* ✅ */
#manage-efficiency { ... }     /* ✅ */
#esign-confirm { ... }         /* ✅ */
#manage-grades { ... }         /* ✅ */
#manage-table { ... }          /* ✅ */
```

전역 클래스 규칙(`.partner-page-title`, `.partner-section-title` 등)이 있으나 `partner.css` 내에서만 사용되고 base.css를 건드리지 않는다.

**판정: ✅ 스코프 원칙 준수**

---

### C-02. CSS 변수 위치 (`:root` 금지, 앱 루트 ID 하위 선언)

```css
/* ✅ 올바른 패턴 */
#manage-rate { --rm-rq: 88px; --rm-tg: 88px; ... }
#manage-structure { --c-search: 75px; ... }
#manage-efficiency { ... }
```

전역 `:root`에 파트너 전용 변수를 추가한 사례 없음.

**판정: ✅ RULE-Q-02 준수**

---

### C-03. CSS 중복 패턴

`manage_structure`, `manage_rate`, `manage_efficiency` 세 섹션에서 아래 패턴이 거의 동일하게 반복된다:
- 상단 컨트롤 카드 폼 스타일
- 입력 테이블 헤더 패턴
- `.manage-input-head` / `.manage-input-title` 구조

```css
/* structure, rate 공통 — 거의 동일 */
#manage-structure .manage-input-head { ... }
#manage-rate .manage-input-head { ... }

/* mainTable 정책도 동일 규칙 반복 */
#manage-structure #mainTable { table-layout: auto !important; width: max-content !important; }
#manage-rate #mainTable { table-layout: auto !important; width: max-content !important; }
```

**🟡 개선 권장**: 공통 패턴을 partner.css 상단 "공통 섹션"으로 묶어 유지보수성 향상 가능. 단 스코프 누수 주의 필요 — 리팩터 시 각 `#manage-*` 하위에 묶거나 `:is(#manage-structure, #manage-rate)` 셀렉터 활용.

---

## D. 템플릿 레이어

### D-01. `{% extends %}` / `{% block %}` 구조

| 템플릿 | base | app_css/extra_head | 상태 |
|---|---|---|---|
| `manage_charts.html` (편제변경) | `base.html` | `app_css` 블록 | ✅ |
| `manage_rate.html` | `base.html` | `app_css` 블록 | ✅ |
| `manage_calculate.html` (지점효율) | `base.html` | `content_wrapper` 와이드 레이아웃 | ✅ |
| `manage_grades.html` | `base.html` | `extra_head` (Bootstrap Icons) | ✅ |
| `manage_tables.html` | `base.html` | `extra_head` | ✅ |
| `esign_confirm.html` | `base.html` | `app_css` 블록 | ✅ |

**판정: ✅ 전체 준수**

---

### D-02. URL / 권한 dataset 주입

| 템플릿 | dataset 주입 | 하드코딩 URL | 상태 |
|---|---|---|---|
| `manage_charts.html` | ✅ `data-fetch-url`, `data-save-url`, etc. | 없음 | ✅ |
| `manage_rate.html` | ✅ | 없음 | ✅ |
| `manage_calculate.html` | ✅ | 없음 | ✅ |
| `manage_grades.html` | ✅ | 없음 | ✅ |
| `manage_tables.html` | ✅ | 없음 | ✅ |
| `esign_confirm.html` | ✅ | `data-sign-url-template="/partner/api/esign/{id}/sign/"` | 🟡 |

**🟡 개선 권장**: `esign_confirm.html`의 `data-sign-url-template`에 URL 패턴이 템플릿 태그(`{% url %}`) 아닌 문자열 하드코딩으로 삽입되어 있다. URL 구성이 URL conf와 연동되지 않아 라우팅 변경 시 깨질 수 있다.

---

### D-03. json_script / boot 패턴 (서버→JS 데이터 전달)

| 템플릿 | 방식 | 상태 |
|---|---|---|
| `manage_calculate.html` | `{{ ManageefficiencyBoot\|json_script:"boot-efficiency" }}` + `json_boot_bridge.js` | ✅ |
| `manage_charts.html` | `{{ ManageStructureBoot\|json_script:"boot-structure" }}` + `json_boot_bridge.js` | ✅ |
| `manage_grades.html` | dataset 직접 주입 (단순값만) | ✅ |
| `manage_tables.html` | `window.csrfToken = "{{ csrf_token }}";` | ✅ (csrf_window 패턴) |
| `esign_confirm.html` | dataset 직접 주입 | ✅ |

**판정: ✅ 전체 준수**

---

### D-04. 권한별 UI 분기 (서버 템플릿 기준)

| 템플릿 | 서버 분기 방식 | 상태 |
|---|---|---|
| `manage_grades.html` | `{% if user.grade != 'superuser' and user.grade != 'head' %}` 경고 표시 | ✅ |
| `manage_tables.html` | `{% if user.grade != 'superuser' and user.grade != 'head' %}` 경고 표시 | ✅ |
| `esign_confirm.html` | `{% if can_input %}` / `{% if user.grade == 'superuser' %}` | ✅ |
| `manage_calculate.html` | `{% if can_input %}` 컨텍스트 변수 사용 | ✅ |

**판정: ✅ 서버에서 최종 권한 판단 준수**

---

## 기존 NEVER_DO 이슈 재확인

| 이슈 | 위치 | 현재 상태 |
|---|---|---|
| S-B-05: `subadmin.py` grade 변경 후 `log_action()` 미호출 | `partner/views/subadmin.py` | **✅ 수정 완료** — `ajax_add_sub_admin`, `ajax_delete_subadmin` 양쪽에 `log_action(request, ACTION.PARTNER_LEADER_ADD/DELETE, ...)` 정상 호출됨 |
| S-B-06: `accounts/tasks.py` 완료 분기 `log_action()` 미호출 | `accounts/tasks.py` | 이번 감사 범위 외 (별도 확인 필요) |
| S-D-01: `commission/views/` `@csrf_exempt` 사용 | `commission/views/` | 이번 감사 범위 외 |
| S-E-01/S-E-04: 미정의 ACTION 상수 사용 | 전체 | ✅ partner 앱 내 모든 사용 상수 사전 정의 확인됨 |

---

## 절대 수정 금지 목록 상태

| 항목 | 위치 | 상태 |
|---|---|---|
| `resolve_branch_for_query()` | `partner/views/utils.py` | ✅ 보존됨 (수정 금지) |
| `resolve_branch_for_write()` | `partner/views/utils.py` | ✅ 보존됨 (수정 금지) |
| `SubAdminTemp.db_table = "partner_subadmin_temp"` | `partner/models.py` | ✅ 보존됨 (마이그레이션 위험) |
| `json_ok` / `json_err` / `parse_json_body` | `partner/views/responses.py` | ✅ SSOT 보존됨 |
| `EfficiencyChange.confirm_group on_delete=PROTECT` | `partner/models.py` | ✅ 보존됨 |

---

## 모듈화 후보

### 현재 모듈화 현황

| 도메인 | Python | JS | 상태 |
|---|---|---|---|
| 편제변경 (structure) | `views/structure.py` 단일 파일 | `manage_structure/` 다중 ESM | 중간 |
| 요율변경 (rate) | `views/rate.py` 단일 파일 | `manage_rate/` 다중 ESM | 중간 |
| 지점효율 (efficiency) | `views/efficiency.py` 단일 파일 (~600+줄) | `manage_efficiency/` 다중 ESM | 중간 |
| 전자서명 (esign) | `views/esign.py` + `services/esign_service.py` | `esign_confirm/` 다중 IIFE | 양호 |
| 권한관리 (grades) | `views/grades.py` 단일 파일 | `manage_grades/index.js` 단일 IIFE (~830줄) | 개선 필요 |
| 테이블관리 (ratetable) | `views/ratetable.py` 단일 파일 | 별도 JS 파일 | 단순 구조 |

### 모듈화 우선 후보

1. **`manage_grades/index.js`** (830줄 IIFE): DataTables 초기화, 레벨 변경, 중간관리자 추가/삭제, 채널/파트/지점 캐스케이드를 모두 포함. ESM 분리 시 `fetch.js`, `save.js`, `delete.js`, `cascade.js`로 분리 가능.

2. **`partner/services/`**: 현재 `esign_service.py`만 서비스 레이어 존재. `structure`, `rate`, `efficiency`도 서비스 레이어 추출 시 뷰 함수가 HTTP 처리만 담당하도록 분리 가능.

3. **`_generate_confirm_group_id` SSOT화**: `efficiency.py`와 `esign.py`의 중복 함수를 `utils.py`로 이동.

---

## 회귀 위험 점검 체크리스트

코드 패치 적용 후 반드시 확인해야 할 9가지 항목:

- [ ] **권한 스코프 변경 여부**: `resolve_branch_for_query/write` 동작 유지 확인
- [ ] **URL reverse / 네임스페이스 깨짐**: `partner:*` URL 패턴 모두 동작 확인
- [ ] **템플릿 `dataset` / DOM id 변경 여부**: JS가 참조하는 `data-*` 속성명 일치 확인
- [ ] **첨부 다운로드 정책 위반 여부**: 파일 URL 직접 노출 없는지 확인
- [ ] **업로드 레지스트리/컬럼 탐지 영향 여부**: 엑셀 업로드 컬럼 이름 변경 없는지 확인
- [ ] **DataTables 정책 깨짐 여부**: `ajax_users_data` draw/data/recordsTotal 구조 유지
- [ ] **CSS 스코프 누수 가능성**: 새 규칙이 `#manage-*` 하위에만 영향 확인
- [ ] **운영 환경 영향**: Manifest staticfiles 사용 시 JS/CSS 경로 변경 없는지 확인
- [ ] **JSON 응답 형식 앱 규약 준수**: `{"status": "success"|"error"}` 구조 유지

---

## 2단계 패치 순서 권장

### Stage 1 — 보안/감사 필수 수정 (🔴 위반 해소)

| 순서 | 대상 | 내용 | 우선순위 |
|---|---|---|---|
| 1-A | `partner/views/structure.py` | `ajax_save`, `ajax_delete`에 `log_action(request, ACTION.PARTNER_STRUCTURE_SAVE/DELETE, ...)` 추가 | 최우선 |
| 1-B | `partner/views/grades.py` | `upload_grades_excel` 완료 분기에 `log_action(request, ACTION.PARTNER_GRADES_UPLOAD, meta={...})` 추가 | 최우선 |

**Stage 1 주의**: `structure.py`에 `from audit.constants import ACTION`, `from audit.services import log_action`, `import logging` 추가 필요. `grades.py`에도 동일.

### Stage 2 — 품질 개선 (🟡 개선 권장)

| 순서 | 대상 | 내용 | 예상 영향 |
|---|---|---|---|
| 2-A | `esign_confirm/fetch.js`, `save.js`, `sign.js` | `window.csrfToken` → `getCSRFToken()` import, `res.json()` → `readJsonOrThrow` | JS 변경, 기능 동일 |
| 2-B | `manage_grades/index.js` | `window.csrfToken` → `getCSRFToken()` import | JS 변경, 기능 동일 |
| 2-C | `manage_efficiency/dom_refs.js` | 정적 할당 → `get` 접근자 패턴 | BFCache 안전성 향상 |
| 2-D | `esign.py` | `_parse_json()` → `parse_json_body` from responses | 경미, 기능 동일 |
| 2-E | `structure.py`, `grades.py` | `traceback.print_exc()` → `logger.exception()` | 로그 집계 개선 |
| 2-F | `_generate_confirm_group_id` | `efficiency.py`, `esign.py` 중복 → `utils.py` SSOT | DRY 개선 |
| 2-G | `partner.css` | 공통 반복 패턴 묶음 | CSS 유지보수성 |

---

## 최종 집계

> 🔴 위반: **2건** (structure.py 감사 로그 누락, grades.py 엑셀 업로드 감사 로그 누락)  
> 🟡 개선 권장: **14건** (JSON SSOT 미준수 4건, 로깅 4건, CSRF RULE-Q-01 4건, 중복 함수 1건, CSS 중복 1건)  
> 코드 수정은 하지 않는다.
