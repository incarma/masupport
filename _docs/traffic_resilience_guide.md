# django_ma 대규모 트래픽 공격 · 장애 대응 지침서

> **생성일**: 2026-05-13
> **분석 커밋**: f3eb938
> **스택**: Cloudflare → Nginx(Alpine) → Gunicorn+Uvicorn → Django 5.2 → PostgreSQL 16 + Redis
> **목적**: 의도된/의도치 않은 대규모 트래픽으로 인한 공격 및 장애에 대한 취약점 분석과 단계별 대응 방안

---

## 요약 대시보드

| 영역 | 취약점 수 | 🔴 즉시조치 | 🟠 단기조치 | 🟡 중기조치 | ✅ 양호 |
|------|----------|-----------|-----------|-----------|--------|
| T-A. 레이어별 Rate Limit | 4 | 2 | 2 | 0 | 1 |
| T-B. 인증/로그인 보호 | 1 | 0 | 0 | 1 | 3 |
| T-C. 파일 업로드 폭탄 | 0 | 0 | 0 | 0 | 6 |
| T-D. DB 부하 집중 | 0 | 0 | 0 | 0 | 3 |
| T-E. Celery/Redis 과부하 | 1 | 0 | 0 | 1 | 5 |
| T-F. 외부 API 의존성 | 1 | 0 | 0 | 1 | 1 |
| T-G. 인프라 보호 설정 | 4 | 0 | 2 | 1 | 4 |
| T-H. 정보 노출 위험 | 1 | 0 | 0 | 1 | 3 |

---

## 🔴 즉시 조치 필요 항목

> 현재 공격 발생 시 직접적인 피해로 이어지는 항목입니다.

### [T-A-01] Nginx 레이어 Rate Limit 완전 미설정

- **위험도**: 🔴 높음
- **공격 시나리오**: Cloudflare WAF를 우회한 트래픽(또는 Cloudflare bypass 공격)이 Nginx에 도달할 경우 로그인 brute force, 업로드 폭탄, AJAX API 과호출을 무제한으로 허용한다. Gunicorn worker가 모두 점유되면 전체 서비스 중단으로 이어진다.
- **현재 코드 위치**: `ops/nginx/default.conf:53-116` — `limit_req_zone`, `limit_req` 지시자 전혀 없음
- **영향 범위**: 전체 서비스 (login, upload, AJAX API 포함)
- **대응 방안**: 아래 T-A-1 섹션 참조
- **구현 우선순위**: 즉시

### [T-A-02] Cloudflare Real IP 복원 미설정 — 오탐/IP 스푸핑 위험

- **위험도**: 🔴 높음
- **공격 시나리오**: Cloudflare가 앞단에 있으므로 Nginx의 `$remote_addr`는 Cloudflare edge IP이다. Django의 IP 기반 rate limit(`board/services/rate_limit.py:83-102`) 및 audit 로그(`audit/middleware.py`)가 모두 Cloudflare IP로 기록되어, 실제 공격자 IP 차단이 불가능하고 정상 사용자가 단일 IP에서 몰리면 오탐 차단될 수 있다.
- **현재 코드 위치**: `ops/nginx/default.conf:96-100` — `X-Real-IP $remote_addr` 전달 시 real_ip_module 미사용
- **영향 범위**: IP 기반 rate limit, audit log IP 기록 정확성
- **대응 방안**: 아래 T-A-1 섹션의 Cloudflare Real IP 복원 설정 참조
- **구현 우선순위**: 즉시

---

## T-A. 레이어별 Rate Limit 현황 및 대응

### A-1. 현재 Rate Limit 적용 현황

#### Nginx 레이어 (최전선 방어)

`ops/nginx/default.conf` 전체 스캔 결과: `limit_req_zone`, `limit_req` 지시자 **0건** — 완전 미설정.

**Nginx Rate Limit 대응 방안:**

```nginx
# ops/nginx/default.conf 상단(http 블록 상위 또는 include 파일)에 추가
# ⚠️ nginx:alpine 기본 빌드에 ngx_http_realip_module이 포함되어 있음

# -- Cloudflare IP 신뢰 + 실제 클라이언트 IP 복원 --
# Cloudflare 공식 IPv4 목록 (https://www.cloudflare.com/ips-v4)
set_real_ip_from 103.21.244.0/22;
set_real_ip_from 103.22.200.0/22;
set_real_ip_from 103.31.4.0/22;
set_real_ip_from 104.16.0.0/13;
set_real_ip_from 104.24.0.0/14;
set_real_ip_from 108.162.192.0/18;
set_real_ip_from 131.0.72.0/22;
set_real_ip_from 141.101.64.0/18;
set_real_ip_from 162.158.0.0/15;
set_real_ip_from 172.64.0.0/13;
set_real_ip_from 173.245.48.0/20;
set_real_ip_from 188.114.96.0/20;
set_real_ip_from 190.93.240.0/20;
set_real_ip_from 197.234.240.0/22;
set_real_ip_from 198.41.128.0/17;
real_ip_header CF-Connecting-IP;
real_ip_recursive on;

# -- Rate Limit Zone 정의 --
# 일반 페이지: 분당 60회 (1초에 1회)
limit_req_zone $binary_remote_addr zone=general:10m rate=60r/m;

# 로그인: 분당 10회 (brute force 방어)
limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;

# 파일 업로드: 분당 5회
limit_req_zone $binary_remote_addr zone=upload:10m rate=5r/m;

# API (AJAX): 분당 120회
limit_req_zone $binary_remote_addr zone=api:10m rate=120r/m;
```

```nginx
# ops/nginx/default.conf — server 블록(443 ssl, ma-support.kr) 내 location 수정

# 로그인 엔드포인트 강화
location = /login/ {
    limit_req zone=login burst=5 nodelay;
    limit_req_status 429;
    proxy_pass http://web:8000;
    proxy_http_version 1.1;
    proxy_set_header Host ma-support.kr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_connect_timeout 30s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}

# 엑셀 업로드 엔드포인트
location ~* ^/(commission|accounts)/.*upload.*$ {
    limit_req zone=upload burst=3 nodelay;
    limit_req_status 429;
    client_max_body_size 50m;
    proxy_pass http://web:8000;
    proxy_http_version 1.1;
    proxy_set_header Host ma-support.kr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_connect_timeout 30s;
    proxy_send_timeout 120s;  # 업로드는 send 타임아웃 여유 필요
    proxy_read_timeout 120s;
}

# AJAX/API 요청
location ~* ^/(board|commission|dash|manual|partner)/.*$ {
    limit_req zone=api burst=20 nodelay;
    limit_req_status 429;
    proxy_pass http://web:8000;
    proxy_http_version 1.1;
    proxy_set_header Host ma-support.kr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_connect_timeout 30s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    proxy_redirect off;
    proxy_intercept_errors on;
    error_page 502 503 504 = /maintenance.html;
}

# 일반 페이지 (기존 / location 교체)
location / {
    limit_req zone=general burst=15 nodelay;
    limit_req_status 429;
    proxy_pass http://web:8000;
    proxy_http_version 1.1;
    proxy_set_header Host ma-support.kr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_connect_timeout 30s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    proxy_redirect off;
    proxy_intercept_errors on;
    error_page 502 503 504 = /maintenance.html;
}
```

> ⚠️ Nginx 설정 변경 후 반드시 `docker exec django_nginx nginx -t`로 문법 검증 후 `docker exec django_nginx nginx -s reload`.

#### Django 레이어 (애플리케이션 레벨 방어)

스캔 결과: `board/services/rate_limit.py` — Redis 기반 고정 윈도우 rate limit SSOT 구현 ✅

**현재 적용 엔드포인트:**

| 파일 | 라인 | 스코프 | 규칙 |
|------|------|--------|------|
| `board/views/industry_info.py` | 210 | `industry:preference` | `BOARD_INDUSTRY_PREF_RATE_LIMIT` (30/60) |
| `board/views/industry_info.py` | 301 | `industry:click` | `BOARD_INDUSTRY_CLICK_RATE_LIMIT` (60/60) |
| `board/views/forms.py` | 59 | `board:search_user` 등 | `BOARD_SEARCH_USER_RATE_LIMIT` (30/60) |
| `board/views/forms.py` | 196 | PDF 생성 | `BOARD_SUPPORT_PDF_RATE_LIMIT` (10/60) |
| `board/views/forms.py` | 245 | PDF 생성 | `BOARD_STATES_PDF_RATE_LIMIT` (10/60) |

**미적용 고위험 엔드포인트 (🟠):**

### [T-A-03] commission 업로드/결재 엔드포인트 Rate Limit 미적용

- **위험도**: 🟠 중간
- **현재 코드 위치**: `commission/views/api_upload.py:53` — `@grade_required("superuser")` 만 있고 rate limit 없음; `commission/views/approval.py:97` 동일
- **공격 시나리오**: superuser 계정 탈취 시 대용량 엑셀 반복 업로드로 gunicorn worker 및 DB 부하 유발
- **대응 방안**: 기존 `board/services/rate_limit.py` 패턴 재사용

```python
# settings.py 에 추가 (11-3 섹션 하위)
COMMISSION_UPLOAD_RATE_LIMIT = config(
    "COMMISSION_UPLOAD_RATE_LIMIT",
    default="5/60",  # 60초에 5회
)

# commission/views/api_upload.py:53 — @grade_required 아래에 추가
from board.services.rate_limit import check_rate_limit, rate_limited_json
from django.conf import settings

@require_POST
@grade_required("superuser")
def upload_excel(request):
    rl = check_rate_limit(
        request,
        scope="commission:upload",
        rule=getattr(settings, "COMMISSION_UPLOAD_RATE_LIMIT", "5/60"),
    )
    if not rl.allowed:
        return rate_limited_json(rl)
    # ... 이하 기존 코드
```

### [T-A-04] 담보평가 계산/삭제 API Rate Limit 설정은 있으나 미적용

- **위험도**: 🟠 중간
- **현재 코드 위치**: `web_ma/settings.py:488-495` — `BOARD_COLLATERAL_CALC_RATE_LIMIT="20/60"`, `BOARD_COLLATERAL_DELETE_RATE_LIMIT="10/60"` 설정 존재하나 `board/views/collateral.py:45-60`의 `collateral_calc` 뷰에서 호출하지 않음
- **공격 시나리오**: 담보평가 계산이 CPU 집약적인 경우 반복 호출로 부하 유발
- **대응 방안**:

```python
# board/views/collateral.py:45 — collateral_calc 함수 상단에 추가
from board.services.rate_limit import check_rate_limit, rate_limited_json
from django.conf import settings

@login_required
@require_POST
def collateral_calc(request):
    rl = check_rate_limit(
        request,
        scope="board:collateral_calc",
        rule=getattr(settings, "BOARD_COLLATERAL_CALC_RATE_LIMIT", "20/60"),
    )
    if not rl.allowed:
        return rate_limited_json(rl)
    # ... 이하 기존 코드
```

---

### A-2. 로그인 Brute Force 방어 현황 ✅

스캔 결과:

- `accounts/constants.py:35` — `LOGIN_FAIL_MAX_COUNT = 5`
- `accounts/views.py:334` — 5회 실패 시 `is_locked = True` 처리
- `accounts/views.py:327` — 잠긴 계정 로그인 시도 즉시 차단

**현재 계정 잠금 정책:**
- 최대 실패 횟수: **5회** (`LOGIN_FAIL_MAX_COUNT = 5`)
- 잠금 기록: `locked_at`, `lock_reason = "LOGIN_FAIL_MAX"` DB 기록
- 잠금 해제: 관리자 수동 해제 방식

**추가 방어 방안 (Cloudflare 레이어):**

```
Cloudflare 대시보드 권장 설정:
- Security > WAF > Rate Limiting Rules:
  * /login/ : 동일 IP 5분에 20회 초과 시 5분 차단 (Challenge)
  * /admin/ : 동일 IP 1분에 5회 초과 시 24시간 차단 (Block)
- Security > Bot Fight Mode: ON
- Security > Challenge Passage: 30분

설정 위치: Cloudflare Dashboard > ma-support.kr > Security
```

---

## T-B. 인증/세션 보호 현황 및 대응

### B-1. 세션 만료 정책 ✅

스캔 결과 (`web_ma/settings.py:322-338`):
- `SESSION_COOKIE_AGE = 3600` (1시간)
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`
- `SESSION_SAVE_EVERY_REQUEST = True`
- `SESSION_COOKIE_HTTPONLY = True`
- `SESSION_COOKIE_SECURE = IS_PROD` (운영에서만 Secure 쿠키)
- `SESSION_COOKIE_SAMESITE = "Lax"`

### B-2. 프록시 헤더 신뢰 설정

스캔 결과 (`web_ma/settings.py:680-681`):
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` ✅
- `USE_X_FORWARDED_HOST = True` ✅

스캔 결과 (`web_ma/settings.py:415-418`):
```python
AUDIT_TRUSTED_PROXY_CIDRS = "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
```

### [T-B-01] AUDIT_TRUSTED_PROXY_CIDRS 범위 과대 설정 🟡

- **위험도**: 🟡 낮음
- **공격 시나리오**: Docker 내부 네트워크 범위(`172.16.0.0/12`)는 적절하나 `10.0.0.0/8` 및 `192.168.0.0/16`은 과도하게 넓다. VPN 또는 내부 네트워크에서 `X-Forwarded-For` 헤더를 조작하면 audit 로그 IP가 스푸핑될 수 있다.
- **대응 방안**: Docker 내부 브리지 네트워크 대역만 신뢰

```python
# settings.py (docker-compose 기본 내부 네트워크: 172.x.x.x)
AUDIT_TRUSTED_PROXY_CIDRS = config(
    "AUDIT_TRUSTED_PROXY_CIDRS",
    default="127.0.0.1/32,::1/128,172.16.0.0/12",
    cast=lambda v: tuple(s.strip() for s in v.split(",") if s.strip()),
)
```

> ✅ T-A-02의 Nginx Real IP 복원을 먼저 적용하면 이 위험이 크게 감소한다.

---

## T-C. 파일 업로드 공격 방어 현황 및 대응 ✅ 전항목 양호

### C-1. 업로드 크기 제한 현황

| 레이어 | 현재 설정 | 상태 |
|--------|----------|------|
| Nginx `client_max_body_size` | `50m` (`ops/nginx/default.conf:65`) | ✅ |
| Django `DATA_UPLOAD_MAX_NUMBER_FIELDS` | `10000` (`settings.py:401`) | ✅ |
| Board 첨부 `BOARD_ATTACHMENT_MAX_UPLOAD_SIZE` | `10MB` (`settings.py:430-433`) | ✅ |

### C-2. 파일 타입 검증 ✅

- `settings.py:436-444` — `BOARD_ATTACHMENT_ALLOWED_EXTENSIONS` 허용 확장자 제한
- MIME allowlist: `board/services/attachments.py` `DEFAULT_ALLOWED_CONTENT_TYPES`

### C-3. 비동기 처리 현황 ✅

- `commission/views/api_upload.py:99` — `transaction.atomic()` 으로 감쌈
- `commission/views/api_upload.py:95` — `save_temp_upload()` 임시 파일 저장
- `commission/views/_files.py` — `safe_delete()` `finally` 정리 패턴
- `accounts` 엑셀 업로드 — `accounts/tasks.py` Celery 비동기 처리

### C-4. CSRF 보호 ✅

- `docs/audit/duplicate_detection_report_20260507.md` 확인: `commission/views/api_upload.py`, `approval.py` 양쪽 `@csrf_exempt` 제거 완료 (grep 0건)

---

## T-D. DB 부하 집중 취약점 및 대응 ✅ 전항목 양호

### D-1. 커넥션 풀 설정 ✅

스캔 결과 (`web_ma/settings.py:212-217`):
```python
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,  # 10분 persistent connection
    )
}
```

단일 gunicorn 인스턴스 + `conn_max_age=600`은 적절하다. worker 수 × 1 커넥션 정도가 유지되므로 PgBouncer 없이도 운영 가능한 수준이다.

### D-2. N+1 쿼리 패턴 ✅

스캔 결과: `select_related` / `prefetch_related` 사용 파일 22건 확인. 서비스 레이어(`commission/services/`, `partner/services/`)에서 주요 쿼리 최적화 적용됨.

### D-3. 페이지네이션 ✅

스캔 결과: `board/views/posts.py`, `board/views/industry_info.py`, `board/views/tasks.py`, `board/views/worktasks.py` — paginate 사용 확인.

### D-4. 슬로우 쿼리 모니터링 설정 (권장)

```python
# settings.py — dev 환경 추가 (선택)
if APP_ENV == "dev":
    LOGGING["loggers"]["django.db.backends"] = {
        "handlers": ["console"],
        "level": "DEBUG",
        "propagate": False,
    }
```

---

## T-E. Celery / Redis 과부하 취약점 및 대응

### E-1. Beat 스케줄 동시 부하 분석

스캔 결과 (`web_ma/celery.py:56-136`):

| 태스크 | 주기 | 실행 시각(분) |
|--------|------|------------|
| `collect_board_industry_news` | 6시간 | :05 (0,6,12,18시) |
| `cleanup_old_industry_articles` | 매일 | 03:00 |
| `build_sales_aggs_hourly` | 매시간 | :10 |
| `build_sales_forecasts_daily` | 매일 | 02:10 |
| `build_sales_forecasts_hourly` | 매시간 | :20 |
| `generate_monthly_worktasks` | 매월 1일 | 00:10 |
| `notify_due_worktasks` | 매일 | 08:00 |
| `sync_kr_holidays_window` (daily) | 매일 | 04:20 |
| `sync_kr_holidays_window` (monthly) | 매월 1일 | 04:40 |

**동시 실행 위험 시각:**
- 매월 1일 00:10 — `build_sales_aggs_hourly` + `generate_monthly_worktasks` 동시 실행
- 매일 02:10 — `build_sales_aggs_hourly` + `build_sales_forecasts_daily` 동시 실행
- 위 겹침은 단일 worker에서 큐잉되므로 deadlock 위험은 낮으나 처리 지연 가능

### E-2. 타임아웃 설정 ✅

스캔 결과 (`web_ma/settings.py:395-396`):
- Hard limit: `CELERY_TASK_TIME_LIMIT = 60 * 30` (30분)
- Soft limit: `CELERY_TASK_SOFT_TIME_LIMIT = 60 * 25` (25분)
- Visibility timeout: `3600`초 (1시간)

### [T-E-01] 장시간 태스크 개별 타임아웃 미설정 🟡

- **위험도**: 🟡 낮음
- **현재 상태**: 전역 time_limit 설정은 있으나 외부 API 호출 태스크에 개별 limit 없음. 외부 API hang 시 전역 25분 soft limit까지 worker 점유
- **현재 코드 위치**: `board/tasks/` — `@shared_task` 에 `soft_time_limit`, `time_limit` 미설정
- **대응 방안**: 외부 API 의존 태스크에 개별 타임아웃 지정

```python
# board/tasks/industry_info.py 또는 해당 태스크에 적용
@shared_task(
    name="board.tasks.industry_info.collect_board_industry_news",
    bind=True,
    max_retries=3,
    soft_time_limit=120,   # 2분 soft limit
    time_limit=180,        # 3분 hard limit
    default_retry_delay=60,
)
def collect_board_industry_news(self):
    from celery.exceptions import SoftTimeLimitExceeded
    try:
        # 수집 로직...
        pass
    except SoftTimeLimitExceeded:
        logger.warning("[collect_news] soft time limit 초과 — 조기 종료")
    except Exception as exc:
        logger.exception("[collect_news] 수집 실패")
        raise self.retry(exc=exc)
```

### E-3. Redis 연결 복구 설정 ✅

스캔 결과 (`web_ma/settings.py:375-391`):
- `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True` ✅
- `CELERY_BROKER_CONNECTION_MAX_RETRIES = 100` ✅
- `CELERY_TASK_ACKS_LATE = True` ✅
- `CELERY_TASK_REJECT_ON_WORKER_LOST = True` ✅
- `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` ✅

### E-4. Redis 단일 장애점(SPOF) 분석

```
현재 아키텍처: Redis 단일 인스턴스 (docker-compose.yaml:18-27)
장애 발생 시 영향:
  - Celery worker 중단 (beat 스케줄 포함)
  - 운영 Django 캐시(RedisCache) 전면 miss
  - (세션은 DB 기반 SESSION_ENGINE = "django.contrib.sessions.backends.db" 이므로 영향 없음)

단기 대응:
  1. restart: unless-stopped 자동 재시작 이미 적용 ✅
  2. 캐시 miss가 발생해도 서비스 연속성은 유지됨 (DB fallback)
     → dash/viewmods/pages.py:95 cache.get() 실패 시 DB 재조회 패턴 ✅

중기 대응: (선택)
  - Redis Sentinel 도입 검토 (단일 서버 운영 규모에선 불필요할 수 있음)
```

---

## T-F. 외부 API 의존성 취약점 및 대응

### F-1. 외부 API 호출 현황

| API | 위치 | timeout | fallback |
|-----|------|---------|---------|
| 공공데이터 공휴일 API | `board/services/holidays.py:161` | `KR_HOLIDAY_API_TIMEOUT=10s` ✅ | DB 캐시 유지 ✅ |
| 네이버 검색 API | `board/services/industry_news.py:128` | 20초 하드코딩 🟡 | 예외 처리 있음 |

### [T-F-01] 네이버 API timeout 하드코딩 — 환경 설정 불가 🟡

- **위험도**: 🟡 낮음
- **현재 코드 위치**: `board/services/industry_news.py:128` — `urlopen(req, timeout=20)` 하드코딩
- **공격 시나리오**: 네이버 API 응답 지연 시 해당 Celery worker가 20초 동안 점유됨. 설정 변경 없이 조정 불가
- **대응 방안**:

```python
# settings.py 에 추가 (17번 섹션 하위)
NAVER_SEARCH_API_TIMEOUT = config(
    "NAVER_SEARCH_API_TIMEOUT",
    default=20,
    cast=int,
)

# board/services/industry_news.py — fetch 함수 내 수정
from django.conf import settings

timeout = getattr(settings, "NAVER_SEARCH_API_TIMEOUT", 20)
with urlopen(req, timeout=timeout) as resp:
    ...
```

---

## T-G. 인프라 보호 설정 현황 및 대응

### G-1. Docker 컨테이너 리소스 제한 미설정 🟠

스캔 결과: `docker-compose.yaml` 전체에 `deploy.resources`, `--cpus`, `--memory` 설정 **0건**.

### [T-G-01] Docker 컨테이너 리소스 무제한 — OOM 카스케이드 위험

- **위험도**: 🟠 중간
- **공격 시나리오**: 대용량 업로드 / 과부하 쿼리 / 메모리 누수 발생 시 컨테이너가 호스트 메모리를 전부 소비 → OOM Killer가 DB 또는 Redis를 종료 → 전체 스택 중단
- **대응 방안**:

```yaml
# docker-compose.yaml — 각 서비스에 추가
# ⚠️ docker-compose up에서 deploy.resources는 --compatibility 플래그 필요
# 단순하게는 아래와 같이 mem_limit을 사용할 수 있음 (v2 syntax)

services:
  web:
    mem_limit: 1g
    cpus: "2.0"

  celery:
    mem_limit: 768m
    cpus: "1.5"

  celery-beat:
    mem_limit: 256m
    cpus: "0.5"

  db:
    mem_limit: 2g
    cpus: "2.0"

  redis:
    mem_limit: 256m
    cpus: "0.5"

  nginx:
    mem_limit: 128m
    cpus: "0.5"
```

> ⚠️ `mem_limit`은 docker-compose v2(Compose spec)에서 직접 사용 가능. `docker stack deploy` 없이도 동작.

### G-2. Gunicorn Worker 설정 미흡 🟠

### [T-G-02] Gunicorn workers / timeout / max-requests 미설정

- **위험도**: 🟠 중간
- **현재 코드 위치**: `docker-compose.yaml:35-41` — workers, timeout, max-requests 없음
- **공격 시나리오**: 기본 worker 수(1개)로 운영 시 동시 요청 처리 불가. `--timeout` 미설정으로 느린 요청이 worker를 영구 점유할 수 있음. 장기 운영 시 메모리 누수 누적
- **대응 방안**:

```yaml
# docker-compose.yaml — web 서비스 command 교체
web:
  command: >
    gunicorn web_ma.asgi:application
    -k uvicorn.workers.UvicornWorker
    --workers 3
    --bind 0.0.0.0:8000
    --timeout 120
    --graceful-timeout 30
    --keep-alive 5
    --max-requests 1000
    --max-requests-jitter 100
    --log-level info
    --access-logfile -
    --error-logfile -
    --capture-output
```

> `--max-requests 1000`: 워커당 1000 요청 후 자동 재시작 (메모리 누수 방지)
> `--max-requests-jitter 100`: 동시 재시작 방지 랜덤 분산
> `--workers 3`: CPU 코어 수 × 2 + 1 공식. 단일 서버에서 2-4가 적절

### G-3. Nginx 타임아웃 설정 분석 ✅

스캔 결과 (`ops/nginx/default.conf:101-104`):
- `proxy_connect_timeout 30s` ✅
- `proxy_send_timeout 60s` ✅
- `proxy_read_timeout 60s` ✅

60초 read timeout은 엑셀 업로드 동기 처리(commission)에서 타임아웃 가능성이 있다. T-G-02의 `--timeout 120` 설정 후 nginx `proxy_read_timeout`도 상향 검토 권장.

### G-4. server_tokens 미설정 🟡

### [T-G-03] Nginx 버전 정보 응답 헤더 노출

- **위험도**: 🟡 낮음
- **현재 코드 위치**: `ops/nginx/default.conf` — `server_tokens` 지시자 없음
- **대응 방안**:

```nginx
# ops/nginx/default.conf — 443 ssl server 블록 상단에 추가
server_tokens off;  # Server: nginx 버전 정보 제거
```

### G-5. 기타 인프라 보호 ✅

- default_server 에서 불필요한 요청 444 차단: `ops/nginx/default.conf:11-14` ✅
- `/media/` 직접 접근 403 차단: `ops/nginx/default.conf:73-75` ✅
- 숨김 파일 차단: `ops/nginx/default.conf:86-90` ✅
- 전 컨테이너 `restart: unless-stopped` ✅
- 전 컨테이너 `healthcheck` 설정 ✅

---

## T-H. 정보 노출 위험 현황 및 대응

### H-1. 환경 파일 시크릿 관리

> ⚠️ 시크릿 실제 값은 기록하지 않습니다.

스캔 결과 (`web_ma/settings.py:68`):
- `SECRET_KEY = config("SECRET_KEY")` — decouple로 환경 파일에서 로드 ✅
- `POSTGRES_PASSWORD` — `docker/.env.prod` 에서 로드 ✅
- `NAVER_SEARCH_CLIENT_SECRET` — `settings.py:759` `config()` 로드 ✅
- `KR_HOLIDAY_API_KEY` — `settings.py:526` `config()` 로드 ✅

모두 코드에 직접 하드코딩되지 않고 환경 파일에서 로드됨. `.env.dev`, `docker/.env.prod`는 `.gitignore`로 커밋 제외 필요 (현재 정책).

```bash
# 강력한 SECRET_KEY 생성
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 강력한 DB 패스워드 생성
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### H-2. 관리자 경로 노출 🟡

### [T-H-01] /admin/ 기본 경로 사용

- **위험도**: 🟡 낮음
- **현재 코드 위치**: `web_ma/urls.py:39` — `path("admin/", custom_admin_site.urls)`
- **공격 시나리오**: 자동화 스캐너가 `/admin/`을 표적으로 brute force 시도
- **참고**: custom_admin_site 사용 중이므로 Django 기본 admin 노출은 아님. Cloudflare WAF가 `/admin/` 접근 제한 규칙을 적용하면 충분
- **대응 방안 (선택적)**:

```python
# web_ma/urls.py
import os
ADMIN_PATH = os.environ.get("ADMIN_URL_PATH", "admin")
# path("admin/", ...) → path(f"{ADMIN_PATH}/", ...)
```

```
# docker/.env.prod 에 추가 (보안 강화 원할 경우)
# ADMIN_URL_PATH=internal-mgmt-xxxx/
```

### H-3. 에러 응답 정보 노출 ✅

스캔 결과:
- `web_ma/settings.py:103-104` — `APP_ENV=prod` + `DEBUG=True` 시 `RuntimeError` 즉시 발생 (Fail-fast rails) ✅
- `web_ma/urls.py:16` — `handler500 = "web_ma.views.handler500"` 커스텀 핸들러 ✅
- `web_ma/settings.py:566-674` — 에러 traceback은 `logs/django_error.log`에만 기록, 클라이언트 노출 없음 ✅
- Nginx `server_tokens` — 미설정 (T-G-03 참조) 🟡

---

## 장애 대응 시나리오별 즉시 조치 절차

### 시나리오 1: 갑작스러운 트래픽 폭증 (DDoS / 바이럴)

```bash
# Step 1: 현재 Nginx 연결 수 확인
docker exec django_nginx sh -c "netstat -an 2>/dev/null | grep ESTABLISHED | wc -l"

# Step 2: Nginx 접근 로그에서 상위 IP 확인 (Cloudflare IP가 표시될 수 있음 — T-A-02 해결 전)
docker exec django_nginx sh -c "tail -1000 /var/log/nginx/access.log 2>/dev/null | awk '{print \$1}' | sort | uniq -c | sort -rn | head -20"

# Step 3: Cloudflare 대시보드에서 해당 IP/ASN 차단
# Security > WAF > Tools > IP Access Rules

# Step 4: Gunicorn worker 상태 확인
docker exec django_web sh -c "ps aux | grep gunicorn"

# Step 5: DB 커넥션 수 확인
docker exec django_db sh -c "psql -U incar_ma -d django_ma_local -c \"SELECT count(*) FROM pg_stat_activity;\""
```

### 시나리오 2: Celery worker 멈춤 / 태스크 큐 쌓임

```bash
# Step 1: Celery worker 상태 확인
docker exec django_celery celery -A web_ma inspect active

# Step 2: 큐에 쌓인 태스크 수 확인
docker exec redis_server redis-cli llen celery

# Step 3: worker 재시작
docker-compose restart celery

# Step 4: beat 재시작
docker-compose restart celery-beat

# Step 5: 큐 비우기 — 주의: 태스크 유실
# 반드시 내용 확인 후 결정:
# docker exec redis_server redis-cli lrange celery 0 10
# docker exec redis_server redis-cli del celery
```

### 시나리오 3: PostgreSQL 커넥션 고갈

```bash
# Step 1: 현재 커넥션 목록 확인
docker exec django_db sh -c "psql -U incar_ma -d django_ma_local -c \
  \"SELECT pid, usename, application_name, state, query_start \
   FROM pg_stat_activity ORDER BY query_start;\""

# Step 2: 장시간 실행 중인 쿼리 확인
docker exec django_db sh -c "psql -U incar_ma -d django_ma_local -c \
  \"SELECT pid, now()-query_start AS duration, state, left(query,80) \
   FROM pg_stat_activity \
   WHERE state='active' AND now()-query_start > interval '30 seconds';\""

# Step 3: 특정 커넥션 강제 종료 (pid 확인 후)
# docker exec django_db sh -c "psql -U incar_ma -d django_ma_local -c \
#   \"SELECT pg_terminate_backend({pid});\""

# Step 4: Django web 재시작으로 커넥션 풀 리셋
docker-compose restart web
```

### 시나리오 4: Redis 장애

```bash
# Step 1: Redis 상태 확인
docker exec redis_server redis-cli ping

# Step 2: 자동 재시작 상태 확인
docker ps -a | grep redis

# Step 3: 수동 재시작
docker-compose restart redis

# Step 4: Redis 재시작 후 Celery worker 재연결 확인
docker-compose restart celery celery-beat

# 참고: SESSION_ENGINE = "django.contrib.sessions.backends.db"
# → Redis 장애로 로그인 세션 유지됨. 캐시(RedisCache)는 miss로 전환되어
# → 서비스 느려지나 중단되지 않음.
```

---

## 모니터링 설정 권장사항

### 현재 로그 파일 위치

스캔 결과 (`web_ma/settings.py:566-674`):

```
logs/django_error.log   # 500 에러 + 예외 traceback (10MB × 10)
logs/access.log         # 보안/접근 로그 (10MB × 5)
logs/django_app.log     # 앱별 INFO 로그 (10MB × 5)
```

### 즉시 확인해야 할 로그 패턴

```bash
# 500 에러 실시간 감시
docker exec django_web sh -c "tail -f /app/logs/django_error.log"

# CSRF 실패 패턴 (brute force 지표)
docker exec django_web sh -c "grep 'Forbidden' /app/logs/access.log | tail -50"

# Celery 에러 실시간 감시
docker-compose logs -f --tail=100 celery

# 로그인 실패 연속 발생 모니터링
docker exec django_web sh -c "grep 'login_fail' /app/logs/django_app.log | tail -50"
```

### Cloudflare 모니터링

```
Cloudflare Analytics 확인 포인트:
- Traffic > Overview: 요청 수 급증 여부
- Security > Overview: 차단/챌린지 트래픽 비율
- Analytics > Firewall Events: WAF 발동 이력
- Speed > Optimization: 캐시 히트율 (낮으면 Origin 서버 부하 증가)
```

---

## 우선순위별 구현 로드맵

### 🔴 즉시 조치 (이번 주 내)

| 항목 | 파일 | 내용 |
|------|------|------|
| T-A-01 | `ops/nginx/default.conf` | Nginx limit_req_zone + limit_req 추가 |
| T-A-02 | `ops/nginx/default.conf` | Cloudflare Real IP 복원 (set_real_ip_from + real_ip_header) |

### 🟠 단기 조치 (1개월 내)

| 항목 | 파일 | 내용 |
|------|------|------|
| T-A-03 | `commission/views/api_upload.py`, `approval.py` | commission 업로드 rate limit 적용 |
| T-A-04 | `board/views/collateral.py` | collateral calc/delete rate limit 실제 호출 추가 |
| T-G-01 | `docker-compose.yaml` | 컨테이너 메모리/CPU 제한 추가 |
| T-G-02 | `docker-compose.yaml` | Gunicorn --workers, --timeout, --max-requests 설정 |

### 🟡 중기 조치 (분기 내)

| 항목 | 파일 | 내용 |
|------|------|------|
| T-B-01 | `web_ma/settings.py` | AUDIT_TRUSTED_PROXY_CIDRS 범위 축소 |
| T-E-01 | `board/tasks/` | 외부 API 태스크 개별 soft_time_limit 설정 |
| T-F-01 | `board/services/industry_news.py` | 네이버 API timeout 설정화 |
| T-G-03 | `ops/nginx/default.conf` | server_tokens off 추가 |
| T-H-01 | `web_ma/urls.py` | /admin/ 경로 환경변수화 (선택) |

---

## 회귀 위험 점검 (본 지침서 구현 후)

```
[ ] Nginx rate limit 추가 후 정상 사용자 로그인/업로드 동작 확인
    → test: 로그인 10회 이하 정상 동작, 30회 이상 429 응답 확인
[ ] Cloudflare Real IP 복원 후 audit 로그의 IP가 실제 클라이언트 IP로 기록되는지 확인
[ ] Docker 리소스 제한 추가 후 전체 스택 정상 기동 확인
    → docker-compose up && docker-compose ps (all healthy)
[ ] python manage.py check — 0 issues 확인
[ ] Gunicorn --workers 3 설정 후 정상 기동 확인
    → docker exec django_web ps aux | grep gunicorn (3개 worker 확인)
[ ] Celery beat 스케줄 정상 동작 확인
    → celery -A web_ma inspect scheduled
[ ] /healthz 및 /nginx-healthz 정상 응답 확인
[ ] 로그인 → 주요 페이지 진입 → 파일 업로드 흐름 전체 확인
[ ] 에러 발생 시 logs/django_error.log 에 traceback 기록 확인
```

---

*이 지침서는 Claude Code에 의해 자동 생성되었습니다.*
*코드베이스 변경 시 재실행하여 최신 상태를 유지하십시오.*
