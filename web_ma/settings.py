"""
Django settings for web_ma project (Django 5.2.x)

Goals:
- APP_ENV(dev/prod)로 .env 자동 선택
- dev/prod 모두 DATABASE_URL 단일화
- Windows/한글 로케일 환경에서 psycopg2/psycopg UnicodeDecodeError 방지용 UTF-8 강제
- 운영에서만 secure cookie / whitenoise manifest 적용
- dev에서 libpq(PG* env) 오염 방지 + docker(db host) 연결 사고 방지
- ✅ 500 에러 traceback이 반드시 로그로 남도록 로깅 체계 강화
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import dj_database_url
from decouple import Config, RepositoryEnv

# =============================================================================
# 0) Base / Env loading
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent


def _read_app_env() -> str:
    """APP_ENV 우선, 없으면 ENV, 없으면 dev."""
    return (os.environ.get("APP_ENV") or os.environ.get("ENV") or "dev").strip().lower()


def _resolve_env_path(base_dir: Path, app_env: str) -> str:
    """
    ENV_FILE 지정 시 우선 사용.
    아니면 app_env에 따라 기본 .env 선택.

    ⚠️ 실행 위치 의존 제거: 항상 BASE_DIR 기준 절대 경로 사용
    - prod:  <BASE_DIR>/docker/.env.prod
    - dev:   <BASE_DIR>/.env.dev
    """
    env_file = (os.environ.get("ENV_FILE") or "").strip()
    if env_file:
        p = Path(env_file)
        return str(p if p.is_absolute() else (base_dir / p))

    if app_env in ("prod", "production"):
        return str(base_dir / "docker" / ".env.prod")
    return str(base_dir / ".env.dev")


APP_ENV = _read_app_env()
ENV_PATH = _resolve_env_path(BASE_DIR, APP_ENV)
config = Config(RepositoryEnv(ENV_PATH))

# -----------------------------------------------------------------------------
# dev에서 libpq가 PG* 환경변수 읽어서 오염되는 케이스 방지
# - PowerShell/Windows에서 흔하게 발생: 이전 세션 값이 남아 DSN이 꼬임
# -----------------------------------------------------------------------------
if APP_ENV == "dev":
    for k in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        os.environ.pop(k, None)

# =============================================================================
# Core flags
# =============================================================================
SECRET_KEY = config("SECRET_KEY")
def _bool_from_env(key: str):
    """
    decouple bool 파서 사용을 위해 config()를 호출하되,
    키가 없으면 None 반환.
    """
    try:
        # decouple은 키가 없으면 default를 반환하므로, default=None으로 두고 cast=bool 적용
        return config(key, default=None, cast=bool)
    except Exception:
        return None


# -----------------------------------------------------------------------------
# DEBUG (SSOT)
# - SSOT 키: DJANGO_DEBUG
# - legacy 키: DEBUG (호환)
# - 기본값: dev=True / prod=False (env 누락 실수 방지)
# -----------------------------------------------------------------------------
_debug = _bool_from_env("DJANGO_DEBUG")
_debug_legacy = _bool_from_env("DEBUG") if _debug is None else None

if _debug is None and _debug_legacy is None:
    DEBUG = (APP_ENV == "dev")
else:
    DEBUG = _debug if _debug is not None else bool(_debug_legacy)


# -----------------------------------------------------------------------------
# Fail-fast safety rails
# - runserver에서 DEBUG=False면 정적파일/디버그 UX가 조용히 깨질 수 있으므로 즉시 중단
# - 운영에서 DEBUG=True면 보안상 치명적이므로 즉시 중단
# -----------------------------------------------------------------------------
_is_runserver = any(arg == "runserver" or arg.startswith("runserver") for arg in sys.argv[1:])

if APP_ENV in ("prod", "production") and DEBUG:
    raise RuntimeError("APP_ENV=prod에서는 DEBUG=True가 허용되지 않습니다. 환경변수를 점검하십시오.")

if APP_ENV == "dev" and _is_runserver and not DEBUG:
    raise RuntimeError(
        "개발(runserver) 환경에서 DEBUG=False로 실행되고 있습니다. "
        "정적파일 서빙이 404로 떨어져 UI가 붕괴할 수 있으므로 안전상 실행을 중단합니다. "
        "ENV_PATH(.env)와 DJANGO_DEBUG/DEBUG 키를 확인하십시오."
    )

IS_PROD = APP_ENV in ("prod", "production") and not DEBUG

# =============================================================================
# 1) Hosts / CSRF
# =============================================================================
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1,local.ma-support.kr,ma-support.kr",
    cast=lambda v: [s.strip() for s in v.split(",") if s.strip()],
)

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="https://local.ma-support.kr,https://ma-support.kr",
    cast=lambda v: [s.strip() for s in v.split(",") if s.strip()],
)

# =============================================================================
# 2) Applications
# =============================================================================
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Local apps
    "home",
    "join",
    "board",
    "accounts.apps.AccountsConfig",
    "commission",
    "dash",
    "manual",
    "partner.apps.PartnerConfig",
    # 3rd party
    "widget_tweaks",
    "django_extensions",
    "ckeditor",
    "ckeditor_uploader",
    "audit.apps.AuditConfig",
]

# =============================================================================
# 3) Middleware
#   - WhiteNoise는 SecurityMiddleware 바로 다음이 권장 구성
# =============================================================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "audit.middleware.RequestLogMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    # ✅ login/admin login GET에서 csrftoken 강제 발급(뷰/캐시 의존 제거)
    "web_ma.middleware.ForceCSRFCookieOnLoginMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # ✅ Phase 3: 강제 비밀번호 변경(플래그+정책엔진 기반)
    # - 인증 이후(request.user 필요) 위치 고정
    "accounts.middleware.force_password_change.ForcePasswordChangeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# =============================================================================
# 4) URL / Templates / WSGI
# =============================================================================
ROOT_URLCONF = "web_ma.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "web_ma.wsgi.application"

# =============================================================================
# 5) Database (dev/prod 단일화 + UTF8 강제)
# =============================================================================
DATABASE_URL = config("DATABASE_URL")

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=False,  # 운영 SSL 필요 시 URL로 제어 권장
    )
}

# ✅ UTF-8 강제 (psycopg2/psycopg 공통으로 안전)
DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"].update({"client_encoding": "UTF8"})

# 🚨 dev 환경에서 docker DB(host=db) 연결 시도 차단 (사고 방지)
if APP_ENV == "dev" and DATABASES["default"].get("HOST") == "db":
    raise RuntimeError("🚨 dev 환경에서 docker DB(db) 연결 차단")

# ✅ 사고 방지: DEBUG 환경에서 운영 DB 키워드 감지 시 차단
if DEBUG and ("django_ma_prod" in DATABASE_URL or "ma_prod" in DATABASE_URL):
    raise RuntimeError("🚨 개발 환경에서 운영 DB 연결 시도 차단!")

# =============================================================================
# 6) Auth / Login
# =============================================================================
AUTH_USER_MODEL = "accounts.CustomUser"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "manual:manual_list"
LOGOUT_REDIRECT_URL = "manual:manual_list"

# =============================================================================
# Phase 3) Force Password Change (SSOT)
# - 운영 롤백을 위해 전역 토글을 반드시 둡니다.
# - 스코프 리스트는 우선 환경변수 기반으로 시작하되,
#   정책엔진(should_enforce)은 향후 DB scope 모델로 확장 가능하게 설계합니다.
# =============================================================================
FORCE_PASSWORD_CHANGE_ENABLED = config(
    "FORCE_PASSWORD_CHANGE_ENABLED",
    default=False,
    cast=bool,
)

def _csv_set(v: str) -> set[str]:
    return {s.strip() for s in (v or "").split(",") if s.strip()}

# ✅ URL name whitelist (최소 동선)
FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES = _csv_set(
    config(
        "FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES",
        default="login,logout,accounts:password_change,accounts:password_change_done",
    )
)

# ✅ 점진 적용 스코프(allow)
FORCE_PASSWORD_CHANGE_SCOPE_BRANCHES = _csv_set(config("FORCE_PASSWORD_CHANGE_SCOPE_BRANCHES", default=""))
FORCE_PASSWORD_CHANGE_SCOPE_PARTS = _csv_set(config("FORCE_PASSWORD_CHANGE_SCOPE_PARTS", default=""))
FORCE_PASSWORD_CHANGE_SCOPE_CHANNELS = _csv_set(config("FORCE_PASSWORD_CHANGE_SCOPE_CHANNELS", default=""))

# ✅ 차단 우선(deny-first)
FORCE_PASSWORD_CHANGE_DENY_BRANCHES = _csv_set(config("FORCE_PASSWORD_CHANGE_DENY_BRANCHES", default=""))
FORCE_PASSWORD_CHANGE_DENY_PARTS = _csv_set(config("FORCE_PASSWORD_CHANGE_DENY_PARTS", default=""))
FORCE_PASSWORD_CHANGE_DENY_CHANNELS = _csv_set(config("FORCE_PASSWORD_CHANGE_DENY_CHANNELS", default=""))

# ✅ grade 예외(운영 안전)
FORCE_PASSWORD_CHANGE_EXEMPT_GRADES = _csv_set(
    config(
        "FORCE_PASSWORD_CHANGE_EXEMPT_GRADES",
        default="superuser,main_admin",
    )
)

# =============================================================================
# 7) I18N / Timezone
# =============================================================================
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

DATETIME_FORMAT = "Y-m-d H:i"
DATE_FORMAT = "Y-m-d"

# =============================================================================
# 8) Static / Media
# =============================================================================
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# 운영에서만 manifest storage (정적 파일 캐시/무결성)
if IS_PROD:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# =============================================================================
# 9) Session / Cookie (운영에서만 secure + domain)
# =============================================================================
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 60  # 1 hour
SESSION_SAVE_EVERY_REQUEST = True

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False

SESSION_COOKIE_SECURE = IS_PROD
CSRF_COOKIE_SECURE = IS_PROD

# ✅ prod에서만 도메인 쿠키 적용(로컬 개발 쿠키 꼬임 방지)
if IS_PROD:
    SESSION_COOKIE_DOMAIN = ".ma-support.kr"
    CSRF_COOKIE_DOMAIN = ".ma-support.kr"

# ✅ 로그인 폼은 top-level navigation이므로 Lax가 안전
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# =============================================================================
# 10) Redis / Celery
# =============================================================================
REDIS_URL = config("REDIS_URL", default="redis://127.0.0.1:6379/1")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)

# =============================================================================
# 11) Upload dirs / Limits
# =============================================================================
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

UPLOAD_RESULT_DIR = Path(config("UPLOAD_RESULT_DIR", default=str(MEDIA_ROOT / "upload_results")))
UPLOAD_TEMP_DIR = Path(config("UPLOAD_TEMP_DIR", default=str(MEDIA_ROOT / "upload_temp")))

# =============================================================================
# 12) CKEditor
# =============================================================================
CKEDITOR_UPLOAD_PATH = "uploads/"
CKEDITOR_CONFIGS = {"default": {"toolbar": "full", "height": 420, "width": "100%"}}

# =============================================================================
# 13) Default PK
# =============================================================================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =============================================================================
# 14) Logging (✅ 500 Traceback 확보 / 운영에서도 누락 방지)
# -----------------------------------------------------------------------------
# 핵심 포인트:
# - django.request: 500 및 에러 traceback의 표준 로거 (반드시 ERROR 핸들러 지정)
# - root: 누락 방지용으로 ERROR를 파일/콘솔에 연결
# - 파일은 RotatingFileHandler로 용량 폭주 방지
# - 로그 디렉터리 고정: <BASE_DIR>/logs/*
# =============================================================================
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FORMAT = "[{asctime}] {levelname} {name} {message}"
LOG_STYLE = "{"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": LOG_FORMAT, "style": LOG_STYLE},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "access_file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "access.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "error_file": {
            "level": "ERROR",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "django_error.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 10,
            "formatter": "verbose",
        },
        "app_file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "django_app.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "loggers": {
        # ✅ 500 / 템플릿 에러 / NoReverseMatch 등 request-level 에러가 여기로 떨어짐
        "django.request": {
            "handlers": ["error_file", "console"],
            "level": "ERROR",
            "propagate": False,
        },
        # 보안 관련
        "django.security": {
            "handlers": ["access_file", "console"],
            "level": "INFO",
            "propagate": True,
        },
        # CSRF 실패 경고는 별도 로거로 크게 찍기
        "django.security.csrf": {
            "handlers": ["access_file", "console"],
            "level": "WARNING",
            "propagate": False,
        },
        # 기존 커스텀 접근 로그 유지
        "accounts.access": {
            "handlers": ["access_file"],
            "level": "INFO",
            "propagate": False,
        },
        # commission 쪽도 문제 추적 쉬우라고 기본 app 로그 연결(선택)
        "commission": {
            "handlers": ["app_file", "error_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    # ✅ root에 ERROR를 연결해 “어디 로거에도 안 잡힌 예외”를 방지
    "root": {
        "handlers": ["error_file", "console"],
        "level": "ERROR",
    },
}

# runserver 요청 로그 소음 제거(유지)
logging.getLogger("django.server").setLevel(logging.ERROR)

CSRF_FAILURE_VIEW = "accounts.views.csrf_failure"

# =============================================================================
# 15) Reverse proxy / SSL (Cloudflare + Nginx 종료 전제)
# =============================================================================
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# =============================================================================
# 16) Dash models directory (pipeline artifacts)
# =============================================================================
DASH_MODEL_DIR = str(BASE_DIR / "var" / "dash_models")