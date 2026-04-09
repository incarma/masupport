# django_ma/board/constants.py
# =========================================================
# Board SSOT Constants
# - URL name / choices / category / paging / form UI fields
# - "기능 영향 없는" 순수 상수 모음 (가장 안전한 분리)
# =========================================================

from __future__ import annotations

# =========================================================
# ✅ Permission / Grades
# =========================================================
BOARD_ALLOWED_GRADES = ("superuser", "head", "leader")   # Post/Support
TASK_ALLOWED_GRADES = ("superuser",)                    # Task
INACTIVE_GRADE = "inactive"

# =========================================================
# ✅ Status / Categories
# =========================================================
STATUS_CHOICES = ("확인중", "진행중", "보완요청", "완료", "반려")
STATUS_CHOICES_TUPLES = tuple((s, s) for s in STATUS_CHOICES)

POST_CATEGORY_VALUES = ("위해촉", "리스크/유지율", "수수료/채권", "운영자금", "전산", "기타")
TASK_CATEGORY_VALUES = ("위해촉", "리스크/유지율", "수수료/채권", "운영자금", "전산", "기타", "민원", "신규제휴")
POST_CATEGORY_CHOICES = (("", "선택"),) + tuple((v, v) for v in POST_CATEGORY_VALUES)
TASK_CATEGORY_CHOICES = (("", "선택"),) + tuple((v, v) for v in TASK_CATEGORY_VALUES)

# =========================================================
# ✅ Paging / Inline actions
# =========================================================
PER_PAGE_CHOICES = [10, 25, 50, 100]
INLINE_ACTIONS = ("handler", "status")

# =========================================================
# ✅ URL Names (reverse/redirect에서 raw string 금지)
# =========================================================
POST_DETAIL = "board:post_detail"
POST_LIST = "board:post_list"
POST_EDIT = "board:post_edit"

TASK_DETAIL = "board:task_detail"
TASK_LIST = "board:task_list"
TASK_EDIT = "board:task_edit"

SUPPORT_FORM = "board:support_form"
STATES_FORM = "board:states_form"

# Attachment download URL name (원천차단)
POST_ATTACHMENT_DOWNLOAD = "board:post_attachment_download"
TASK_ATTACHMENT_DOWNLOAD = "board:task_attachment_download"

# =========================================================
# ✅ Form UI Constants (SSOT)
# =========================================================
SUPPORT_TARGET_FIELDS = [
    ("성명", "target_name_"),
    ("사번", "target_code_"),
    ("입사일", "target_join_"),
    ("퇴사일", "target_leave_"),
]

SUPPORT_CONTRACT_FIELDS = [
    ("보험사", "insurer_", 3),
    ("증권번호", "policy_no_", 3),
    ("계약자(피보험자)", "contractor_", 3),
    ("보험료", "premium_", 2),
]


# ──────────────────────────────────────────────
# 담보평가 비율 상수 (SSOT)
# ──────────────────────────────────────────────

# ── 물건 유형별 적용 비율 (%) ─────────────────────────────
# ⚠️ 규칙 변경 시 이 파일만 수정한다. 뷰·서비스에 하드코딩 금지.
COLLATERAL_RATE_APT       = 70   # 아파트
COLLATERAL_RATE_VILLA_NEW = 60   # 빌라/다세대/오피스텔 (연식 20년 미만)
COLLATERAL_RATE_VILLA_OLD = 50   # 빌라/다세대/오피스텔 (연식 20년 이상)
COLLATERAL_RATE_HOUSE     = 50   # 주택/단독주택
COLLATERAL_RATE_LAND      = 40   # 토지(지목:대)

# 계산 불가 유형 코드 집합
COLLATERAL_UNCALCULABLE_TYPES = {"etc"}

# 물건 유형 코드 → 적용 비율 매핑 (SSOT)
COLLATERAL_RATE_MAP = {
    "apt":       COLLATERAL_RATE_APT,
    "villa_new": COLLATERAL_RATE_VILLA_NEW,
    "villa_old": COLLATERAL_RATE_VILLA_OLD,
    "house":     COLLATERAL_RATE_HOUSE,
    "land":      COLLATERAL_RATE_LAND,
    # "etc" → 계산 불가, 매핑 없음
}

# Audit 액션 상수
AUDIT_ACTION_COLLATERAL_EVAL = "collateral_eval_create"

# 소유자 관계 중 근저당 설정 불가 코드 집합
COLLATERAL_OWNER_REL_BLOCKED = {"third"}