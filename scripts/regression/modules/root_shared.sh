#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "${ROOT_DIR}/scripts/regression/lib.sh"

require_cmd bash
require_cmd find

run_step "root: markdown/docs sanity" bash -lc "test -f '${ROOT_DIR}/PLAN.md' && test -f '${ROOT_DIR}/CLAUDE.md'"
run_step "root: shell scripts syntax" bash -lc "find '${ROOT_DIR}/scripts' -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n"
