# django_ma CORE INFRA 운영 지침서

> 목적: 앞으로 전체 코드를 다시 공유하지 않더라도 `core infra` 관련 보안 취약점 보완, 성능개선, 코드정리, 운영 점검, 패치 설계를 일관된 기준으로 진행하기 위한 기준 문서입니다.

---

## 1. 적용 범위

이 문서는 다음 코드 영역을 기준으로 합니다.

```text
django_ma/
├─ manage.py
├─ Dockerfile
├─ docker-compose.yaml
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
│  └─ components/search_user_modal.html
├─ static/
│  ├─ css/base.css
│  ├─ css/fixes.css
│  ├─ css/plugins/datatables.css
│  └─ js/
│     ├─ base_ui.js
│     ├─ datatable_config.js
│     ├─ login_page.js
│     ├─ admin_user_excel.js
│     ├─ excel_upload.js
│     ├─ landing/index.js
│     ├─ utils/file_upload_utils.js
│     ├─ common/forms/*
│     └─ common/manage/*
└─ ops/
   ├─ nginx/default.conf
   ├─ certs/*
   └─ maintenance/maintenance.html
```

---

## 2. 핵심 운영 원칙

### 2.1 가장 중요한 원칙

- `DJANGO_SETTINGS_MODULE`은 `web_ma.settings`가 기준입니다.
- 운영 구조는 `Nginx → Gunicorn/Uvicorn → Django ASGI`입니다.
- DB는 PostgreSQL, broker/cache는 Redis, 비동기 처리는 Celery/Celery Beat입니다.
- 파일 다운로드는 절대 `.file.url` 직접 링크로 처리하지 않습니다.
- `/media/` 직접 접근은 Nginx에서 403으로 차단합니다.
- 모든 파일 조회/다운로드는 앱별 보호 view에서 권한 검증 후 `FileResponse`로 제공합니다.
- 권한 등급은 신규 기준인 `superuser`, `head`, `leader`, `basic`, `resign`, `inactive`를 사용합니다.
- `main_admin`, `sub_admin`은 legacy 잔재이며 신규 권한 판단에는 사용하지 않습니다.
- CSS는 `base.css` / `plugins/datatables.css` / `fixes.css` / `apps/*` 레이어를 유지합니다.
- 프론트 fetch JSON 처리는 `static/js/common/manage/http.js`의 `readJsonOrThrow()`를 우선 사용합니다.

---

## 3. Django 프로젝트 진입점

### 3.1 `manage.py`

위치: `django_ma/manage.py`

역할:

- Django management command 진입점입니다.
- `DJANGO_SETTINGS_MODULE`을 `web_ma.settings`로 고정합니다.

변경 금지 기준:

```python
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ma.settings")
```

환경별 settings 분기는 `manage.py`에서 하지 않습니다. 환경 분기는 `web_ma/settings.py`의 `APP_ENV`, `ENV_FILE` 기준으로 처리합니다.

### 3.2 `web_ma/asgi.py`, `web_ma/wsgi.py`

역할:

- ASGI/WSGI application 객체를 제공합니다.
- 운영 compose에서는 `gunicorn web_ma.asgi:application -k uvicorn.workers.UvicornWorker`를 사용합니다.

변경 주의:

- ASGI 기준 운영 구조를 깨지 않습니다.
- WSGI는 호환 목적으로 유지합니다.

---

## 4. 전역 URL 기준

### 4.1 `web_ma/urls.py`

주요 라우팅:

| URL | 대상 | name |
|---|---|---|
| `/healthz` | `web_ma.views.healthz` | `healthz` |
| `/login/` | `accounts.views.SessionCloseLoginView` | `login` |
| `/logout/` | Django `LogoutView` | `logout` |
| `/admin/` | `accounts.custom_admin.custom_admin_site.urls` | custom admin |
| `/` | `web_ma.views.landing_view` | `home` |
| `/join/` | `join.urls` | - |
| `/board/` | `board.urls` | - |
| `/commission/` | `commission.urls` | - |
| `/dash/` | `dash.urls` | - |
| `/partner/` | `partner.urls` namespace `partner` | - |
| `/manual/` | `manual.urls` | - |
| `/accounts/` | `accounts.urls` namespace `accounts` | - |

500 handler:

```python
handler500 = "web_ma.views.handler500"
```

중요 원칙:

- `web_ma/urls.py`에서 `/media/`를 직접 서빙하지 않습니다.
- DEBUG 환경에서도 `/media/` 직접 서빙 금지 원칙을 유지합니다.
- 파일 접근은 앱별 보호 view에서 권한 검증 후 처리합니다.

강제 비밀번호 변경 whitelist URL name:

```text
login
logout
accounts:password_change
accounts:password_change_done
```

---

## 5. 전역 View 기준

### 5.1 `web_ma/views.py`

| 함수 | 역할 | 주의 |
|---|---|---|
| `healthz(request)` | Django 컨테이너 healthcheck | body는 `ok` 기준 유지 |
| `handler500(request)` | 운영 500 traceback 강제 로깅 | 사용자에게 traceback 노출 금지 |
| `landing_view(request)` | 인증 사용자 redirect / 미인증 랜딩 렌더 | `ensure_csrf_cookie`, `never_cache` 유지 |

### 5.2 `healthz`

운영 compose의 `web` healthcheck가 이 endpoint를 사용합니다.

기대 응답:

```text
HTTP 200
ok
```

### 5.3 `handler500`

기준:

- `logger.exception("Unhandled server error (500)")`로 traceback을 남깁니다.
- 응답은 `Server Error (500)` 수준으로 제한합니다.

### 5.4 `landing_view`

기준 흐름:

- 인증 사용자: `board:industry_info`로 redirect
- 미인증 사용자: `landing/index.html` 렌더
- context: `next_url = reverse("board:industry_info")`

---

## 6. Settings 운영 기준

### 6.1 `web_ma/settings.py` 역할

`settings.py`는 다음 설정의 SSOT입니다.

- APP_ENV/ENV_FILE 기반 env 선택
- DEBUG fail-fast
- ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS
- INSTALLED_APPS / MIDDLEWARE
- DATABASE_URL 단일화
- CustomUser 모델 지정
- 강제 비밀번호 변경 정책
- static/media 경로
- session/cookie 보안
- Redis/Celery
- 업로드 경로/제한
- board rate limit 정책
- logging
- reverse proxy / SSL
- security headers / CSP
- dash model dir
- 외부 API key

### 6.2 환경 선택 함수

| 함수 | 역할 |
|---|---|
| `_read_app_env()` | `APP_ENV` 우선, 없으면 `ENV`, 없으면 `dev` |
| `_resolve_env_path(base_dir, app_env)` | `ENV_FILE` 우선, 아니면 prod/dev 기본 env 선택 |
| `_bool_from_env(key)` | decouple bool 파서 wrapper |

기본 env:

| APP_ENV | env 파일 |
|---|---|
| `prod`, `production` | `<BASE_DIR>/docker/.env.prod` |
| 그 외 | `<BASE_DIR>/.env.dev` |

### 6.3 DEBUG fail-fast

반드시 유지해야 하는 방어선입니다.

- prod에서 `DEBUG=True`면 RuntimeError
- dev + runserver에서 `DEBUG=False`면 RuntimeError
- dev에서 DB host가 `db`면 RuntimeError
- DEBUG 환경에서 운영 DB 키워드가 DATABASE_URL에 있으면 RuntimeError

이 방어선은 운영 사고 방지용이므로 임시로 제거하지 않습니다.

### 6.4 DATABASE 기준

SSOT:

```python
DATABASE_URL = config("DATABASE_URL")
DATABASES["default"] = dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=False)
DATABASES["default"]["OPTIONS"].update({"client_encoding": "UTF8"})
```

원칙:

- `DATABASE_URL` 단일화 유지
- Windows/한글 환경을 고려한 UTF-8 강제 유지
- dev/prod DB 오접속 방어 유지

### 6.5 Static / Media 기준

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

- `MEDIA_URL`은 저장 위치 개념이지 공개 URL 정책이 아닙니다.
- Nginx에서 `/media/`는 403입니다.
- 다운로드는 보호 view를 경유합니다.

### 6.6 Session / Cookie

운영 기준:

- `SESSION_ENGINE = "django.contrib.sessions.backends.db"`
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`
- `SESSION_COOKIE_AGE = 3600`
- `SESSION_SAVE_EVERY_REQUEST = True`
- `SESSION_COOKIE_HTTPONLY = True`
- `CSRF_COOKIE_HTTPONLY = False`
- prod에서 `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`
- prod에서 cookie domain `.ma-support.kr`
- `SESSION_COOKIE_SAMESITE = "Lax"`
- `CSRF_COOKIE_SAMESITE = "Lax"`

로그인/CSRF 장애 분석 시 함께 확인할 파일:

- `web_ma/middleware.py`
- `accounts/views.py`
- `templates/landing/index.html`
- `static/js/landing/index.js`

### 6.7 Force Password Change 설정

주요 설정:

| 설정 | 역할 |
|---|---|
| `FORCE_PASSWORD_CHANGE_ENABLED` | 전역 ON/OFF |
| `FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES` | URL name whitelist |
| `FORCE_PASSWORD_CHANGE_SCOPE_BRANCHES` | allow branch |
| `FORCE_PASSWORD_CHANGE_SCOPE_PARTS` | allow part |
| `FORCE_PASSWORD_CHANGE_SCOPE_CHANNELS` | allow channel |
| `FORCE_PASSWORD_CHANGE_DENY_BRANCHES` | deny branch |
| `FORCE_PASSWORD_CHANGE_DENY_PARTS` | deny part |
| `FORCE_PASSWORD_CHANGE_DENY_CHANNELS` | deny channel |
| `FORCE_PASSWORD_CHANGE_EXEMPT_GRADES` | 예외 grade |

정책 구현 위치:

- `accounts/policies/password_policy.py`
- `accounts/middleware/force_password_change.py`
- `accounts/views.py`의 `SessionCloseLoginView.form_valid()`

### 6.8 Redis / Celery

주요 설정:

- `REDIS_URL`
- `CACHES["default"]`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP=True`
- `CELERY_TASK_ACKS_LATE=True`
- `CELERY_TASK_REJECT_ON_WORKER_LOST=True`
- `CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS=True`
- `CELERY_WORKER_PREFETCH_MULTIPLIER=1`
- `CELERY_TASK_TIME_LIMIT=30분`
- `CELERY_TASK_SOFT_TIME_LIMIT=25분`

운영 전제:

- at-least-once 실행 가능성이 있으므로 task는 idempotent하게 작성합니다.
- 대량 DB 변경은 transaction, unique key, select_for_update, update_or_create 등을 사용합니다.

### 6.9 Upload dirs / limits

주요 설정:

- `DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000`
- `UPLOAD_RESULT_DIR`
- `UPLOAD_TEMP_DIR`
- `BOARD_ATTACHMENT_MAX_UPLOAD_SIZE`
- `BOARD_ATTACHMENT_ALLOWED_EXTENSIONS`

원칙:

- 업로드 파일은 서버단 크기/확장자/MIME 검증을 갖춰야 합니다.
- 임시파일/결과파일 정리 정책은 별도 운영 점검 대상입니다.

### 6.10 Logging

로그 디렉터리:

```text
<BASE_DIR>/logs/
```

핸들러:

| Handler | 파일 | 용도 |
|---|---|---|
| `console` | stdout/stderr | 컨테이너 로그 |
| `access_file` | `logs/access.log` | 접근/보안 로그 |
| `error_file` | `logs/django_error.log` | 에러/traceback |
| `app_file` | `logs/django_app.log` | 앱 로그 |

주요 logger:

- `django.request`
- `django.security`
- `django.security.csrf`
- `accounts.access`
- `commission`
- `partner`
- `dash`
- `audit`
- `web_ma.celery`
- `celery`
- root ERROR fallback

원칙:

- 500 traceback이 누락되면 안 됩니다.
- 민감정보는 로그에 직접 남기지 않습니다.

### 6.11 Reverse proxy / SSL

주요 설정:

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
```

Cloudflare + Nginx TLS termination 전제입니다.

### 6.12 Security headers

SSOT:

- `web_ma/settings.py`
- `web_ma/middleware.py`의 `SecurityHeadersMiddleware`

주요 항목:

- `SECURE_SSL_REDIRECT`
- `SECURE_HSTS_SECONDS`
- `SECURE_HSTS_INCLUDE_SUBDOMAINS`
- `SECURE_HSTS_PRELOAD`
- `SECURE_CONTENT_TYPE_NOSNIFF`
- `X_FRAME_OPTIONS="DENY"`
- `SECURE_REFERRER_POLICY="same-origin"`
- `SECURE_CROSS_ORIGIN_OPENER_POLICY="same-origin"`
- `PERMISSIONS_POLICY`
- `CONTENT_SECURITY_POLICY`
- `CSP_REPORT_ONLY`

주의:

- CSP는 현재 inline script/style 이력 때문에 즉시 strict 모드로 전환하지 않습니다.
- 강화 시 `CSP_REPORT_ONLY=True`로 먼저 검증합니다.

---

## 7. Middleware 기준

### 7.1 `web_ma/middleware.py`

| 클래스 | 역할 |
|---|---|
| `SecurityHeadersMiddleware` | CSP, Referrer, Permissions, COOP, XFO 헤더 보강 |
| `ForceCSRFCookieOnLoginMiddleware` | `/login/`, `/admin/login/` GET 시 CSRF 쿠키 강제 발급 및 no-store |
| `CleanupLegacyCSRFCookieMiddleware` | 운영 도메인에서 중복 csrftoken 정리 |

### 7.2 Middleware 순서

기준 순서:

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

- `ForcePasswordChangeMiddleware`는 `request.user`가 필요하므로 AuthenticationMiddleware 이후여야 합니다.
- CSRF 관련 미들웨어 위치 변경은 로그인/랜딩 AJAX에 영향을 줄 수 있습니다.

---

## 8. Celery 기준

### 8.1 `web_ma/celery.py`

역할:

- Celery app 생성
- Django settings 로드
- app task autodiscover
- `board.tasks` 패키지 명시 autodiscover
- beat schedule SSOT

주요 함수:

| 함수 | 역할 |
|---|---|
| `_safe_args(value, default=())` | beat args 안전 변환 |
| `debug_task(self)` | 디버그 task |

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

### 9.1 Docker services

| 서비스 | 역할 |
|---|---|
| `db` | PostgreSQL 16 alpine |
| `redis` | Redis |
| `web` | Django ASGI + Gunicorn/Uvicorn |
| `celery` | Celery worker |
| `celery-beat` | Celery beat |
| `nginx` | TLS termination + reverse proxy |

### 9.2 Volumes

| volume/mount | 역할 |
|---|---|
| `pgdata` | DB 데이터 |
| `media_data:/app/media` | 업로드 파일 공유 |
| `../var:/app/var` | dash model 등 운영 artifact |
| `./ops/nginx/default.conf` | Nginx 설정 |
| `./ops/certs` | TLS 인증서 |
| `./ops/maintenance/maintenance.html` | 장애 fallback |

### 9.3 Web command

```bash
gunicorn web_ma.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --log-level info \
  --access-logfile - \
  --error-logfile - \
  --capture-output
```

### 9.4 Nginx 기준

핵심 정책:

- default server는 unknown host를 `444`로 drop
- HTTP `ma-support.kr`는 HTTPS redirect
- `/nginx-healthz`는 Nginx 자체 healthcheck
- `/media/`는 403
- `/static/`은 30일 immutable cache
- dotfile 차단
- reverse proxy는 `web:8000`
- 502/503/504는 internal maintenance page

중요 block:

```nginx
location ^~ /media/ {
    access_log off;
    return 403;
}
```

금지:

- `/media/` alias/root 직접 서빙
- Django 첨부 `.file.url` 직접 노출

---

## 10. Template / UI 기준

### 10.1 `templates/base.html`

역할:

- 인증 후 공통 layout
- Navbar / 모바일 offcanvas
- 권한별 메뉴 노출
- privacy watermark
- core CSS/JS 로드
- app별 CSS/JS block 제공

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

메뉴 권한 노출:

| 메뉴 | 노출 기준 |
|---|---|
| 대시보드 | `superuser`, `head` |
| 업무지원 | `grade != inactive` |
| 조직관리 | `superuser`, `head`, `leader`, `basic` 일부 |
| 수수료 | `superuser`, `head`, `leader` 일부 |
| 매뉴얼 | `user.is_active` |
| 관리자 | `superuser` |

주의:

- template의 메뉴 숨김은 UX 보조일 뿐입니다.
- 실제 접근 제어는 view/policy/queryset에서 처리해야 합니다.

### 10.2 `templates/no_permission_popup.html`

역할:

- 권한 없음 표준 안내
- `grade_required()` 기본 forbidden template
- custom admin 비권한 접근 안내

### 10.3 `templates/components/search_user_modal.html`

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

검색 API SSOT:

```text
accounts:api_search_user
```

### 10.4 로그인/비밀번호 변경 템플릿

| 파일 | 역할 |
|---|---|
| `registration/login.html` | 일반 로그인 화면 |
| `registration/password_change_form.html` | 비밀번호 변경 |
| `registration/password_change_done.html` | 변경 완료 |

중요 DOM:

| 요소 | 사용처 |
|---|---|
| `#loginForm` | `login_page.js` |
| `#loginBtn` | `login_page.js` |

비밀번호 변경:

- 서버 Form인 `StrictPasswordChangeForm`이 SSOT입니다.
- JS 동일 비밀번호 방지는 UX 보조입니다.

### 10.5 Landing

파일:

- `templates/landing/index.html`
- `static/js/landing/index.js`

역할:

- 미인증 사용자 랜딩
- AJAX 로그인 모달
- section animation
- scroll arrow

AJAX 로그인 endpoint:

```text
POST /login/
```

필수 header:

```text
X-CSRFToken
X-Requested-With: XMLHttpRequest
```

---

## 11. CSS 레이어 기준

### 11.1 `static/css/base.css`

포함 범위:

- design token
- typography
- body layout
- navbar
- button
- form
- card
- loading overlay
- disabled/busy state
- 공통 search hover
- money cell
- dt ellipsis

금지:

- 앱 전용 상세 스타일
- 특정 페이지에만 필요한 id selector
- DataTables plugin button 중복 정의

### 11.2 `static/css/fixes.css`

역할:

- 전역 최소 fix
- 충돌 방어
- 가장 마지막에 로드

현재 기준:

- `#mainSheet { min-width: 0; }`
- `#manage-efficiency #mainTable` fixed layout 방어
- `.privacy-watermark`

주의:

- fixes.css는 임시 잡동사니 파일이 아닙니다.
- 정말 전역이어야 하는 방어만 둡니다.

### 11.3 `static/css/plugins/datatables.css`

역할:

- DataTables 공통 스킨
- filter input
- length select
- thead
- hover
- dt-buttons

주의:

- 일부 페이지는 DataTables 사용을 의도적으로 차단합니다.
- 앱별 DataTables 정책을 이 파일에서 강제하지 않습니다.

---

## 12. 공통 JS 기준

### 12.1 Entry JS

| 파일 | 역할 |
|---|---|
| `admin_user_excel.js` | admin 엑셀 업로드 중복 submit 방지 |
| `login_page.js` | 로그인 중복 submit 방지 + spinner |
| `datatable_config.js` | `.datatable` 자동 초기화 |
| `excel_upload.js` | fetch 기반 Excel 업로드 + 결과 모달 |
| `utils/file_upload_utils.js` | 범용 첨부 파일 추가/삭제/FormData 전송 |
| `landing/index.js` | 랜딩 animation + AJAX 로그인 |

### 12.2 `static/js/common/forms/*`

| 파일 | 함수 | 역할 |
|---|---|---|
| `dom.js` | `qs`, `qsa`, `safeOn`, `show`, `hide` | DOM 공통 유틸 |
| `premium.js` | `bindPremiumInputs()` | 보험료 숫자/콤마 처리 |
| `rows.js` | `initRowController()` | 행 추가/초기화/삭제 |

### 12.3 `static/js/common/manage/*`

| 파일 | 함수 | 역할 |
|---|---|---|
| `csrf.js` | `getCSRFToken()` | CSRF token 추출 |
| `dataset.js` | `ds()`, `getDatasetUrl()` | dataset 접근 |
| `datatables.js` | `canUseDataTables()`, `destroyDataTableIfExists()`, `safeAdjust()` | DataTables 안전 처리 |
| `http.js` | `readJsonOrThrow()`, `isSuccessJson()` | JSON fetch 표준 처리 |
| `loading.js` | `showLoading()`, `hideLoading()` | loading overlay |
| `ym.js` | `pad2()`, `selectedYM()`, `normalizeYM()` | YYYY-MM 유틸 |

### 12.4 JS 표준 패턴

중복 submit 방지:

```js
if (form.dataset.submitting === "1") return;
form.dataset.submitting = "1";
```

중복 초기화 방지:

```js
if (root.dataset.inited === "1") return;
root.dataset.inited = "1";
```

이벤트 중복 바인딩 방지:

```js
if (el.dataset.bound === "1") return;
el.dataset.bound = "1";
```

fetch JSON 처리:

```js
const data = await readJsonOrThrow(res);
if (!isSuccessJson(data)) throw new Error(data.message || "처리 실패");
```

---

## 13. Accounts 앱 기준

### 13.1 역할

Accounts 앱은 다음 핵심 기능을 담당합니다.

- CustomUser 모델
- 사번 문자열 PK 인증
- custom admin 접근 제어
- 계정 잠금 lockout
- 강제 비밀번호 변경
- 사용자 엑셀 업로드 / Celery 처리
- 사용자 검색 API
- leader 변경 시 SubAdminTemp 동기화

### 13.2 `accounts/models.py`

#### `CustomUserManager`

| 함수 | 역할 |
|---|---|
| `create_user(id, password=None, **extra_fields)` | 일반 사용자 생성 |
| `create_superuser(id, password=None, **extra_fields)` | superuser 생성 |

`create_user()` 기준:

- id 필수
- name 필수
- password는 `set_password()` 사용

#### `CustomUser`

PK:

```python
id = models.CharField(max_length=30, unique=True, primary_key=True)
USERNAME_FIELD = "id"
REQUIRED_FIELDS = ["name"]
```

조직 필드:

| 필드 | 의미 |
|---|---|
| `channel` | 부문 |
| `division` | 총괄 |
| `part` | 부서 |
| `branch` | 지점 |

권한 등급:

```text
superuser
head
leader
basic
resign
inactive
```

save hook:

- `grade == inactive`이면 `is_active=False` 강제
- inactive가 아니라고 자동 True 복구는 하지 않음

Lockout 필드:

- `login_fail_count`
- `is_locked`
- `locked_at`
- `last_login_fail_at`
- `lock_reason`
- `lock_cleared_at`
- `lock_cleared_by`
- `password_reset_by_admin_at`

Force password change 필드:

- `must_change_password`
- `must_change_password_set_at`
- `must_change_password_cleared_at`

PASS 본인인증 stub:

- `pass_verified`
- `pass_verified_at`
- `pass_verified_ip`
- `ci_hash`

개인정보 원칙:

- CI 원본 저장 금지
- 전화번호 원본 저장 금지
- 주민번호 저장 금지

### 13.3 `accounts/custom_admin.py`

클래스:

```python
CustomAdminSite(AdminSite)
```

접근 기준:

```python
user.is_authenticated and user.grade == "superuser"
```

역할:

- superuser grade만 admin 접근
- 로그인된 비권한 사용자에게 `no_permission_popup.html`
- admin logout 시 `/` redirect

### 13.4 `accounts/decorators.py`

주요 함수:

| 함수 | 역할 |
|---|---|
| `grade_required(*allowed_grades, forbidden_template="no_permission_popup.html")` | grade 기반 접근 제한 |
| `not_inactive_required(view_func)` | inactive 차단 |

기준:

- `GRADE_ALIAS_MAP = {}`
- 신규 권한은 `head`, `leader` 기준
- legacy `main_admin`, `sub_admin` 신규 사용 금지

### 13.5 `accounts/forms.py`

| 클래스 | 역할 |
|---|---|
| `ExcelUploadForm` | Excel 업로드 form |
| `ActiveOnlyAuthenticationForm` | locked/inactive 로그인 차단 |
| `StrictPasswordChangeForm` | 현재 비밀번호와 동일한 새 비밀번호 차단 |

### 13.6 `accounts/signals.py`

주요 signal:

| signal | 함수 | 역할 |
|---|---|---|
| `pre_save(CustomUser)` | `_capture_old_grade` | 기존 grade 캡처 |
| `post_save(CustomUser)` | `_sync_subadmin_on_grade_change` | leader 변경 시 SubAdminTemp 동기화 |

leader 승격:

- SubAdminTemp 없으면 생성
- 있으면 name/part/branch/grade/level 최소 갱신
- team/position은 덮어쓰지 않음

leader 강등:

- SubAdminTemp 삭제 금지
- grade/level/name/branch/part만 최소 동기화

### 13.7 `accounts/urls.py`

| URL | view | name |
|---|---|---|
| `password-change/` | `password_change_view` | `accounts:password_change` |
| `password-change/done/` | `password_change_done_view` | `accounts:password_change_done` |
| `upload-progress/` | `upload_progress_view` | `accounts:accounts_upload_progress` |
| `upload-result/<task_id>/` | `upload_result_view` | `accounts:accounts_upload_result` |
| `api/search-user/` | `api_search_user` | `accounts:api_search_user` |
| `search-user/` | `search_user` | `accounts:search_user_legacy` |

### 13.8 `accounts/views.py`

주요 구성:

| 구성 | 역할 |
|---|---|
| `csrf_failure` | CSRF 실패 상세 로그 |
| `UserPasswordChangeView` | 비밀번호 변경 + must_change_password 해제 |
| `UserPasswordChangeDoneView` | 완료 화면 |
| `upload_progress_view` | Celery 진행률 JSON |
| `upload_result_view` | 결과 파일 다운로드 |
| `SessionCloseLoginView` | 로그인/lockout/AJAX/default password flag |
| `api_search_user` | 검색 API wrapper |
| `search_user` | legacy alias |

#### `SessionCloseLoginView` 내부 함수

| 함수 | 역할 |
|---|---|
| `_extract_login_id()` | username/id 추출 |
| `_get_submitted_user()` | 제출 ID 기준 사용자 조회 |
| `_build_invalid_login_message()` | 실패 횟수 안내 |
| `_build_locked_message()` | 잠금 메시지 |
| `_replace_non_field_error()` | form error 교체 |
| `_audit_safe()` | audit 실패 방어 |
| `_mark_login_failed()` | select_for_update로 실패 횟수 증가 및 lock |
| `_reset_login_fail_state()` | 로그인 성공 시 실패 상태 초기화 |

로그인 성공 흐름:

1. raw password 확보
2. Django 기본 로그인 처리
3. session browser close 만료 설정
4. 실패 횟수 초기화
5. audit login success
6. raw password가 `id` 또는 `incar{id}`이면 `must_change_password=True`
7. AJAX 요청이면 JSON 반환
8. 일반 요청이면 redirect 반환

로그인 실패 흐름:

1. `invalid_login`일 때만 실패 횟수 누적
2. 5회 도달 시 locked 처리
3. audit fail/locked 기록
4. AJAX 요청이면 401 JSON 반환
5. 일반 요청이면 HTML form error 반환

### 13.9 `accounts/search_api.py`

역할:

- 사용자 검색 API SSOT
- 권한 스코프 적용
- SubAdminTemp 결합
- `affiliation_display` 생성

검색 제한:

```python
RESULT_LIMIT = 50
```

권한별 범위:

| grade | 범위 |
|---|---|
| `superuser` | 전체 또는 선택 branch |
| `head` | 본인 branch |
| `leader` | 본인 branch 또는 SubAdminTemp level/team |
| `basic`, `inactive` | 본인만 |
| 기타 | none |

### 13.10 `accounts/tasks.py`

Celery task:

```python
process_users_excel_task(task_id, file_path, batch_size=500)
```

역할:

- 계정 Excel 업로드 비동기 처리
- 필수 컬럼 포함 visible sheet 자동 선택
- 기존 사용자 업데이트
- 신규 사용자 생성
- 결과 report workbook 생성
- cache 상태/진행률/result_path 기록

정책:

| 항목 | 기준 |
|---|---|
| 신규 초기 비밀번호 | `incar` + 사번 |
| 기존 비밀번호 | 변경 금지 |
| 보호등급 | `superuser`, `head`, `leader` |
| 보호필드 | `position`, `team_a`, `team_b`, `team_c` |
| batch size | 1~2000 clamp |
| 확장자 | `.xlsx`, `.xlsm`, `.xls` |

### 13.11 `accounts/services/users_excel_import.py`

역할:

- 계정 Excel 파싱 SSOT

필수 컬럼:

```text
사원번호
성명
재직여부
소속부서
영업가족명
입사일자(사원)
퇴사일자(사원)
```

주요 함수:

| 함수 | 역할 |
|---|---|
| `normalize_emp_id()` | 사번 정규화 |
| `normalize_part()` | 부서 정규화. `1인GA사업부` → `MA사업4부` |
| `parse_excel_date()` | 날짜 변환 |
| `infer_channel()` | channel 추론 |
| `infer_grade()` | grade 추론 |
| `infer_status()` | status 추론 |
| `pick_worksheet_by_required_cols()` | 필수컬럼 포함 시트 선택 |
| `build_defaults_from_row()` | row → emp_id/name/defaults |

### 13.12 `accounts/policies/password_policy.py`

SSOT 함수:

```python
should_enforce(user, request=None) -> bool
```

True 조건:

- `FORCE_PASSWORD_CHANGE_ENABLED=True`
- 인증 사용자
- `must_change_password=True`
- grade가 exempt 아님
- allow scope에 포함
- deny scope에 포함되지 않음

우선순위:

```text
deny-first
branch > part > channel
```

### 13.13 `accounts/middleware/force_password_change.py`

역할:

- 강제 비밀번호 변경 대상 사용자를 password_change로 redirect

bypass:

- `/static/`
- `/media/`
- `/favicon.ico`
- `/robots.txt`
- resolve 실패 URL
- whitelist URL name

중요:

- 기본 비밀번호 여부는 여기서 판단하지 않습니다.
- 로그인 성공 시 `must_change_password` 플래그로 수렴합니다.

### 13.14 `accounts/admin.py`

역할:

- CustomUserAdmin
- Excel export/upload/template/result
- 업로드 cache 초기화
- Celery task 시작
- lockout 복구 action
- must_change_password 해제 action
- audit log 연계

주요 함수/클래스:

| 항목 | 역할 |
|---|---|
| `_init_upload_cache()` | 진행률 cache 초기화 |
| `_save_uploaded_file_to_disk()` | 업로드 파일 temp 저장 |
| `_file_response_or_404()` | 결과 파일 다운로드 |
| `_build_users_export_workbook()` | 사용자 export workbook 생성 |
| `upload_users_from_excel_view()` | admin upload 시작 |
| `upload_users_result_view()` | 결과 다운로드 |
| `upload_excel_template_view()` | 양식 다운로드 |
| `CustomUserCreationAdminForm` | add form |
| `CustomUserChangeAdminForm` | change form |
| `CustomUserAdmin` | admin 등록 |

관리자 action:

| action | 역할 |
|---|---|
| `reset_password_and_unlock_accounts` | 비밀번호 `incar{id}` 초기화, lock 해제, must_change_password=True |
| `clear_must_change_password` | 강제 변경 플래그 해제 |

주의:

- `GRADE_DISPLAY`에 legacy grade가 남아 있을 수 있습니다.
- 관리자 메시지에 legacy `main_admin` 문구가 남아 있을 수 있습니다.
- 이는 향후 코드정리 후보입니다.

---

## 14. Audit 앱 기준

### 14.1 역할

Audit 앱은 다음 두 로그 체계를 제공합니다.

| 모델 | 역할 |
|---|---|
| `RequestLog` | 모든 요청/응답 단위 로그 |
| `AuditLog` | 의미 있는 행위 이벤트 로그 |

### 14.2 `audit/models.py`

#### RequestLog

DB table:

```text
audit_request_log
```

저장 항목:

- ts
- user
- is_authenticated
- method
- path
- querystring
- status_code
- duration_ms
- ip
- user_agent
- referer
- request_id
- session_key

원칙:

- body 저장 금지
- querystring은 마스킹 후 저장

#### AuditLog

DB table:

```text
audit_audit_log
```

저장 항목:

- ts
- action
- user
- ip
- success
- reason
- object_type
- object_id
- meta
- request_id

### 14.3 `audit/constants.py`

클래스:

```python
class ACTION:
    ...
```

역할:

- action string SSOT
- 신규 이벤트는 여기에 상수로 추가합니다.

카테고리:

- Auth
- Board
- Manual
- Partner
- Commission
- Accounts
- Support
- Collect
- Retention
- Partner esign

### 14.4 `audit/middleware.py`

클래스:

```python
RequestLogMiddleware
```

역할:

- request 시작 시 `_audit_start`, `audit_request_id` 설정
- response 시 RequestLog 저장
- 로깅 실패가 서비스 장애로 이어지지 않도록 예외 무시

### 14.5 `audit/services.py`

주요 함수:

```python
log_action(request, action, obj=None, object_type="", object_id="", meta=None, success=True, reason="")
```

역할:

- 중요 행위 기록
- request user/ip/request_id 연결
- obj 기반 object_type/object_id 자동 설정
- meta 마스킹/깊이 제한/개수 제한

제한:

```text
MAX_META_DEPTH = 2
MAX_META_ITEMS = 30
```

### 14.6 `audit/utils.py`

주요 함수:

| 함수 | 역할 |
|---|---|
| `mask_value()` | 전화번호/주민번호/긴 문자열 마스킹 |
| `mask_querystring()` | querystring 민감키 마스킹 |
| `get_client_ip()` | X-Forwarded-For, X-Real-IP, REMOTE_ADDR 순 IP 추출 |

민감키:

```text
password, passwd, pwd, token, access_token, refresh_token,
authorization, auth, api_key, ssn, resident, resident_no,
jumin, 주민번호, session, sessionid, csrftoken
```

---

## 15. 권한 지침

### 15.1 신규 grade 기준

| grade | 의미 |
|---|---|
| `superuser` | 전체 관리자 |
| `head` | 부서/지점 책임자급 |
| `leader` | 팀 리더급 |
| `basic` | 일반 사용자 |
| `resign` | 퇴사자 |
| `inactive` | 비활성 사용자 |

Legacy:

| legacy | 신규 기준 |
|---|---|
| `main_admin` | `head` |
| `sub_admin` | `leader` |

신규 코드에서 legacy grade로 권한 판단하지 않습니다.

### 15.2 권한 검증 우선순위

1. View decorator / class dispatch
2. Policy function
3. Queryset scope 제한
4. Object-level permission
5. Template menu visibility

Template menu visibility는 보안 수단이 아닙니다.

### 15.3 파일 권한

파일 접근은 다음 순서를 따릅니다.

1. 로그인 확인
2. grade/scope 확인
3. object 소유/branch/team 범위 확인
4. 파일 존재 확인
5. `FileResponse`
6. audit log 기록

---

## 16. 보안 점검 체크리스트

### 16.1 인증/인가

- [ ] 모든 내부 view/API가 인증 보호를 갖는가?
- [ ] 권한은 template가 아니라 서버에서 검증하는가?
- [ ] queryset이 사용자 scope로 제한되는가?
- [ ] object-level permission이 필요한 곳에 적용되었는가?
- [ ] legacy grade가 신규 권한 판단에 사용되지 않는가?

### 16.2 CSRF

- [ ] AJAX POST에 `X-CSRFToken`이 있는가?
- [ ] 로그인 페이지에서 csrftoken이 발급되는가?
- [ ] CSRF 실패 시 로그가 충분히 남는가?
- [ ] 중복 csrftoken 이슈를 고려했는가?

### 16.3 파일

- [ ] `.file.url` 직접 노출이 없는가?
- [ ] `/media/` 직접 접근이 403인가?
- [ ] 다운로드 view가 권한 검증을 수행하는가?
- [ ] 업로드 확장자/크기/MIME 검증이 있는가?
- [ ] 다운로드/업로드가 audit 대상인가?

### 16.4 로그/감사

- [ ] 중요 행위에 `log_action()`이 있는가?
- [ ] meta에 민감정보가 들어가지 않는가?
- [ ] request body를 저장하지 않는가?
- [ ] querystring이 마스킹되는가?
- [ ] 500 traceback이 남는가?

### 16.5 보안 헤더

- [ ] `SecurityHeadersMiddleware`가 유지되는가?
- [ ] CSP 강화 시 Report-Only 검증을 거쳤는가?
- [ ] `X_FRAME_OPTIONS="DENY"`인가?
- [ ] 운영에서 HTTPS redirect/HSTS가 적절한가?

---

## 17. 성능개선 점검 기준

### 17.1 Backend / DB

- [ ] N+1 query가 있는가?
- [ ] `select_related`, `prefetch_related` 적용 가능한가?
- [ ] row-by-row save를 bulk 처리로 바꿀 수 있는가?
- [ ] 대량 작업에 적절한 transaction 범위가 있는가?
- [ ] 경쟁 조건이 있으면 `select_for_update()`가 필요한가?
- [ ] 인덱스가 조회 패턴과 맞는가?

### 17.2 Celery

- [ ] task가 idempotent한가?
- [ ] connection loss 후 재전달에 안전한가?
- [ ] batch size가 적절한가?
- [ ] temp/result 파일 cleanup이 필요한가?
- [ ] 진행률 cache timeout이 적절한가?

### 17.3 Frontend

- [ ] 이벤트 중복 바인딩이 없는가?
- [ ] BFCache 재진입에 안전한가?
- [ ] fetch JSON 처리가 공통 유틸을 쓰는가?
- [ ] DataTables destroy/reinit 비용이 과도하지 않은가?
- [ ] document delegation 범위가 과도하지 않은가?

### 17.4 CSS

- [ ] 앱 전용 CSS가 `base.css`나 `fixes.css`로 새지 않았는가?
- [ ] 전역 id selector가 다른 앱에 영향을 주지 않는가?
- [ ] `!important`가 불필요하게 늘지 않았는가?
- [ ] DataTables 스타일이 중복 정의되지 않았는가?

---

## 18. 패치 응답 시 표준 산출물

CORE INFRA 관련 패치 요청 시 다음 형식을 사용합니다.

### 18.1 변경 목적

- 1~2줄 요약

### 18.2 수정 파일 목록 + 영향도

| 파일 | 변경 내용 | 영향도 |
|---|---|---|
| 예: `web_ma/settings.py` | 보안 헤더 조정 | 운영 전체 영향 |

### 18.3 회귀 위험 체크

- [ ] 권한 스코프 변경 여부
- [ ] URL name/reverse 변경 여부
- [ ] template DOM id/dataset 변경 여부
- [ ] 파일 다운로드 정책 위반 여부
- [ ] upload/cache/task contract 변경 여부
- [ ] DataTables 정책 영향 여부
- [ ] CSS 전역 누수 여부
- [ ] 운영 설정 영향 여부

### 18.4 diff patch

- 반드시 unified diff 형식 사용
- 기능 변화 0 요청이면 동작 동일 보장 포인트 명시

### 18.5 로컬 검증

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
```

필요 시:

```bash
celery -A web_ma inspect registered
```

### 18.6 운영 유사 검증

- [ ] `/healthz` 정상
- [ ] `/nginx-healthz` 정상
- [ ] 로그인/로그아웃 정상
- [ ] CSRF 실패 로그 정상
- [ ] static 파일 200/304
- [ ] `/media/` 직접 접근 403
- [ ] 업로드 진행률 polling 정상
- [ ] 결과 파일 다운로드 권한 정상
- [ ] celery/beat 로그 정상

---

## 19. 금지 패턴

- [ ] `/media/` 직접 서빙 허용
- [ ] `.file.url` 직접 링크
- [ ] DEBUG=True로 운영 장애 임시 해결
- [ ] custom admin 권한을 `is_superuser`만으로 완화
- [ ] CSRF exempt 남용
- [ ] DB 연결 정보를 settings에 분산 하드코딩
- [ ] base.css/fixes.css에 앱 전용 스타일 추가
- [ ] Celery beat task명을 실제 등록명과 다르게 작성
- [ ] legacy `main_admin/sub_admin`을 신규 권한 판단에 사용
- [ ] audit meta에 password/token/주민번호/전화번호 원문 저장

---

## 20. 빠른 위치 참조표

| 찾고 싶은 것 | 파일 | 함수/클래스 |
|---|---|---|
| 전역 URL | `web_ma/urls.py` | `urlpatterns` |
| 랜딩 view | `web_ma/views.py` | `landing_view` |
| healthcheck | `web_ma/views.py` | `healthz` |
| 500 handler | `web_ma/views.py` | `handler500` |
| 보안 헤더 | `web_ma/middleware.py` | `SecurityHeadersMiddleware` |
| 로그인 CSRF 쿠키 | `web_ma/middleware.py` | `ForceCSRFCookieOnLoginMiddleware` |
| legacy CSRF 쿠키 정리 | `web_ma/middleware.py` | `CleanupLegacyCSRFCookieMiddleware` |
| Celery schedule | `web_ma/celery.py` | `app.conf.beat_schedule` |
| CustomUser | `accounts/models.py` | `CustomUser` |
| Custom admin | `accounts/custom_admin.py` | `CustomAdminSite` |
| 로그인 처리 | `accounts/views.py` | `SessionCloseLoginView` |
| 계정 잠금 | `accounts/views.py` | `_mark_login_failed()` |
| 비번 강제 변경 middleware | `accounts/middleware/force_password_change.py` | `ForcePasswordChangeMiddleware` |
| 비번 정책 | `accounts/policies/password_policy.py` | `should_enforce()` |
| 사용자 검색 | `accounts/search_api.py` | `search_users_for_api()` |
| 계정 Excel task | `accounts/tasks.py` | `process_users_excel_task()` |
| Excel 파싱 | `accounts/services/users_excel_import.py` | `build_defaults_from_row()` |
| 요청 로그 | `audit/middleware.py` | `RequestLogMiddleware` |
| 액션 로그 | `audit/services.py` | `log_action()` |
| 액션 상수 | `audit/constants.py` | `ACTION` |
| 마스킹 | `audit/utils.py` | `mask_value()`, `mask_querystring()` |
| 공통 layout | `templates/base.html` | blocks/menu |
| 공통 CSS | `static/css/base.css` | token/component/utility |
| 전역 fix | `static/css/fixes.css` | minimal fix |
| DataTables CSS | `static/css/plugins/datatables.css` | plugin skin |
| fetch JSON | `static/js/common/manage/http.js` | `readJsonOrThrow()` |
| JS CSRF | `static/js/common/manage/csrf.js` | `getCSRFToken()` |
| dataset helper | `static/js/common/manage/dataset.js` | `ds()`, `getDatasetUrl()` |
| 파일 업로드 JS | `static/js/utils/file_upload_utils.js` | `initFileUpload()` |

---

## 21. 운영 점검 명령 모음

### Django

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
```

### Docker

```bash
docker compose ps
docker compose logs -f web
docker compose logs -f celery
docker compose logs -f celery-beat
docker compose logs -f nginx
```

### Celery

```bash
celery -A web_ma inspect registered
```

### Healthcheck

```bash
curl -i https://ma-support.kr/healthz
curl -i http://127.0.0.1/nginx-healthz
```

### Media 차단 확인

```bash
curl -i https://ma-support.kr/media/test.txt
```

기대:

```text
403 Forbidden
```

---

## 22. 향후 개선 검토 후보

이 문서는 패치를 수행하지 않지만, 향후 보안/성능 점검 시 다음 항목을 우선 검토할 수 있습니다.

- CSP strict 전환 가능성
- legacy grade 문구/상수 잔재 정리
- admin export 파일명 RFC5987 한글 대응
- upload temp/result cleanup 정책
- RequestLog 보존 기간/파티셔닝/정리 배치
- Celery task idempotency 전수 점검
- DataTables 자동 초기화와 앱별 정책 충돌 여부
- inline script/style 축소
- static vendor version 일관성
- audit meta 민감정보 유입 가능성
- `/logs`와 컨테이너 stdout 로그 운영 이중화 기준

---

## 23. 이후 피드백 기본 전제

앞으로 CORE INFRA 관련 요청이 들어오면 다음 전제를 기본으로 판단합니다.

1. settings SSOT는 `web_ma.settings`입니다.
2. 운영은 Docker Compose + Nginx + Gunicorn/Uvicorn + Redis + Celery + PostgreSQL입니다.
3. `/media/` 직접 접근은 금지입니다.
4. 파일 다운로드는 보호 view + 권한 검증 + FileResponse가 원칙입니다.
5. 권한 등급은 `superuser/head/leader/basic/resign/inactive`입니다.
6. `main_admin/sub_admin`은 legacy 잔재입니다.
7. 로그인 잠금, 강제 비밀번호 변경, audit log는 accounts/audit 인프라의 핵심 축입니다.
8. 프론트는 dataset boot, safe binding, CSRF utility, `readJsonOrThrow`, duplicate submit guard를 기본 패턴으로 합니다.
9. CSS는 base/plugins/fixes/apps 레이어를 유지합니다.
10. 패치는 기능 변화 범위를 최소화하고 diff로 제시합니다.
