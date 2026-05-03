#!/usr/bin/env bash
# scripts/harness/css_scope_check.sh
# CSS 스코프 루트 밖 규칙 탐지
#
# 규칙 (CLAUDE.md CSS Architecture):
#   - board.css    : 모든 규칙이 .board-scope 하위에 있어야 함
#   - partner.css  : 모든 규칙이 #manage-* 또는 #partner-* 하위에 있어야 함
#   - base.css     : 앱 전용 클래스(.board-*, #manage-*, #dash-*, #commission-*) 존재 금지
#   - apps/*.css   : :root 전역 변수 선언 금지
#
# 사용: bash scripts/harness/css_scope_check.sh
# 성공: exit 0
# 실패: exit 1 + 위반 목록

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
if [ -z "$PYTHON" ]; then
  echo "❌ Python 3.8+ 를 찾을 수 없습니다. Python을 설치하거나 PATH를 확인하세요."
  exit 1
fi

PYTHONIOENCODING=utf-8 "$PYTHON" "${SCRIPT_DIR}/_css_scope_check.py"
