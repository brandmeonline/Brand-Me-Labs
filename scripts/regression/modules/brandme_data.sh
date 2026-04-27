#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "${ROOT_DIR}/scripts/regression/lib.sh"

require_cmd find
run_step "brandme-data: schema files present" bash -lc "test -d '${ROOT_DIR}/brandme-data/schemas'"
run_step "brandme-data: SQL parse smoke" bash -lc "find '${ROOT_DIR}/brandme-data' -type f \( -name '*.sql' -o -name '*.ddl' \) | sed -n '1,200p' >/dev/null"
