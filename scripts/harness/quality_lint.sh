#!/usr/bin/env bash
# scripts/harness/quality_lint.sh
# 코드 품질 위반 패턴 탐지 — QUALITY_RULES.md 기반
#
# 사용: bash scripts/harness/quality_lint.sh
# 성공(위반 없음): exit 0 + "✅ 품질 점검 통과"
# 실패(위반 있음): exit 1 + 위반 목록

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

# Python 런처 자동 감지
_find_python() {
  for cmd in python3 python py; do
    if command -v "$cmd" &>/dev/null; then
      if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" 2>/dev/null; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  echo ""
}
PYTHON=$(_find_python)

VIOLATIONS=0

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

echo "========================================"
echo " 코드 품질 위반 탐지 (QUALITY_RULES.md)"
echo "========================================"
echo ""

# ─────────────────────────────────────────
# Q-01: CSRF 토큰 조회 로직 파일 내 재구현 탐지
#   → common/manage/csrf.js의 getCSRFToken()이 SSOT
#   → getCookie / getCsrf / csrfmiddlewaretoken / document.cookie.*csrf 재구현 금지
# ─────────────────────────────────────────
result=$(grep -rn \
  "getCookie\s*(\|getCsrf\|function getCsrf\|csrfmiddlewaretoken\|document\.cookie.*csrf\|document\.cookie.*csrftoken" \
  static/js/ --include="*.js" 2>/dev/null \
  | grep -v "/csrf\.js:" \
  | grep -v "/csrf_window\.js:" \
  | grep -v "\.min\.js:" \
  | grep -v "csrfInput\.name\s*=" \
  || true)
fail "Q-01" "CSRF 토큰 재구현 — common/manage/csrf.js getCSRFToken() 사용 필요" "$result"

# ─────────────────────────────────────────
# Q-02a: 앱 전용 CSS에서 :root 전역 변수 선언
#   → 앱 루트 ID 하위로 이동 필요 (#app-root { --var: ... })
# ─────────────────────────────────────────
result=$(grep -rn "^:root\s*{" static/css/apps/ 2>/dev/null || true)
fail "Q-02a" "앱 CSS에서 :root 전역 변수 선언 (앱 루트 ID 하위로 스코핑 필요)" "$result"

# ─────────────────────────────────────────
# Q-02b: commission.css 스코프 없는 전역 클래스 선언
#   → 페이지 루트 ID 하위에서만 클래스 선언 허용
# ─────────────────────────────────────────
if [ -f "static/css/apps/commission.css" ]; then
  result=$(grep -n "^\.[a-z][a-z_-]*\s*{" static/css/apps/commission.css 2>/dev/null || true)
  fail "Q-02b" "commission.css 전역 클래스 — 페이지 루트 ID 하위로 스코핑 필요" "$result"
fi

# ─────────────────────────────────────────
# Q-03: commission/views/ 내 JSON 응답 헬퍼 중복 정의
#   → commission/views/utils_json.py의 _json_error가 SSOT
# ─────────────────────────────────────────
if [ -d "commission/views" ]; then
  json_helper_defs=$(grep -rn \
    "def _json_err\b\|def _json_error\b\|def _ok\b\|def _err\b" \
    commission/views/ --include="*.py" 2>/dev/null || true)
  def_count=$(echo "$json_helper_defs" | grep -c "def " 2>/dev/null || echo "0")
  if [ "$def_count" -gt 1 ]; then
    fail "Q-03" "commission/views/ 내 JSON 응답 헬퍼 중복 정의 (utils_json.py SSOT 사용 필요)" \
      "$json_helper_defs"
  fi
fi

# ─────────────────────────────────────────
# URL-01: static/js/ 내 Django 앱 경로 하드코딩
#   → 모든 URL은 dataset 속성으로 주입 (data-fetch-url 등)
# ─────────────────────────────────────────
result=$(grep -rn \
  '["'"'"'][/]\(board\|commission\|partner\|dash\|accounts\|manual\|audit\|join\)[/]' \
  static/js/ --include="*.js" 2>/dev/null \
  | grep -v "\.min\.js:" \
  | grep -v "^\s*//" \
  | grep -v "\s*||" \
  | grep -v "\*\s" \
  | grep -v "fallbacks\s*=" \
  | grep -v "new URL\b" \
  | grep -v "href=.*encodeURIComponent" \
  || true)
fail "URL-01" "JS 내 URL 하드코딩 — dataset 속성으로 주입 필요 (data-fetch-url 등)" "$result"

# ─────────────────────────────────────────
# BF-01: IIFE 페이지 스크립트에서 BFCache 가드 누락
#   → addEventListener를 바인딩하는 비모듈 파일은
#     'if (root.dataset.inited === "1") return; root.dataset.inited = "1"' 필수
#   (common/, vendor/, *.min.js, ESM 모듈 파일 제외)
# ─────────────────────────────────────────
BF_VIOLATIONS=""
while IFS= read -r -d '' jsfile; do
  # 공통 유틸·벤더 제외
  [[ "$jsfile" == *"/common/"* ]] && continue
  [[ "$jsfile" == *"/vendor/"* ]] && continue

  # addEventListener 없는 파일 건너뜀
  grep -q "addEventListener" "$jsfile" 2>/dev/null || continue

  # ESM 모듈 파일(import 문 포함) 건너뜀
  grep -q "^import " "$jsfile" 2>/dev/null && continue

  # BFCache 가드 확인
  if ! grep -q "dataset\.inited" "$jsfile" 2>/dev/null; then
    BF_VIOLATIONS="${BF_VIOLATIONS}${jsfile}"$'\n'
  fi
done < <(find static/js -name "*.js" ! -name "*.min.js" -type f -print0 2>/dev/null)

# BF-01: 경고 출력만, VIOLATIONS 카운트 제외
# 근거: 로그인·랜딩 등 단일 진입 페이지, 모달·유틸 파일 등 BFCache 실제 영향 없는
#       파일이 다수 포함되어 false positive 비율이 높음.
#       실제 재진입 가능 페이지(deposit_home 등)는 별도 스프린트에서 점진적 적용.
if [ -n "${BF_VIOLATIONS%$'\n'}" ]; then
  echo "⚠️  [BF-01] BFCache 가드(dataset.inited) 누락 파일 (경고만, 커밋 차단 안 함)"
  echo "${BF_VIOLATIONS%$'\n'}" | sed 's/^/     /'
  echo ""
fi

# ─────────────────────────────────────────
# EX-01: except: pass 예외 삼키기 패턴
#   → 예외를 조용히 삼키면 audit log 누락 등 silent failure 발생
#   (migrations, tests 제외 / logger.* 또는 log_action 있는 경우 제외)
# ─────────────────────────────────────────
if [ -n "${PYTHON:-}" ]; then
  result=$(PYTHONIOENCODING=utf-8 "$PYTHON" "${SCRIPT_DIR}/_except_check.py" 2>/dev/null)
  fail "EX-01" "except: pass 예외 삼키기 — logger 또는 log_action으로 처리 필요" "$result"
else
  echo "⚠️  [EX-01] Python 없음 — except:pass 검사 건너뜀"
fi

# ─────────────────────────────────────────
# 결과 출력
# ─────────────────────────────────────────
echo "========================================"
if [ "$VIOLATIONS" -eq 0 ]; then
  echo "✅ 품질 점검 통과"
  exit 0
else
  echo "❌ 품질 위반 ${VIOLATIONS}건 발견 — docs/harness/QUALITY_RULES.md 확인 필요"
  exit 1
fi

# ─────────────────────────────────────────
# RN-01: RateExample normalizer 위험 연산 패턴 경고
#   → 보험사별 parser에서 % 단위 보정이 섞이면 회귀 가능
#   → 1차 도입은 경고만 출력한다.
# ─────────────────────────────────────────
RN_VIOLATIONS=""
if [ -d "commission/services/rate_example_normalizers" ]; then
  RN_VIOLATIONS=$(grep -rn \
    "\* *100\|/ *100\|/ *0\.97\|\* *12" \
    commission/services/rate_example_normalizers --include="*.py" 2>/dev/null \
    | grep -v "_common/decimal.py" \
    | grep -v "_common/pdf.py" \
    || true)
fi

if [ -n "${RN_VIOLATIONS%$'\n'}" ]; then
  echo "⚠️  [RN-01] RateExample normalizer 위험 연산 패턴 감지 (경고만, 커밋 차단 안 함)"
  echo "${RN_VIOLATIONS%$'\n'}" | sed 's/^/     /'
  echo ""
fi

# ─────────────────────────────────────────
# RN-02: RateExample parser 내부 PDF extractor 중복 구현 경고
#   → _common/pdf.py의 extract_pdf_text_with_fallback 사용 권장
#   → 보험사별 좌표 parser는 예외 가능하므로 경고만 출력한다.
# ─────────────────────────────────────────
PDF_EXTRACT_DUP=""
if [ -d "commission/services/rate_example_normalizers" ]; then
  PDF_EXTRACT_DUP=$(grep -rn \
    "def _extract_pdf_text\|PdfReader\|pdfplumber\.open\|fitz\.open" \
    commission/services/rate_example_normalizers --include="*.py" 2>/dev/null \
    | grep -v "_common/pdf.py" \
    || true)
fi

if [ -n "${PDF_EXTRACT_DUP%$'\n'}" ]; then
  echo "⚠️  [RN-02] RateExample PDF extractor 중복 구현 후보 (경고만, 커밋 차단 안 함)"
  echo "${PDF_EXTRACT_DUP%$'\n'}" | sed 's/^/     /'
  echo ""
fi