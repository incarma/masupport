#!/usr/bin/env bash
# scripts/harness/security_lint.sh
# 보안 위반 패턴 탐지 — HARNESS_RULES.md 기반
#
# 사용: bash scripts/harness/security_lint.sh
# 성공(위반 없음): exit 0 + "✅ 보안 점검 통과"
# 실패(위반 있음): exit 1 + 위반 목록

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

VIOLATIONS=0

# 위반 항목 출력 헬퍼
fail() {
  local rule="$1"
  local desc="$2"
  local result="$3"
  if [ -n "$result" ]; then
    echo "❌ [${rule}] ${desc}"
    echo "$result" | sed 's/^/     /'
    echo ""
    VIOLATIONS=$((VIOLATIONS + 1))
  fi
}

# 상수 미사용 체크 헬퍼 (정의됨 but 호출 없음)
warn_unused_constant() {
  local rule="$1"
  local constant="$2"
  local result
  result=$(grep -rn "${constant}" --include="*.py" . 2>/dev/null \
    | grep -v "audit/constants.py" \
    | grep -v "^Binary" \
    || true)
  if [ -z "$result" ]; then
    echo "❌ [${rule}] 상수 '${constant}' 정의됨 → log_action 호출 없음 (감사 기록 공백)"
    echo "     위치: audit/constants.py 에 정의됨, 실제 사용처 0건"
    echo ""
    VIOLATIONS=$((VIOLATIONS + 1))
  fi
}

echo "========================================"
echo " 보안 위반 탐지 (HARNESS_RULES.md)"
echo "========================================"
echo ""

# ─────────────────────────────────────────
# S-A-01: 템플릿에서 .file.url / .image.url 직접 노출
#   → 첨부 파일 URL 직접 노출 금지, 반드시 다운로드 뷰 경유
# ─────────────────────────────────────────
result=$(grep -rn "\.file\.url\|\.image\.url" templates/ --include="*.html" 2>/dev/null || true)
fail "S-A-01" "템플릿에서 .file.url / .image.url 직접 노출 (다운로드 뷰 경유 필수)" "$result"

# ─────────────────────────────────────────
# S-A-02: 템플릿에서 /media/ 직접 링크
#   → /media/ URL을 href/src에 직접 삽입하면 권한 검증 우회
# ─────────────────────────────────────────
result=$(grep -rn "href=[\"'][^\"']*\/media\/\|src=[\"'][^\"']*\/media\/" \
  templates/ --include="*.html" 2>/dev/null || true)
fail "S-A-02" "템플릿에서 /media/ 직접 링크 (다운로드 뷰 경유 필수)" "$result"

# ─────────────────────────────────────────
# S-A-05: Attachment.objects.create(file= 직접 사용
#   → save_attachments() SSOT 우회 금지
# ─────────────────────────────────────────
result=$(grep -rn "Attachment\.objects\.create(" --include="*.py" . 2>/dev/null \
  | grep "file=" \
  | grep -v "migrations/" \
  | grep -v "tests" \
  || true)
fail "S-A-05" "Attachment.objects.create(file=) 직접 호출 (save_attachments() SSOT 우회)" "$result"

# ─────────────────────────────────────────
# S-B-03: .update()에 grade='inactive' 단독 사용
#   → grade 변경 시 is_active=False 미반영 위험
# ─────────────────────────────────────────
result=$(grep -rn "\.update(" --include="*.py" . 2>/dev/null \
  | grep "grade" \
  | grep "inactive" \
  | grep -v "migrations/" \
  | grep -v "#" \
  || true)
fail "S-B-03" ".update(grade='inactive') 단독 사용 (is_active=False 동기화 필요)" "$result"

# ─────────────────────────────────────────
# S-B-04: 외부 노출 API/뷰에서 CustomUser.objects.filter/all() 직접 사용
#   → 사용자 검색 결과는 반드시 accounts/search_api.py 경유
#   (accounts 앱 내부, 서비스·유틸·태스크·관리명령·PDF 생성 등 정상 사용은 제외)
# ─────────────────────────────────────────
result=$(grep -rn "CustomUser\.objects\.\(filter\|all\)(" --include="*.py" . 2>/dev/null \
  | grep -v "accounts/" \
  | grep -v "/services/" \
  | grep -v "/utils" \
  | grep -v "/tasks" \
  | grep -v "management/commands/" \
  | grep -v "pdf_" \
  | grep -v "migrations/" \
  | grep -v "tests" \
  || true)
fail "S-B-04" "뷰에서 CustomUser.objects.filter/all() 직접 사용 — 사용자 검색은 search_api.py 경유 필요" "$result"

# ─────────────────────────────────────────
# S-C-03: request.user.username 사용
#   → USERNAME_FIELD = "id" (사번), username 필드 없음
# ─────────────────────────────────────────
result=$(grep -rn "request\.user\.username" --include="*.py" . 2>/dev/null \
  | grep -v "migrations/" \
  | grep -v "#" \
  || true)
fail "S-C-03" "request.user.username 사용 (USERNAME_FIELD='id', request.user.id 사용 필요)" "$result"

# ─────────────────────────────────────────
# S-S-01: grade 할당 후 log_action 미호출 (partner/views/subadmin.py)
#   → grade 변경은 감사 필수 이벤트
# ─────────────────────────────────────────
SUBADMIN="partner/views/subadmin.py"
if [ -f "$SUBADMIN" ]; then
  grade_lines=$(grep -n "grade\s*=\s*[\"']" "$SUBADMIN" 2>/dev/null || true)
  has_log_action=false
  grep -q "log_action" "$SUBADMIN" 2>/dev/null && has_log_action=true || true
  if [ -n "$grade_lines" ] && [ "$has_log_action" = "false" ]; then
    fail "S-S-01" "partner/views/subadmin.py: grade 변경 후 log_action 미호출" "$grade_lines"
  fi
fi

# ─────────────────────────────────────────
# S-S-02: accounts/tasks.py에 ACCOUNTS_EXCEL_UPLOAD log_action 미호출
#   → 계정 일괄 업로드는 grade 포함 → 감사 필수
# ─────────────────────────────────────────
accounts_audit=$(grep -n "ACCOUNTS_EXCEL_UPLOAD\|ACCOUNTS_GRADE_UPDATE" \
  accounts/tasks.py accounts/admin.py 2>/dev/null || true)
if [ -z "$accounts_audit" ]; then
  fail "S-S-02" \
    "accounts/tasks.py에 ACCOUNTS_EXCEL_UPLOAD / ACCOUNTS_GRADE_UPDATE log_action 미호출" \
    "accounts/tasks.py, accounts/admin.py 내 해당 상수 참조 0건"
fi

# ─────────────────────────────────────────
# S-S-03: commission/ 내 @csrf_exempt 사용
#   → cross-origin POST 허용 → CSRF 우회 가능
# ─────────────────────────────────────────
result=$(grep -rn "csrf_exempt" --include="*.py" commission/ 2>/dev/null || true)
fail "S-S-03" "commission/ 내 @csrf_exempt 사용 (X-CSRFToken 헤더 방식으로 대체 필요)" "$result"

# ─────────────────────────────────────────
# S-S-04: COMMISSION_EXCEL_UPLOAD — 미정의 상수 참조
#   → AttributeError → try/except 안에서 조용히 실패 → 감사 기록 없음
# ─────────────────────────────────────────
defined=$(grep -n "COMMISSION_EXCEL_UPLOAD" audit/constants.py 2>/dev/null || true)
used=$(grep -rn "COMMISSION_EXCEL_UPLOAD" --include="*.py" . 2>/dev/null \
  | grep -v "audit/constants\.py" || true)
if [ -z "$defined" ] && [ -n "$used" ]; then
  fail "S-S-04" \
    "COMMISSION_EXCEL_UPLOAD: audit/constants.py 미정의 + 참조 존재 (AttributeError → 감사 기록 공백)" \
    "$used"
fi

# ─────────────────────────────────────────
# S-S-05: 정의된 grade 변경 상수가 실제 log_action 호출에 미사용
#   → 상수만 있고 실제 호출 없으면 감사 시스템 무력화와 동일
# ─────────────────────────────────────────
warn_unused_constant "S-S-05" "PARTNER_LEADER_ADD"
warn_unused_constant "S-S-05" "PARTNER_LEADER_DELETE"
warn_unused_constant "S-S-05" "ACCOUNTS_GRADE_UPDATE"

# ─────────────────────────────────────────
# 결과 출력
# ─────────────────────────────────────────
echo "========================================"
if [ "$VIOLATIONS" -eq 0 ]; then
  echo "✅ 보안 점검 통과"
  exit 0
else
  echo "❌ 보안 위반 ${VIOLATIONS}건 발견 — docs/harness/HARNESS_RULES.md 확인 필요"
  exit 1
fi
