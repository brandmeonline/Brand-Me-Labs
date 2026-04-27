#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "${ROOT_DIR}/scripts/regression/lib.sh"

require_cmd pnpm
run_step "brandme-frontend: typescript compile" pnpm -C "${ROOT_DIR}/brandme-frontend" exec tsc --noEmit
