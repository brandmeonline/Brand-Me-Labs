#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "${ROOT_DIR}/scripts/regression/lib.sh"

require_cmd python3
run_step "brandme-core: compileall" python3 -m compileall "${ROOT_DIR}/brandme-core" "${ROOT_DIR}/brandme_core"
