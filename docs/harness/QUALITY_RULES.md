# QUALITY_RULES — 코드 품질 위반 규칙
> 출처: `docs/audit/quality_checklist.md` 의 🔴 위반 항목 (3건)
> 생성일: 2026-05-03 | 기준 커밋: 5e7e7f1

---

## RULE-Q-01. CSRF 토큰은 반드시 공통 유틸에서 가져올 것

❌ 금지:
```javascript
// static/js/board/collateral.js:38-43
function getCSRF() {
  const el = document.querySelector("[name=csrfmiddlewaretoken]");
  if (el) return el.value;
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : "";
}

// static/js/board/states_form.js:30-37
function getCsrfToken() { ... }  // 동일 패턴 재구현

// static/js/partner/manage_grades/index.js:38-43
function getCookie(name) { ... }  // 또 다른 재구현
```

위반 파일 목록 (12개+):
- `static/js/board/collateral.js:38-43`
- `static/js/board/states_form.js:30-37`
- `static/js/board/support_form.js:36-37`
- `static/js/dash/dash_retention_page.js:19-21`
- `static/js/commission/collect_home.js:72-79`
- `static/js/partner/esign_confirm/fetch.js:12-13`
- `static/js/partner/esign_confirm/save.js:25-26`
- `static/js/partner/esign_confirm/sign.js:14-15`
- `static/js/partner/manage_grades/index.js:38-43`
- `static/js/utils/file_upload_utils.js:51-70`
- `static/js/excel_upload.js:22-23`

✅ 올바른 방법:
```javascript
// ESM 파일 (type="module"):
import { getCSRFToken } from "../../common/manage/csrf.js";

// IIFE 파일 (일반 <script>):
// window.csrfToken이 csrf_window.js에 의해 노출돼 있으면 우선 사용
const csrf = window.csrfToken || getCSRFToken();
// getCSRFToken은 common/manage/csrf.js 의 전역 함수
```

📌 근거: CSRF 토큰 조회 로직이 12개 이상 파일에 분산돼 있어 쿠키 이름 변경·조회 방식 변경 시 전체 수정이 필요하다. `static/js/common/manage/csrf.js`의 `getCSRFToken()`이 SSOT다.

🔍 탐지:
```bash
grep -rn "getCookie\|getCsrf\|csrfmiddlewaretoken\|document\.cookie.*csrf" \
  static/js/ --include="*.js" | grep -v "csrf\.js"
# 결과가 있으면 위반
```

---

## RULE-Q-02. 앱 전용 CSS 변수를 :root 전역으로 선언하지 말 것

❌ 금지:
```css
/* static/css/apps/manual.css:12-15 */
:root {
  --manual-wide-width: 72vw;
  --manual-wide-max: 1200px;
}
/* → 모든 페이지에서 이 변수가 전역으로 노출됨 */
```

```css
/* static/css/apps/commission.css */
.info-table { ... }       /* 전역 클래스 — 스코프 없음 */
.ellipsis-cell { ... }    /* 전역 클래스 — 스코프 없음 */
.deposit-title { ... }    /* 전역 클래스 — 스코프 없음 */
.deposit-section-title { ... }  /* 전역 클래스 — 스코프 없음 */
```

✅ 올바른 방법:
```css
/* manual.css: 스코프 ID 하위 CSS 변수로 선언 */
#manual-detail {
  --manual-wide-width: 72vw;
  --manual-wide-max: 1200px;
}

/* commission.css: 페이지 ID 하위로 스코핑 */
#deposit-home .info-table { ... }
#deposit-home .ellipsis-cell { ... }
#collect-home .deposit-title { ... }
```

📌 근거: 앱 전용 CSS가 전역 네임스페이스를 오염시키면 다른 페이지에서 변수·클래스 충돌이 발생한다. 각 앱 CSS는 해당 앱의 루트 ID/클래스 하위에서만 동작해야 한다 (CLAUDE.md `[규약 F]`).

🔍 탐지:
```bash
grep -n "^:root\s*{" static/css/apps/*.css
# 결과가 있으면 위반
grep -n "^\.[a-z]" static/css/apps/commission.css | head -20
# 스코프 선택자 없이 시작하는 클래스 규칙 확인
```

---

## RULE-Q-03. 같은 앱 내 JSON 응답 헬퍼를 중복 구현하지 말 것

❌ 금지:
```python
# commission/views/api_deposit_impl.py:63-64
# commission/views/utils_json.py 에 _json_error가 이미 있음에도 재구현
def _json_err(message, *, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)
```

✅ 올바른 방법:
```python
# commission/views/api_deposit_impl.py 상단
from commission.views.utils_json import _json_error

# 이름이 달라야 할 경우 alias 사용
_json_err = _json_error

# 또는 직접 사용
return _json_error("오류 메시지")
```

📌 근거: `commission/views/utils_json.py`의 `_json_error`가 commission 앱 내 JSON 응답 SSOT다. 같은 앱 내에서 동일 기능을 다른 이름으로 재정의하면 signature 불일치·동작 차이가 생길 수 있다.

🔍 탐지:
```bash
grep -n "def _json_err\b\|def _json_error\b\|def _ok\b\|def _err\b" \
  commission/views/*.py
# 같은 앱 내에서 복수의 정의가 있으면 중복 검토 필요
grep -n "from commission.views.utils_json import" commission/views/api_deposit_impl.py
# import가 없으면 위반 가능성
```
