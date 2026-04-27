#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "${ROOT_DIR}/scripts/regression/lib.sh"

require_cmd pnpm
run_step "brandme-chain: type-check" pnpm -C "${ROOT_DIR}/brandme-chain" type-check
run_step "brandme-chain: tests" pnpm -C "${ROOT_DIR}/brandme-chain" test
