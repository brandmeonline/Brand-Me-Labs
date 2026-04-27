#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODULE_DIR="${ROOT_DIR}/scripts/regression/modules"
REPORT_FILE="${ROOT_DIR}/scripts/regression/.last-run-report.md"

modules=(
  root_shared
  brandme_core
  brandme_cube
  brandme_governance
  brandme_agents
  brandme_gateway
  brandme_chain
  brandme_frontend
  brandme_console
  brandme_data
  brandme_infra
)

passed=()
failed=()
start_ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

echo "# Module Regression Report" >"${REPORT_FILE}"
echo "" >>"${REPORT_FILE}"
echo "Start: ${start_ts}" >>"${REPORT_FILE}"
echo "Timeout per step: ${REGRESSION_TIMEOUT:-600}s" >>"${REPORT_FILE}"
echo "" >>"${REPORT_FILE}"

for module in "${modules[@]}"; do
  echo ""
  echo "=============================="
  echo "Running regression module: ${module}"
  echo "=============================="

  if bash "${MODULE_DIR}/${module}.sh"; then
    echo "✅ Module passed: ${module}"
    passed+=("${module}")
  else
    echo "❌ Module failed: ${module}"
    failed+=("${module}")
  fi
done

{
  echo "## Results"
  echo ""
  echo "### Passed (${#passed[@]})"
  for m in "${passed[@]}"; do
    echo "- ✅ ${m}"
  done
  echo ""
  echo "### Failed (${#failed[@]})"
  if [[ ${#failed[@]} -eq 0 ]]; then
    echo "- None"
  else
    for m in "${failed[@]}"; do
      echo "- ❌ ${m}"
    done
  fi
  echo ""
  echo "End: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
} >>"${REPORT_FILE}"

if [[ ${#failed[@]} -ne 0 ]]; then
  echo ""
  echo "Regression suite FAILED (${#failed[@]} module(s))"
  echo "Report: ${REPORT_FILE}"
  exit 1
fi

echo ""
echo "Regression suite PASSED"
echo "Report: ${REPORT_FILE}"
