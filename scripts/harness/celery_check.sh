#!/usr/bin/env bash
# scripts/harness/celery_check.sh
# Celery beat_schedule "task" 이름과 @shared_task(name=) 등록명 불일치 탐지
#
# 원칙 (CLAUDE.md): beat_schedule의 "task" 값은 @shared_task(name=) 값과 정확히 일치해야 한다.
# 불일치 시 태스크가 실행되지 않고 에러도 발생하지 않아 탐지가 매우 어렵다.
#
# 사용: bash scripts/harness/celery_check.sh
# 성공: exit 0
# 실패: exit 1 + 불일치 목록

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

# Python 런처 자동 감지 (python3 → python → py 순서)
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

PYTHONIOENCODING=utf-8 "$PYTHON" "${SCRIPT_DIR}/_celery_check.py"
