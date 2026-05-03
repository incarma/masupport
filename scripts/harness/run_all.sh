#!/usr/bin/env bash
# scripts/harness/run_all.sh
# 보안·품질·Celery·CSS 린트 스크립트를 순서대로 실행하고 결과를 저장한다.
#
# 사용: bash scripts/harness/run_all.sh
# 출력: docs/audit/lint_result_YYYYMMDD.txt
# 종료: 하나라도 실패하면 exit 1

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

DATE=$(date +"%Y%m%d")
RESULT_DIR="docs/audit"
RESULT_FILE="${RESULT_DIR}/lint_result_${DATE}.txt"

mkdir -p "${RESULT_DIR}"

OVERALL_PASS=true

# 스크립트 목록 (실행 순서 고정)
SCRIPTS=(
  "scripts/harness/security_lint.sh"
  "scripts/harness/quality_lint.sh"
  "scripts/harness/celery_check.sh"
  "scripts/harness/css_scope_check.sh"
)

SCRIPT_LABELS=(
  "보안 위반 탐지"
  "코드 품질 위반 탐지"
  "Celery task 이름 정합성"
  "CSS 스코프 위반 탐지"
)

# 결과 파일 헤더
{
  echo "========================================"
  echo " django_ma Harness Lint 결과"
  echo " 실행일시: $(date '+%Y-%m-%d %H:%M:%S')"
  echo " 기준 커밋: $(git rev-parse --short HEAD 2>/dev/null || echo 'N/A')"
  echo "========================================"
  echo ""
} | tee "${RESULT_FILE}"

# 각 스크립트 실행
for i in "${!SCRIPTS[@]}"; do
  script="${SCRIPTS[$i]}"
  label="${SCRIPT_LABELS[$i]}"

  {
    echo "────────────────────────────────────────"
    echo "[$((i+1))/${#SCRIPTS[@]}] ${label}"
    echo "────────────────────────────────────────"
  } | tee -a "${RESULT_FILE}"

  if bash "${script}" 2>&1 | tee -a "${RESULT_FILE}"; then
    echo "" | tee -a "${RESULT_FILE}"
  else
    OVERALL_PASS=false
    echo "" | tee -a "${RESULT_FILE}"
  fi
done

# 최종 결과
{
  echo "========================================"
  if $OVERALL_PASS; then
    echo "✅ 전체 점검 통과 — 커밋 진행 가능"
  else
    echo "❌ 점검 실패 — docs/harness/NEVER_DO.md 를 확인하세요"
    echo ""
    echo "  결과 저장 위치: ${RESULT_FILE}"
  fi
  echo "========================================"
} | tee -a "${RESULT_FILE}"

echo ""
echo "결과 저장: ${RESULT_FILE}"

if $OVERALL_PASS; then
  exit 0
else
  exit 1
fi
