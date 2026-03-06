# django_ma/accounts/constants.py
"""
accounts 앱 공통 상수/헬퍼 모음
- 로그인 잠금 정책 상수 단일화
"""

from __future__ import annotations


# ---------------------------------------------------------------------
# Upload progress cache keys (admin.py / views.py / tasks.py 공통)
# ---------------------------------------------------------------------
CACHE_PROGRESS_PREFIX = "upload_progress:"
CACHE_STATUS_PREFIX = "upload_status:"
CACHE_ERROR_PREFIX = "upload_error:"
CACHE_RESULT_PATH_PREFIX = "upload_result_path:"

CACHE_TIMEOUT_SECONDS = 60 * 60  # 1 hour


def cache_key(prefix: str, task_id: str) -> str:
    return f"{prefix}{task_id}"


# ---------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------
EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------
# Account Lockout
# ---------------------------------------------------------------------
# 로그인 5회 연속 실패 시 계정 잠금
LOGIN_FAIL_MAX_COUNT = 5

# 잠금 사유(SSOT)
LOCK_REASON_LOGIN_FAIL_MAX = "LOGIN_FAIL_MAX"

# 사용자 메시지(SSOT)
INVALID_LOGIN_MESSAGE = "아이디 또는 비밀번호가 올바르지 않습니다."
ACCOUNT_LOCKED_MESSAGE = "비밀번호를 5회 이상 틀리게 입력하셔서 계정이 잠겼습니다. 관리자에게 문의 바랍니다."

# Admin action label
ADMIN_ACTION_RESET_PASSWORD_AND_UNLOCK = "(Lockout) 선택 사용자 비밀번호 초기화 + 잠금 해제"
