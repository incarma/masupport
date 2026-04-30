# django_ma CORE INFRA 운영·개발 지침서 — FINAL REFACTORED

> 목적: 추후 새 채팅에서 전체 소스코드를 다시 공유하지 않더라도, `django_ma` 프로젝트의 Core & Infra 영역을 기준으로 보안 취약점 보완, 성능개선, 코드정리, 운영 점검, 패치 설계를 일관되게 진행하기 위한 최종 기준 문서입니다.  
> 기준 상태: 최근 반영된 CSP strict 패치, `.file.url/.image.url` 전수 점검 결과, audit/proxy/log 보안 패치, accounts/commission 업로드 결과 권한 검증, dashboard JS 안정성 패치까지 포함합니다.

---

## 0. 현재 Core Infra 보안 상태 요약

### 0.1 완료된 최상급 보완사항

- [x] `/media/` 직접 접근 차단
  - Nginx에서 `/media/` 요청은 `403`으로 차단합니다.
  - 개발/운영 모두 파일 직접 URL 접근을 허용하지 않는 기준을 유지합니다.

- [x] `.file.url`, `.image.url` 직접 노출 전수 점검
  - 실제 다운로드/이미지 출력용 직접 URL 사용은 발견되지 않았습니다.
  - grep 결과에 남은 항목은 대부분 “직접 노출 금지” 주석/가이드 문구입니다.
  - 기준 명령:

    ```powershell
    rg "\.file\.url|\.image\.url" templates board manual partner commission dash `
      -g "*.html" -g "*.py" `
      -g "!**/__pycache__/**" `
      -g "!docs/**" `
      -g "!*.txt"
    ```

- [x] CSP inline script 제거
  - `onclick`, `onsubmit`, `onchange`, inline `<script>` 제거 방향으로 정리했습니다.
  - inline 이벤트는 공통 JS로 이동합니다.
  - 대표 신규/보조 JS:
    - `static/js/common/auto_submit_controls.js`
    - `static/js/common/confirm_submit.js`
    - `static/js/common/redirect_buttons.js`
    - `static/js/common/json_boot_bridge.js`
    - `static/js/common/csrf_window.js`
    - `static/js/common/prevent_form_submit.js`

- [x] CSP inline style 제거
  - `style=`, `<style>` 잔여 grep에서 마지막으로 확인된 `templates/admin/accounts/customuser/change_list.html`의 `<style>`도 외부 CSS로 이동하는 기준을 확정했습니다.
  - 최종 검증 명령:

    ```powershell
    rg "<style>|style=|onclick=|onsubmit=|onchange=" templates board manual partner commission dash `
      -g "*.html" `
      -g "!**/__pycache__/**"
    ```

- [x] CSP `script-src 'self'` / `style-src 'self'` 기준 정립
  - 외부 CDN은 기본 차단합니다.
  - 예외적으로 Daum 주소 API를 유지하려면 `https://ssl.daumcdn.net`를 명시 허용해야 합니다.
  - Cloudflare beacon은 그래프 미표시 원인이 아니며, 필요 없으면 허용하지 않습니다.

- [x] CSRF failure 로그 민감정보 마스킹
  - cookie, authorization, token 계열 값은 원문 로그 금지입니다.
  - `audit.utils.mask_value()`, `mask_querystring()`, `is_sensitive_key()` 기준으로 마스킹합니다.

- [x] X-Forwarded-For 신뢰 제한
  - `AUDIT_PROXY_HEADER_ENABLED=True`일 때만 proxy header를 신뢰합니다.
  - `AUDIT_TRUSTED_PROXY_CIDRS`에 포함된 reverse proxy에서 들어온 요청만 XFF/X-Real-IP를 사용합니다.

- [x] accounts 업로드 결과 파일 owner 검증
  - `task_id` 단독으로 결과 파일에 접근할 수 없도록 owner binding을 적용합니다.
  - owner 없는 legacy cache는 `superuser`만 fallback 허용합니다.

- [x] commission fail token owner 검증
  - 업로드 실패 엑셀 token은 `owner_id`와 연결합니다.
  - 신규 token은 업로드 실행자 본인만 다운로드 가능합니다.
  - legacy token은 superuser만 fallback 허용합니다.

- [x] dashboard 그래프 JS 안정성 보정
  - `dash_sales_page.js`의 `hideWarnById()`에서 잘못된 변수명 `el` 사용을 `warnEl`로 수정합니다.
  - CSP 차단 후 그래프 미표시 원인과 JS 함수 누락/변수 오류를 분리해서 판단합니다.

---

## 1. 적용 범위

이 문서는 Core Infra와 전역 공통 기능을 기준으로 합니다.

```text
django_ma/
├─ manage.py
├─ Dockerfile
├─ docker-compose.yaml
├─ docker-compose.dev.yml
├─ requirements.txt
├─ web_ma/
│  ├─ settings.py
│  ├─ urls.py
│  ├─ views.py
│  ├─ middleware.py
│  ├─ celery.py
│  ├─ asgi.py
│  └─ wsgi.py
├─ accounts/
│  ├─ apps.py
│  ├─ constants.py
│  ├─ custom_admin.py
│  ├─ decorators.py
│  ├─ forms.py
│  ├─ models.py
│  ├─ signals.py
│  ├─ urls.py
│  ├─ utils.py
│  ├─ views.py
│  ├─ admin.py
│  ├─ tasks.py
│  ├─ search_api.py
│  ├─ middleware/force_password_change.py
│  ├─ policies/password_policy.py
│  └─ services/users_excel_import.py
├─ audit/
│  ├─ admin.py
│  ├─ apps.py
│  ├─ constants.py
│  ├─ middleware.py
│  ├─ models.py
│  ├─ services.py
│  └─ utils.py
├─ templates/
│  ├─ base.html
│  ├─ no_permission_popup.html
│  ├─ landing/index.html
│  ├─ registration/login.html
│  ├─ registration/password_change_form.html
│  ├─ registration/password_change_done.html
│  ├─ admin/accounts/customuser/change_list.html
│  └─ components/search_user_modal.html
├─ static/
│  ├─ css/base.css
│  ├─ css/fixes.css
│  ├─ css/plugins/datatables.css
│  ├─ css/apps/*.css
│  ├─ css/admin/accounts_customuser.css
│  └─ js/
│     ├─ base_ui.js
│     ├─ datatable_config.js
│     ├─ login_page.js
│     ├─ admin_user_excel.js
│     ├─ excel_upload.js
│     ├─ landing/index.js
│     ├─ utils/file_upload_utils.js
│     ├─ common/forms/*
│     ├─ common/manage/*
│     └─ common/*.js
└─ ops/
   ├─ nginx/default.conf
   ├─ certs/*
   └─ maintenance/maintenance.html
```

---

## 2. 절대 운영 원칙

### 2.1 settings / deployment

- `DJANGO_SETTINGS_MODULE`은 항상 `web_ma.settings`입니다.
- 환경 분기는 `manage.py`가 아니라 `web_ma/settings.py`에서 처리합니다.
- 운영 구조는 `Nginx → Gunicorn/Uvicorn → Django ASGI`입니다.
- DB는 PostgreSQL, broker/cache는 Redis, 비동기 처리는 Celery/Celery Beat입니다.
- DEBUG 방어 로직은 운영 사고 방지용이므로 임시 제거하지 않습니다.

### 2.2 파일 접근

- `.file.url`, `.image.url` 직접 사용 금지.
- `/media/` 직접 접근 금지.
- 모든 파일 조회/다운로드는 앱별 보호 view에서 권한 검증 후 `FileResponse`로 제공합니다.
- 다운로드/업로드는 audit 대상입니다.
- 파일명은 RFC5987 호환 방식으로 내려야 합니다.

### 2.3 권한

신규 기준 등급:

```text
superuser
head
leader
basic
resign
inactive
```

legacy:

```text
main_admin → head
sub_admin  → leader
```

- 신규 코드에서 `main_admin`, `sub_admin`로 권한 판단하지 않습니다.
- 메뉴 노출은 UX 보조일 뿐이며 실제 권한은 view/policy/queryset/object-level에서 검증합니다.

### 2.4 CSP

최종 목표:

```text
default-src 'self';
script-src 'self';
style-src 'self';
img-src 'self' data: https:;
font-src 'self' data:;
connect-src 'self';
object-src 'none';
base-uri 'self';
frame-ancestors 'none';
form-action 'self';
```

- inline script 금지.
- inline style 금지.
- `onclick`, `onsubmit`, `onchange` 금지.
- `<style>` 금지.
- 외부 CDN은 기본 금지.
- Daum postcode가 필요한 경우만 `https://ssl.daumcdn.net`를 `script-src`에 명시 허용합니다.

### 2.5 프론트 표준

- JS는 dataset boot 패턴을 사용합니다.
- JSON은 `json_script` + `json_boot_bridge.js`를 사용합니다.
- CSRF는 `common/manage/csrf.js` 또는 `csrf_window.js` 기준으로 처리합니다.
- Fetch JSON 처리는 `readJsonOrThrow()`를 우선합니다.
- 중복 바인딩은 `dataset.bound`, `dataset.inited`로 방지합니다.
- BFCache 재진입에 안전해야 합니다.

---

## 3. Django 프로젝트 진입점

### 3.1 `manage.py`

유지 기준:

```python
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ma.settings")
```

금지:

- 환경별 settings 분기를 `manage.py`에 추가.
- dev/prod 별 별도 settings module을 임의로 지정.

### 3.2 `web_ma/asgi.py`, `web_ma/wsgi.py`

- 운영은 ASGI + Gunicorn/Uvicorn 기준입니다.
- WSGI는 호환 목적으로 유지합니다.
- ASGI application import 구조를 변경하지 않습니다.

---

## 4. 전역 URL 기준

### 4.1 `web_ma/urls.py`

핵심 route:

| URL | 대상 | name |
|---|---|---|
| `/healthz` | `web_ma.views.healthz` | `healthz` |
| `/login/` | `accounts.views.SessionCloseLoginView` | `login` |
| `/logout/` | Django `LogoutView` | `logout` |
| `/admin/` | `accounts.custom_admin.custom_admin_site.urls` | custom admin |
| `/` | `web_ma.views.landing_view` | `home` |
| `/accounts/` | `accounts.urls` namespace `accounts` | - |
| `/board/` | `board.urls` | - |
| `/commission/` | `commission.urls` | - |
| `/dash/` | `dash.urls` | - |
| `/partner/` | `partner.urls` namespace `partner` | - |
| `/manual/` | `manual.urls` | - |

500 handler:

```python
handler500 = "web_ma.views.handler500"
```

중요:

- `web_ma/urls.py`에서 `/media/` 직접 서빙 금지.
- DEBUG 환경에서도 `/media/` 직접 서빙 금지.
- 파일 접근은 앱별 보호 view가 담당합니다.

### 4.2 강제 비밀번호 변경 whitelist

URL name 기준:

```text
login
logout
accounts:password_change
accounts:password_change_done
```

---

## 5. 전역 View 기준

### 5.1 `web_ma/views.py`

| 함수 | 역할 | 기준 |
|---|---|---|
| `healthz()` | Django 컨테이너 healthcheck | `ok`, 200 |
| `handler500()` | 운영 500 traceback 로깅 | traceback 로그, 사용자 상세 노출 금지 |
| `landing_view()` | 인증/미인증 랜딩 분기 | 인증 사용자 `board:industry_info` redirect |

### 5.2 `handler500`

- `logger.exception("Unhandled server error (500)")` 유지.
- 사용자 응답은 `Server Error (500)` 수준으로 제한합니다.

---

## 6. Settings 운영 기준

### 6.1 환경 선택

`web_ma/settings.py`는 다음의 SSOT입니다.

- APP_ENV/ENV_FILE 기반 env 선택
- DEBUG fail-fast
- ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS
- INSTALLED_APPS / MIDDLEWARE
- DATABASE_URL
- AUTH_USER_MODEL
- 강제 비밀번호 변경 정책
- static/media 경로
- session/cookie 보안
- Redis/Celery
- upload 경로/제한
- logging
- reverse proxy / SSL
- security headers / CSP

### 6.2 DEBUG fail-fast

유지해야 하는 방어선:

- prod에서 `DEBUG=True` 금지.
- dev + runserver에서 `DEBUG=False` 금지.
- dev에서 DB host가 `db`이면 금지.
- DEBUG 환경에서 운영 DB 키워드가 DATABASE_URL에 있으면 금지.

### 6.3 DATABASE

기준:

```python
DATABASE_URL = config("DATABASE_URL")
DATABASES["default"] = dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=False)
DATABASES["default"]["OPTIONS"].update({"client_encoding": "UTF8"})
```

원칙:

- DB 연결 정보는 `DATABASE_URL` 단일화.
- Windows/한글 환경을 고려하여 UTF-8 강제.
- dev/prod DB 오접속 방어 유지.

### 6.4 Static / Media

Static:

```python
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
```

운영:

```python
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
```

Media:

```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```

중요:

- `MEDIA_URL`은 저장 위치 개념입니다.
- 공개 접근 정책은 Nginx와 보호 view가 결정합니다.
- `/media/`는 Nginx에서 403입니다.

### 6.5 Session / Cookie

운영 기준:

- `SESSION_ENGINE = "django.contrib.sessions.backends.db"`
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`
- `SESSION_COOKIE_AGE = 3600`
- `SESSION_SAVE_EVERY_REQUEST = True`
- `SESSION_COOKIE_HTTPONLY = True`
- `CSRF_COOKIE_HTTPONLY = False`
- prod에서 secure cookie true
- `SESSION_COOKIE_SAMESITE = "Lax"`
- `CSRF_COOKIE_SAMESITE = "Lax"`

### 6.6 Audit proxy settings

기준:

```python
AUDIT_PROXY_HEADER_ENABLED = config("AUDIT_PROXY_HEADER_ENABLED", default=IS_PROD, cast=bool)
AUDIT_TRUSTED_PROXY_CIDRS = config(..., cast=lambda v: tuple(...))
```

권장 운영 env:

```env
AUDIT_PROXY_HEADER_ENABLED=True
AUDIT_TRUSTED_PROXY_CIDRS=127.0.0.1/32,::1/128,172.16.0.0/12
```

### 6.7 CSP

현재 최종 운영 목표:

```python
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
)
```

Daum postcode 유지 시:

```python
"script-src 'self' https://ssl.daumcdn.net; "
```

Cloudflare beacon은 필수 기능이 아니면 허용하지 않습니다.

---

## 7. Middleware 기준

### 7.1 `web_ma/middleware.py`

| 클래스 | 역할 |
|---|---|
| `SecurityHeadersMiddleware` | CSP, Referrer, Permissions, COOP, XFO |
| `ForceCSRFCookieOnLoginMiddleware` | 로그인 GET 시 CSRF cookie 강제 발급 |
| `CleanupLegacyCSRFCookieMiddleware` | 운영 도메인 중복 csrftoken 정리 |

권장 순서:

```text
SecurityMiddleware
WhiteNoiseMiddleware
SecurityHeadersMiddleware
SessionMiddleware
CommonMiddleware
RequestLogMiddleware
CsrfViewMiddleware
ForceCSRFCookieOnLoginMiddleware
CleanupLegacyCSRFCookieMiddleware
AuthenticationMiddleware
ForcePasswordChangeMiddleware
MessageMiddleware
XFrameOptionsMiddleware
```

주의:

- `ForcePasswordChangeMiddleware`는 AuthenticationMiddleware 이후.
- CSRF 관련 미들웨어 위치 변경은 로그인/랜딩 AJAX에 영향.

---

## 8. Celery 기준

### 8.1 `web_ma/celery.py`

역할:

- Celery app 생성
- Django settings 로드
- app task autodiscover
- `board.tasks` 패키지 명시 autodiscover
- beat schedule SSOT

### 8.2 Beat schedule

| 이름 | task | 주기 |
|---|---|---|
| `board-industry-news-collect` | `board.tasks.industry_info.collect_board_industry_news` | 6시간마다 5분 |
| `board-industry-cleanup-daily` | `board.tasks.industry_info.cleanup_old_industry_articles` | 매일 03:00 |
| `dash-agg-hourly` | `dash.tasks.build_sales_aggs_hourly` | 매시간 10분 |
| `dash-forecast-daily` | `dash.tasks.build_sales_forecasts_daily` | 매일 02:10 |
| `dash-forecast-hourly` | `dash.tasks.build_sales_forecasts_hourly` | 매시간 20분 |

Task 이름 확인:

```bash
celery -A web_ma inspect registered
```

---

## 9. Docker / Nginx 기준

### 9.1 Services

| 서비스 | 역할 |
|---|---|
| `db` | PostgreSQL |
| `redis` | Redis |
| `web` | Django ASGI + Gunicorn/Uvicorn |
| `celery` | Celery worker |
| `celery-beat` | Celery beat |
| `nginx` | TLS termination + reverse proxy |

### 9.2 Nginx 핵심

```nginx
location ^~ /media/ {
    access_log off;
    return 403;
}
```

원칙:

- unknown host는 `444`.
- HTTP는 HTTPS redirect.
- `/static/`은 Nginx static serving + immutable cache.
- `/media/`는 403.
- 502/503/504는 maintenance page.

---

## 10. Template / UI 기준

### 10.1 `base.html`

CSS 로드 순서:

```text
bootstrap.min.css
css/base.css
css/plugins/datatables.css
css/fixes.css
{% block app_css %}
```

JS 로드 순서:

```text
bootstrap.bundle.min.js
js/base_ui.js
{% block datatables_bundle %}
{% block extra_js %}
```

### 10.2 `no_permission_popup.html`

최종 standalone 기준:

```django
{% load static %}
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>접근 권한 없음</title>
  <link rel="stylesheet" href="{% static 'css/base.css' %}">
</head>
<body>
<div class="permission-box">
  <p>접근 권한이 없는 페이지입니다.</p>
  <button type="button" class="btn btn-primary" data-redirect-url="/">
    홈으로 이동
  </button>
</div>
<script src="{% static 'js/common/redirect_buttons.js' %}?v={% now 'U' %}"></script>
</body>
</html>
```

주의:

- standalone HTML에는 `{% block extra_js %}`를 쓰지 않습니다.
- `{% static %}` 사용 시 `{% load static %}` 필수.
- `onclick` 금지, `data-redirect-url` 사용.

### 10.3 `components/search_user_modal.html`

DOM contract:

| 요소 | 역할 |
|---|---|
| `#searchUserModal` | modal root |
| `data-search-url` | 검색 URL |
| `#searchUserForm` | form |
| `#searchKeyword` | 검색어 input |
| `#searchResults` | 결과 영역 |

연동 JS:

```text
static/js/common/search_user_modal.js
```

---

## 11. CSS 레이어 기준

### 11.1 `base.css`

포함:

- design token
- typography
- body layout
- navbar
- button
- form
- card
- loading overlay
- 공통 utility
- CSP-safe helper class

최근 추가 기준:

```css
.page-title-primary
.max-w-600
.max-w-640
.max-w-720
.progress-h-20
.toast-z-1080
.login-card-wrap
.auth-done-wrap
.spinner-4rem
.blank-h-32
.pre-wrap-break
.ellipsis-w-260
```

### 11.2 `fixes.css`

포함:

- 전역 최소 fix
- 충돌 방어
- privacy watermark

금지:

- 앱 전용 UI 스타일 추가.
- 특정 app의 상세 레이아웃 조정.

### 11.3 `plugins/datatables.css`

포함:

- DataTables 공통 스킨.
- 앱별 정책 강제 금지.

### 11.4 `apps/*.css`

- board는 `.board-scope` 하위.
- partner는 `#manage-*`, `.partner-*` 중심.
- commission은 commission root/class 하위.
- manual은 manual root/class 하위.
- dash는 dash root/class 하위.

---

## 12. 공통 JS 기준

### 12.1 신규 CSP-safe 공통 JS

| 파일 | 역할 |
|---|---|
| `static/js/common/auto_submit_controls.js` | `select[data-auto-submit="true"]` 변경 시 form submit |
| `static/js/common/confirm_submit.js` | `form[data-confirm-submit]` submit confirm |
| `static/js/common/redirect_buttons.js` | `[data-redirect-url]` 클릭 redirect |
| `static/js/common/json_boot_bridge.js` | `json_script` 값을 window 전역으로 연결 |
| `static/js/common/csrf_window.js` | hidden input/cookie에서 `window.csrfToken` 설정 |
| `static/js/common/prevent_form_submit.js` | `form[data-prevent-submit="true"]` submit 차단 |

### 12.2 기존 공통 JS

| 파일 | 역할 |
|---|---|
| `admin_user_excel.js` | admin upload 중복 submit 방지 |
| `login_page.js` | 로그인 중복 submit 방지 |
| `datatable_config.js` | `.datatable` 자동 초기화 |
| `excel_upload.js` | Excel fetch upload + 결과 modal |
| `utils/file_upload_utils.js` | 범용 첨부 파일 UI |
| `common/forms/dom.js` | DOM 유틸 |
| `common/forms/premium.js` | 보험료 콤마 처리 |
| `common/forms/rows.js` | 행 추가/삭제 |
| `common/manage/http.js` | `readJsonOrThrow()` |
| `common/manage/csrf.js` | `getCSRFToken()` |

### 12.3 JS 표준 패턴

중복 submit:

```js
if (form.dataset.submitting === "1") return;
form.dataset.submitting = "1";
```

중복 초기화:

```js
if (root.dataset.inited === "1") return;
root.dataset.inited = "1";
```

fetch JSON:

```js
const data = await readJsonOrThrow(res);
```

DOM show/hide:

```js
el.classList.remove("d-none");
el.classList.add("d-none");
```

inline style 직접 조작은 가능하면 CSS class 방식으로 대체합니다.  
단, Chart.js canvas 내부 렌더링이나 progress bar width처럼 동적 수치 UI는 제한적으로 허용할 수 있습니다.

---

## 13. Accounts 앱 기준

### 13.1 `CustomUser`

PK:

```python
id = models.CharField(max_length=30, unique=True, primary_key=True)
USERNAME_FIELD = "id"
```

조직 필드:

```text
channel > division > part > branch
```

등급:

```text
superuser, head, leader, basic, resign, inactive
```

save hook:

- `grade == inactive`이면 `is_active=False`.

### 13.2 로그인/lockout

`accounts/views.py`의 `SessionCloseLoginView`가 담당합니다.

기준:

- 5회 실패 시 lock.
- 성공 시 fail state reset.
- default password(`id`, `incar{id}`) 감지 시 `must_change_password=True`.
- AJAX 로그인은 JSON 응답.

### 13.3 업로드 결과 보안

accounts 업로드 결과 다운로드 기준:

- `task_id` 필요.
- cache owner 검증.
- owner가 있으면 요청자와 일치해야 함.
- owner 없는 legacy는 superuser만 fallback.
- result path는 `UPLOAD_RESULT_DIR` 하위인지 검증.

### 13.4 검색 API

`accounts/search_api.py` 기준:

| grade | 범위 |
|---|---|
| `superuser` | 전체 또는 선택 branch |
| `head` | 본인 branch |
| `leader` | 본인 branch 또는 SubAdminTemp scope |
| `basic/inactive` | 본인만 |

---

## 14. Audit 앱 기준

### 14.1 RequestLog

- 모든 요청/응답 단위 로그.
- body 저장 금지.
- querystring은 마스킹.

### 14.2 AuditLog

- 중요 행위 기록.
- 다운로드/업로드/권한 변경/로그인/피드백/전자서명 등.

### 14.3 `audit/utils.py`

핵심 함수:

| 함수 | 역할 |
|---|---|
| `is_sensitive_key()` | 민감키 판단 |
| `mask_value()` | 전화번호/주민번호/긴 문자열 마스킹 |
| `mask_querystring()` | querystring 마스킹 |
| `get_client_ip()` | trusted proxy에서만 XFF/X-Real-IP 사용 |

XFF 정책:

```text
AUDIT_PROXY_HEADER_ENABLED=False → REMOTE_ADDR만 사용
AUDIT_PROXY_HEADER_ENABLED=True  → REMOTE_ADDR이 trusted CIDR일 때만 XFF 사용
```

---

## 15. Commission fail token 기준

업로드 실패 엑셀 token 정책:

- cache key: `commission:upload_fail:{token}`
- payload:
  - `content`
  - `filename`
  - `owner_id`
- 신규 token은 owner만 다운로드.
- legacy owner 없는 token은 superuser만 fallback.
- TTL: 1 hour.

다운로드 endpoint:

- `@login_required`
- `@grade_required("superuser")`
- `_can_download_fail_payload()` 검증.

---

## 16. Manual sanitize 기준

manual block content는 저장된 HTML을 렌더링하므로 stored XSS 방어가 필요합니다.

기준:

```django
{% load manual_sanitize %}
{{ b.content|sanitize_manual_html }}
```

금지:

```django
{{ b.content|safe }}
```

필터 위치:

```text
manual/templatetags/manual_sanitize.py
```

권장 allowlist:

- `p`, `br`, `div`, `span`
- `strong`, `b`, `em`, `i`, `u`, `s`
- `ul`, `ol`, `li`
- `blockquote`, `pre`, `code`
- heading
- table 관련 태그
- `a`

금지:

- `script`
- `style`
- `on*` event attributes
- style attribute
- javascript: URL

---

## 17. Dash frontend 안정성 기준

### 17.1 Chart.js

- Chart.js는 로컬 vendor 사용.
- CDN 사용 금지.
- `dash_sales_page.js`에서 Chart.js 미로딩 시 오류를 명확히 남깁니다.

### 17.2 `hideWarnById()` 버그 기준

수정 기준:

```js
function hideWarnById(warnId) {
  const warnEl = document.getElementById(warnId);
  if (!warnEl) return;
  warnEl.classList.add("d-none");
  warnEl.textContent = "";
}
```

금지:

```js
el.classList.add("d-none");
```

### 17.3 CSP와 Cloudflare beacon

콘솔 경고:

```text
static.cloudflareinsights.com/beacon.min.js blocked by CSP
```

판단:

- 그래프 미표시 직접 원인이 아닙니다.
- 필수 분석 기능이 아니면 CSP에 허용하지 않습니다.

---

## 18. 보안 점검 체크리스트

### 18.1 최상급

- [ ] `rg "<style>|style=|onclick=|onsubmit=|onchange=" ...` 출력 0건인가?
- [ ] `style-src 'self'` 적용 가능한가?
- [ ] `.file.url`, `.image.url` 실제 사용 0건인가?
- [ ] `/media/` 직접 접근 403인가?
- [ ] manual `b.content|safe`가 제거되었는가?
- [ ] 업로드 결과 파일이 owner 검증을 거치는가?
- [ ] commission fail token이 owner 검증을 거치는가?
- [ ] XFF는 trusted proxy에서만 신뢰하는가?
- [ ] CSRF failure 로그에 cookie/token 원문이 없는가?

### 18.2 상급

- [ ] 모든 upload endpoint에 크기/확장자/MIME 검증이 있는가?
- [ ] 다운로드/업로드 audit가 있는가?
- [ ] Celery task가 idempotent한가?
- [ ] temp/result cleanup 정책이 있는가?
- [ ] RequestLog retention 정책이 있는가?

### 18.3 중급

- [ ] fetch JSON은 `readJsonOrThrow()`를 사용하는가?
- [ ] DataTables destroy/reinit이 안전한가?
- [ ] BFCache 재진입에 안전한가?
- [ ] duplicate submit 방지가 있는가?
- [ ] 공통 JS 유틸 중복이 없는가?

---

## 19. 성능개선 점검 기준

### 19.1 DB

- [ ] N+1 query 여부
- [ ] `select_related`, `prefetch_related` 적용 가능 여부
- [ ] bulk 처리 가능 여부
- [ ] transaction 범위 과도 여부
- [ ] `select_for_update()` 필요 여부
- [ ] 인덱스 적정성

### 19.2 Celery

- [ ] task 재실행 안전성
- [ ] batch size 적정성
- [ ] timeout 적정성
- [ ] progress cache timeout
- [ ] result cleanup

### 19.3 Frontend

- [ ] 이벤트 중복 바인딩 여부
- [ ] DOM query 과다 여부
- [ ] chart destroy/recreate 안정성
- [ ] style 직접 조작 최소화
- [ ] 공통 유틸 사용 여부

---

## 20. grep / 점검 명령

### 20.1 CSP inline 점검

```powershell
rg "<style>|style=|onclick=|onsubmit=|onchange=" templates board manual partner commission dash `
  -g "*.html" `
  -g "!**/__pycache__/**"
```

정상:

```text
출력 없음
```

### 20.2 file url 점검

```powershell
rg "\.file\.url|\.image\.url" templates board manual partner commission dash `
  -g "*.html" -g "*.py" `
  -g "!**/__pycache__/**" `
  -g "!docs/**" `
  -g "!*.txt"
```

정상:

- 실제 사용 0건.
- 주석만 남는 경우 통과로 판단 가능.

### 20.3 Django 검증

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --dry-run --noinput
```

### 20.4 Docker / Celery

```bash
docker compose ps
docker compose logs -f web
docker compose logs -f celery
docker compose logs -f celery-beat
docker compose logs -f nginx
celery -A web_ma inspect registered
```

### 20.5 Healthcheck

```bash
curl -i https://ma-support.kr/healthz
curl -i http://127.0.0.1/nginx-healthz
curl -i https://ma-support.kr/media/test.txt
```

`/media/` 기대값:

```text
403 Forbidden
```

---

## 21. 패치 응답 표준

Core Infra 패치 요청 시 다음 형식으로 답합니다.

### 21.1 변경 목적

1~2줄.

### 21.2 수정 파일 목록 + 영향도

| 파일 | 변경 내용 | 영향도 |
|---|---|---|

### 21.3 회귀 위험 체크

- [ ] 권한 스코프 변경 여부
- [ ] URL name/reverse 변경 여부
- [ ] template DOM id/dataset 변경 여부
- [ ] 파일 다운로드 정책 위반 여부
- [ ] upload/cache/task contract 변경 여부
- [ ] DataTables 정책 영향 여부
- [ ] CSS 전역 누수 여부
- [ ] CSP 위반 여부
- [ ] 운영 설정 영향 여부

### 21.4 diff patch

- 기존 파일은 unified diff.
- 신규 파일은 최종본.
- 기능 변화 0 요청이면 동작 동일 보장 포인트 명시.

### 21.5 검증

- `python manage.py check`
- 관련 페이지 수동 테스트
- 권한별 접근 확인
- 로그 확인
- CSP console 확인

---

## 22. 금지 패턴

- `/media/` 직접 서빙 허용
- `.file.url`, `.image.url` 직접 링크
- inline `<script>`, `<style>`, `style=`, `onclick`, `onsubmit`, `onchange`
- DEBUG=True 운영 임시 해결
- CSRF exempt 남용
- token/password/cookie 원문 로그
- legacy `main_admin/sub_admin` 신규 권한 판단
- base.css/fixes.css에 앱 전용 상세 스타일 추가
- Celery beat task명과 실제 task명 불일치
- object permission 없이 파일 반환
- task_id/token만으로 결과 파일 반환

---

## 23. 빠른 위치 참조표

| 목적 | 파일 | 함수/클래스 |
|---|---|---|
| 전역 URL | `web_ma/urls.py` | `urlpatterns` |
| healthcheck | `web_ma/views.py` | `healthz` |
| 500 handler | `web_ma/views.py` | `handler500` |
| 보안 헤더 | `web_ma/middleware.py` | `SecurityHeadersMiddleware` |
| Celery schedule | `web_ma/celery.py` | `app.conf.beat_schedule` |
| CustomUser | `accounts/models.py` | `CustomUser` |
| 로그인 | `accounts/views.py` | `SessionCloseLoginView` |
| 계정 upload progress/result | `accounts/views.py` | `upload_progress_view`, `upload_result_view` |
| custom admin | `accounts/custom_admin.py` | `CustomAdminSite` |
| 계정 Excel task | `accounts/tasks.py` | `process_users_excel_task` |
| 계정 Excel parser | `accounts/services/users_excel_import.py` | `build_defaults_from_row` |
| 사용자 검색 | `accounts/search_api.py` | `search_users_for_api` |
| 요청 로그 | `audit/middleware.py` | `RequestLogMiddleware` |
| 액션 로그 | `audit/services.py` | `log_action` |
| 마스킹/IP | `audit/utils.py` | `mask_value`, `get_client_ip` |
| CSP-safe redirect | `static/js/common/redirect_buttons.js` | click delegation |
| CSP-safe confirm | `static/js/common/confirm_submit.js` | submit confirm |
| CSP-safe auto submit | `static/js/common/auto_submit_controls.js` | select auto submit |
| JSON boot | `static/js/common/json_boot_bridge.js` | json_script bridge |
| CSRF window | `static/js/common/csrf_window.js` | csrf bridge |
| fetch JSON | `static/js/common/manage/http.js` | `readJsonOrThrow` |

---

## 24. 향후 개선 후보

- RequestLog retention/partitioning
- upload temp/result cleanup 자동화
- Celery idempotency 전수 점검
- admin legacy grade 문구 제거
- 외부 Daum postcode 대체 가능성 검토
- Cloudflare beacon 사용 여부 결정
- upload MIME validation 전 앱 일관화
- DataTables 공통 init 정책 정리
- CSP report endpoint 추가
- 보안 grep CI 자동화
- pytest 기반 permission/file download regression test 추가

---

## 25. 이후 새 채팅 기본 전제

향후 Core Infra 관련 요청이 들어오면 다음을 기본 전제로 판단합니다.

1. settings SSOT는 `web_ma.settings`.
2. 운영은 Docker Compose + Nginx + Gunicorn/Uvicorn + Redis + Celery + PostgreSQL.
3. `/media/` 직접 접근 금지.
4. 파일 다운로드는 보호 view + 권한 검증 + FileResponse.
5. 권한 등급은 `superuser/head/leader/basic/resign/inactive`.
6. `main_admin/sub_admin`은 legacy.
7. CSP strict 기준은 `script-src 'self'`, `style-src 'self'`.
8. inline script/style/event handler는 금지.
9. 계정 upload result와 commission fail token은 owner 검증이 필요.
10. audit log는 민감정보 마스킹과 request_id 연결이 필요.
11. 프론트는 dataset boot, safe binding, CSRF utility, `readJsonOrThrow`, duplicate submit guard를 기본 패턴으로 사용.
12. CSS는 base/plugins/fixes/apps 레이어를 유지.
13. 기존 파일 수정은 diff, 신규 파일은 최종본으로 제시.
14. 패치 후 grep/check/collectstatic 검증을 제시.
