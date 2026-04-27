#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "${ROOT_DIR}/scripts/regression/lib.sh"

require_cmd pnpm
run_step "brandme-gateway: type-check" pnpm -C "${ROOT_DIR}/brandme-gateway" type-check
run_step "brandme-gateway: tests" env OAUTH_CLIENT_ID=test-client OAUTH_CLIENT_SECRET=test-secret JWT_SECRET=test-secret-key-32-chars-minimum-xxxx pnpm -C "${ROOT_DIR}/brandme-gateway" test -- --run
