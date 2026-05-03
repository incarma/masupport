# Infra / 배포 가이드

> **대상 독자**: 배포 담당자, 새 기능에서 Celery task·설정을 건드리는 개발자 (LLM 포함)
> **SSOT 파일**: `web_ma/settings.py`, `web_ma/celery.py`, `docker-compose.yaml`

---

## 1. 환경 분리 구조 (dev / prod)

### 1-1. IS_PROD 판단 기준

```python
# settings.py (SSOT)
APP_ENV = _read_app_env()          # 환경변수 APP_ENV → ENV → 기본값 "dev"
IS_PROD = APP_ENV in ("prod", "production") and not DEBUG
```

`IS_PROD`는 **단일 Boolean 게이트**다. `APP_ENV`가 `prod`/`production`이고 동시에 `DEBUG=False`일 때만 `True`가 된다. 이 값이 `True`이어야 아래 설정들이 활성화된다.

| 조건 | IS_PROD |
|---|---|
| `APP_ENV=dev` (기본) | `False` |
| `APP_ENV=prod` + `DEBUG=True` | `RuntimeError` (즉시 중단) |
| `APP_ENV=prod` + `DEBUG=False` | `True` |

### 1-2. 환경 파일 경로 (자동 선택)

| APP_ENV | 로드되는 .env 파일 |
|---|---|
| `dev` (기본) | `<BASE_DIR>/.env.dev` |
| `prod` / `production` | `<BASE_DIR>/docker/.env.prod` |
| `ENV_FILE` 환경변수 지정 시 | 해당 경로 (절대 or BASE_DIR 상대) |

### 1-3. 환경별 활성화 설정 목록

| 설정 | dev | prod (IS_PROD=True) |
|---|---|---|
| `DEBUG` | `True` | `False` (강제) |
| `STATICFILES_STORAGE` | 미설정 (기본 파일 서빙) | `CompressedManifestStaticFilesStorage` |
| `CACHES` | `LocMemCache` (프로세스 인메모리) | `RedisCache` (REDIS_URL) |
| `SESSION_COOKIE_SECURE` | `False` | `True` |
| `CSRF_COOKIE_SECURE` | `False` | `True` |
| `SESSION_COOKIE_DOMAIN` | 미설정 | `.ma-support.kr` |
| `CSRF_COOKIE_DOMAIN` | 미설정 | `.ma-support.kr` |
| `SECURE_SSL_REDIRECT` | `False` | `True` |
| `SECURE_HSTS_SECONDS` | `0` | `2592000` (30일) |
| CSP `upgrade-insecure-requests` | 미포함 | 자동 추가 |
| `AUDIT_PROXY_HEADER_ENABLED` | `False` | `True` |

### 1-4. Fail-fast Safety Rails (의도적 RuntimeError)

아래 상황에서는 Django가 **즉시 RuntimeError를 발생**시켜 기동을 중단한다.

```
APP_ENV=prod  + DEBUG=True         → "prod에서 DEBUG=True 허용 안 됨"
APP_ENV=dev   + runserver + DEBUG=False → "개발에서 DEBUG=False 차단"
APP_ENV=dev   + DATABASE HOST=db   → "dev에서 docker DB 연결 차단"
DEBUG=True    + DATABASE_URL에 django_ma_prod/ma_prod 포함 → "개발에서 운영 DB 차단"
```

이 rails는 설정 실수로 인한 **운영 DB 오염 및 정적파일 UI 붕괴**를 방지하기 위한 것이다. 에러가 발생하면 bypass하지 말고 .env 파일과 APP_ENV를 점검한다.

---

## 2. 정적파일 정책

### 2-1. WhiteNoise Manifest 동작 원리

| 환경 | 스토리지 | 동작 |
|---|---|---|
| `IS_PROD=False` | Django 기본 | 파일을 STATICFILES_DIRS에서 직접 서빙. 해시 없음. |
| `IS_PROD=True` | `CompressedManifestStaticFilesStorage` | `collectstatic` 실행 시 각 파일에 콘텐츠 해시를 붙여 `staticfiles/` 에 복사. `staticfiles.json` manifest 생성. |

`CompressedManifestStaticFilesStorage`는 빌드 시점에 `staticfiles.json`을 생성하고, 런타임에는 이 manifest를 읽어 해시가 붙은 URL로 응답한다. **manifest 파일이 없으면 서버 기동 시 `ValueError: Missing staticfiles.json manifest file` 오류가 발생한다.**

### 2-2. collectstatic 시점/명령어

```bash
# 배포 직전 반드시 실행 (코드 변경 후 매번)
python manage.py collectstatic --noinput
```

- 결과물 위치: `<BASE_DIR>/staticfiles/`
- Docker 배포 시 `build.sh` 또는 `Dockerfile`의 빌드 단계에서 실행되어야 한다.
- `web` 컨테이너 볼륨(`.:/app`)으로 호스트 디렉터리를 마운트하므로, 호스트에서 `collectstatic`을 실행한 결과물이 컨테이너에 그대로 반영된다.

### 2-3. "캐시 무시로 임시 해결" 금지 이유

WhiteNoise Manifest 모드에서 파일을 수정하고 `collectstatic`을 실행하지 않으면:
- 브라우저에 캐시된 **구 해시 URL**이 남아 있고,
- manifest에는 **새 해시 URL**만 존재하므로,
- 서버는 구 URL 요청에 대해 `500 ValueError`를 반환한다.

이때 `Cache-Control: no-cache` 헤더를 추가하거나 `STATICFILES_STORAGE`를 변경하는 임시 해결책은 **manifest 불일치를 숨길 뿐 근본 원인을 해결하지 않는다.** 반드시 `collectstatic`을 다시 실행해야 한다.

### 2-4. 경로 요약

```
BASE_DIR/
├── static/                  ← STATICFILES_DIRS (소스)
├── staticfiles/             ← STATIC_ROOT (collectstatic 결과물, .gitignore 대상)
│   └── staticfiles.json     ← manifest (IS_PROD 필수)
├── media/                   ← MEDIA_ROOT (업로드 파일)
│   ├── upload_results/      ← UPLOAD_RESULT_DIR
│   └── upload_temp/         ← UPLOAD_TEMP_DIR
```

---

## 3. Celery / Redis 운영 규약

### 3-1. beat_schedule 등록 위치 (SSOT)

**`web_ma/celery.py`의 `app.conf.beat_schedule`이 유일한 정의 위치다.**

```python
# celery.py beat_schedule 현황
"board-industry-news-collect"   # 6시간 주기 (00:05/06:05/12:05/18:05)
"board-industry-cleanup-daily"  # 매일 03:00 (14일 이전 기사 삭제)
"dash-agg-hourly"               # 매시 :10
"dash-forecast-daily"           # 매일 02:10
"dash-forecast-hourly"          # 매시 :20
"generate-monthly-worktasks"    # 매월 1일 00:10
"notify-due-worktasks"          # 매일 08:00
```

### 3-2. task name 등록 규약

`beat_schedule`의 `"task"` 값은 `@shared_task(name=...)` 으로 등록한 이름과 **정확히 일치**해야 한다. 불일치 시 에러 없이 묵묵히 실행되지 않는다.

```python
# tasks.py (예시)
@shared_task(name="board.tasks.generate_monthly_worktasks")
def generate_monthly_worktasks(): ...

# celery.py beat_schedule — 위 name과 반드시 일치
"generate-monthly-worktasks": {
    "task": "board.tasks.generate_monthly_worktasks",  # ← SSOT
    ...
}
```

**등록 확인 명령:**
```bash
celery -A web_ma inspect registered
```

### 3-3. board/tasks/ 패키지 주의사항

`board/tasks/`는 패키지(디렉터리) 구조이므로 `autodiscover_tasks()` 단독으로는 탐색되지 않는다.

```python
# celery.py — 이 두 줄이 모두 필요
app.autodiscover_tasks()                    # INSTALLED_APPS 기반
app.autodiscover_tasks(["board.tasks"])     # board 패키지 명시 추가
```

board에 새 task 파일을 추가할 때 이 호출이 없으면 워커가 task를 인식하지 못한다.

### 3-4. 진행률 cache 계약 (percent / status / error / download_url)

Celery task가 진행 상황을 프론트엔드에 알릴 때 아래 키 구조로 Django cache에 기록한다.

```python
# task 내부 (규약)
from django.core.cache import cache

cache.set(f"task_progress_{task_id}", {
    "percent": 40,                   # 0~100 정수
    "status": "processing",          # "pending" | "processing" | "done" | "error"
    "error": "",                     # 오류 메시지 (status="error"일 때)
    "download_url": "",              # 완료 후 다운로드 URL (status="done"일 때)
}, timeout=3600)
```

**dev/prod 차이**: dev는 `LocMemCache`(프로세스 인메모리)를 사용하므로 **Celery worker 프로세스와 Django 웹 프로세스가 서로 다른 캐시를 본다**. 진행률 폴링이 dev에서 동작하지 않는 것은 이 때문이다. 진행률 기능은 prod(RedisCache)에서만 정상 동작한다.

### 3-5. ACK/재시도 정책

```python
CELERY_TASK_ACKS_LATE = True              # task 완료 후 ACK (at-least-once)
CELERY_TASK_REJECT_ON_WORKER_LOST = True  # worker 죽으면 메시지 재큐
CELERY_WORKER_PREFETCH_MULTIPLIER = 1     # 동시 선점 방지
CELERY_TASK_TIME_LIMIT = 1800             # hard limit: 30분
CELERY_TASK_SOFT_TIME_LIMIT = 1500        # soft limit: 25분
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 3600,           # 1시간 (장기 task 중복 방지)
}
```

`TASK_ACKS_LATE=True`는 worker가 재시작될 때 task가 **최소 1회** 재실행될 수 있음을 의미한다. 따라서 모든 Celery task는 반드시 **idempotent(멱등)** 하게 설계되어야 한다 (`update_or_create`, unique key, 분산 락 등 활용).

### 3-6. Redis 연결 실패 복구

```python
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 100
CELERY_BROKER_CONNECTION_TIMEOUT = 30
```

Redis 재시작이나 순간 단절 시 worker가 자동으로 재연결을 시도한다. 컨테이너 재시작 순서는 `db → redis → web/celery/celery-beat` 순으로 healthcheck가 보장한다.

---

## 4. 세션 / 쿠키 보안 설정

### 4-1. 전 환경 공통 설정

```python
SESSION_ENGINE              = "django.contrib.sessions.backends.db"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE          = 3600   # 1시간 (브라우저 오픈 중에도 만료)
SESSION_SAVE_EVERY_REQUEST  = True   # 매 요청마다 만료 시간 갱신
SESSION_COOKIE_HTTPONLY     = True   # JS 접근 차단
CSRF_COOKIE_HTTPONLY        = False  # JS에서 csrfToken을 읽어야 하므로 False 유지
SESSION_COOKIE_SAMESITE     = "Lax"
CSRF_COOKIE_SAMESITE        = "Lax"
```

### 4-2. prod 전용 추가 설정 (IS_PROD=True일 때만 활성화)

```python
SESSION_COOKIE_SECURE  = True           # HTTPS only
CSRF_COOKIE_SECURE     = True           # HTTPS only
SESSION_COOKIE_DOMAIN  = ".ma-support.kr"  # 서브도메인 공유
CSRF_COOKIE_DOMAIN     = ".ma-support.kr"
SECURE_SSL_REDIRECT    = True
SECURE_HSTS_SECONDS    = 2592000        # 30일
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
```

**주의**: `CSRF_COOKIE_DOMAIN`은 prod에서만 설정된다. dev에서 `.ma-support.kr`로 설정하면 `localhost` 개발 환경에서 CSRF 쿠키가 발급되지 않아 로그인 자체가 불가능해진다.

### 4-3. CSRF 실패 뷰

```python
CSRF_FAILURE_VIEW = "accounts.views.csrf_failure"
```

기본 Django CSRF 실패 응답 대신 커스텀 뷰를 사용한다. CSRF 실패 로그는 `django.security.csrf` 로거(`WARNING` 레벨)에 기록된다.

### 4-4. 세션 만료 동작

- `SESSION_EXPIRE_AT_BROWSER_CLOSE=True`: 브라우저 닫으면 즉시 만료
- `SESSION_COOKIE_AGE=3600`: 브라우저를 닫지 않아도 1시간 후 만료
- `SESSION_SAVE_EVERY_REQUEST=True`: 요청마다 1시간 연장 (활성 사용자 자동 유지)

---

## 5. 업로드 디렉터리 구조

### 5-1. 경로 설정

```python
# settings.py
MEDIA_ROOT        = BASE_DIR / "media"
UPLOAD_RESULT_DIR = Path(config("UPLOAD_RESULT_DIR",
                      default=str(MEDIA_ROOT / "upload_results")))
UPLOAD_TEMP_DIR   = Path(config("UPLOAD_TEMP_DIR",
                      default=str(MEDIA_ROOT / "upload_temp")))
```

| 경로 | 용도 | 환경변수 override |
|---|---|---|
| `media/` | 전체 업로드 루트 (MEDIA_ROOT) | — |
| `media/upload_results/` | Celery task 완료 결과 파일 (엑셀 등) | `UPLOAD_RESULT_DIR` |
| `media/upload_temp/` | task 처리 중 임시 파일 | `UPLOAD_TEMP_DIR` |

### 5-2. Docker 볼륨 마운트

```yaml
# docker-compose.yaml
volumes:
  - .:/app            # 소스 코드 (collectstatic 결과물 포함)
  - media_data:/app/media  # 업로드 파일 (named volume, 컨테이너 재생성 후에도 유지)
  - ../var:/app/var   # dash 모델 artifacts (DASH_MODEL_DIR)
```

`media_data` named volume은 `web`, `celery`, `celery-beat` 세 컨테이너가 **공유**한다. 엑셀 업로드를 web 컨테이너가 받고, 처리는 celery 컨테이너가 하더라도 같은 파일을 볼 수 있다.

### 5-3. 임시 파일 정리 정책

`UPLOAD_TEMP_DIR`의 임시 파일은 **task 완료 후 각 task 코드에서 직접 삭제**하는 것이 원칙이다. `try/finally` 블록으로 task 성공/실패 양쪽에서 정리한다.

```python
# task 내 임시파일 정리 패턴
tmp_path = None
try:
    tmp_path = UPLOAD_TEMP_DIR / f"{task_id}.xlsx"
    # 처리 ...
finally:
    if tmp_path and tmp_path.exists():
        tmp_path.unlink(missing_ok=True)
```

별도 배치 정리 task는 없다. 비정상 종료로 남은 잔재 파일은 수동 정리가 필요하다.

### 5-4. 첨부파일 업로드 정책 (board)

```python
BOARD_ATTACHMENT_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
BOARD_ATTACHMENT_ALLOWED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".txt", ".csv", ".xls", ".xlsx",
    ".doc", ".docx", ".ppt", ".pptx",
    ".hwp", ".hwpx",
}
```

MIME allowlist 기본값은 `board/services/attachments.py`의 `DEFAULT_ALLOWED_CONTENT_TYPES`가 SSOT다. 운영에서 커스터마이징이 필요할 때만 settings에 `BOARD_ATTACHMENT_ALLOWED_CONTENT_TYPES`를 별도 정의한다.

---

## 6. 운영 배포 체크리스트

### 6-1. Docker 서비스 구성 및 기동 순서

```
db (postgres:16-alpine)  ← healthcheck: pg_isready
redis (redis:latest)     ← healthcheck: redis-cli ping
  ↓ depends_on (healthy)
web (gunicorn+uvicorn)   ← healthcheck: GET /healthz
celery (worker)
celery-beat (scheduler)
  ↓ depends_on (web healthy)
nginx (alpine)           ← healthcheck: GET /nginx-healthz
```

**모든 컨테이너는 `restart: unless-stopped`**로 설정되어 있어 비정상 종료 시 자동 재시작된다.

### 6-2. 배포 전 체크리스트

```
[ ] .env.dev에 운영 DB/Redis URL이 포함되지 않았는지 확인
[ ] docker/.env.prod 파일 최신 값 확인 (SECRET_KEY, DATABASE_URL, REDIS_URL)
[ ] python manage.py collectstatic --noinput 실행 완료
[ ] python manage.py migrate 실행 완료 (새 마이그레이션 있을 때)
[ ] celery.py beat_schedule의 "task" 이름이 @shared_task(name=)과 일치하는지 확인
[ ] 새 Celery task 추가 시 board.tasks 패키지면 autodiscover_tasks(["board.tasks"]) 커버 확인
[ ] ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS에 신규 도메인 포함 여부 확인
```

### 6-3. 배포 후 확인

```bash
# 헬스체크
curl -H "Host: ma-support.kr" -H "X-Forwarded-Proto: https" http://127.0.0.1:8000/healthz
# 예상 응답: ok

# Celery worker 등록 task 목록 확인
celery -A web_ma inspect registered

# Celery beat 스케줄 확인
celery -A web_ma inspect scheduled

# 로그 위치
logs/django_error.log   # 500 오류 + 예외 traceback (RotatingFile, 10MB×10)
logs/access.log         # 접근 로그 (10MB×5)
logs/django_app.log     # 앱별 INFO 로그 (10MB×5)
```

### 6-4. 전체 스택 실행/중단

```bash
# 전체 스택 실행
docker-compose up -d

# 특정 서비스만 재시작 (코드 변경 후)
docker-compose restart web celery celery-beat

# 전체 중단 (볼륨 유지)
docker-compose down

# 로그 확인
docker-compose logs -f web
docker-compose logs -f celery
```

---

## 7. LLM 함정 포인트

### 7-1. 운영 설정 임의 변경 패턴 (절대 금지)

#### `IS_PROD` 판단을 우회하는 패턴

```python
# ❌ 절대 금지 — IS_PROD 게이트를 우회하는 직접 할당
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"  # IS_PROD 밖에서
SESSION_COOKIE_SECURE = True  # dev에서 True로 설정 시 localhost 쿠키 전달 실패

# ✅ 항상 IS_PROD 게이트 안에서만
if IS_PROD:
    SESSION_COOKIE_SECURE = True
```

#### Fail-fast Rails를 `try/except`로 감싸는 패턴

```python
# ❌ 절대 금지 — 의도적인 안전 차단을 무력화
try:
    ...settings import...
except RuntimeError:
    pass

# ✅ 에러가 나면 .env 파일과 APP_ENV 환경변수를 점검한다
```

#### `CELERY_TASK_ACKS_LATE` 비활성화

```python
# ❌ 금지 — at-most-once로 바꾸면 worker 재시작 시 task가 유실됨
CELERY_TASK_ACKS_LATE = False
```

### 7-2. DEBUG=True 상태에서 운영 DB 접근

settings.py는 `DEBUG=True` + `DATABASE_URL`에 `django_ma_prod` 또는 `ma_prod` 문자열이 포함되면 `RuntimeError`로 기동을 차단한다.

이를 우회하기 위해 운영 DB URL에서 해당 키워드를 제거하거나 DATABASE_URL을 환경변수로 직접 주입하는 방식은 **보안 사고의 직접적인 원인**이 된다.

```
# ❌ 절대 금지 패턴
DATABASE_URL=postgresql://user:pass@prod-host/renamed_db  # 키워드 우회
export DATABASE_URL=...  # settings.py .env 로딩 건너뜀
```

### 7-3. beat_schedule task name 불일치

```python
# ❌ 흔한 실수 — @shared_task(name=)이 없거나 beat_schedule과 다름
@shared_task  # name 미지정 → 자동 생성 이름이 beat_schedule의 "task" 값과 불일치
def my_task(): ...

# celery.py
"my-task": { "task": "board.tasks.my_task" }  # 자동 이름과 다를 수 있음

# ✅ name 항상 명시
@shared_task(name="board.tasks.my_task")
def my_task(): ...
```

### 7-4. dev에서 Celery task 진행률이 동작하지 않는 이유

dev는 `CACHES = LocMemCache`(프로세스 인메모리)다. **Django 웹 프로세스와 Celery worker 프로세스는 별개 프로세스**이므로 cache를 공유하지 않는다. task가 `cache.set()`으로 진행률을 기록해도 웹에서 `cache.get()`으로 읽을 수 없다.

이를 해결하려고 dev에 `RedisCache`를 추가하거나 `CACHES` 설정을 바꾸는 것은 의도적인 환경 분리를 파괴한다. **진행률 기능 테스트는 prod 환경에서 수행한다.**

### 7-5. collectstatic 없이 배포 후 500 오류

`IS_PROD=True`에서 `CompressedManifestStaticFilesStorage`는 `staticfiles/staticfiles.json`을 읽는다. 이 파일이 없거나 구버전이면 정적 파일 요청마다 `ValueError`가 발생한다.

```
# 증상: 운영 배포 후 CSS/JS 로드 실패, Django 500 에러
# 원인: collectstatic을 실행하지 않았거나 staticfiles/ 디렉터리가 새 컨테이너에 없음
# 해결: 반드시 배포 전 collectstatic 실행
python manage.py collectstatic --noinput
```

### 7-6. nginx healthcheck 경로 혼동

```
/healthz        → Django 뷰 응답 (web 컨테이너 healthcheck)
/nginx-healthz  → Nginx 자체 응답 (nginx 컨테이너 healthcheck)
```

두 경로는 다르다. Django `/healthz`가 응답해도 Nginx가 다운이면 외부에서 접근 불가다.

### 7-7. 새 관리 페이지에서 부문/부서/지점 API 엔드포인트 누락

`part_branch_selector.js`의 fallback URL(`/partner/ajax/fetch-parts/` 등)은 `partner` 앱의 URL 설정에 따라 존재하지 않을 수 있다. 새 페이지를 추가할 때는 반드시 root 요소의 `data-fetch-parts-url` 등 dataset을 통해 URL을 명시적으로 주입한다.
