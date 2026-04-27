#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "${ROOT_DIR}/scripts/regression/lib.sh"

require_cmd find
run_step "brandme-infra: manifests present" bash -lc "find '${ROOT_DIR}/brandme-infra' -type f \( -name '*.yml' -o -name '*.yaml' -o -name '*.tf' \) | sed -n '1p' | grep -q ."
run_step "brandme-infra: shell syntax" bash -lc "find '${ROOT_DIR}/brandme-infra' -type f -name '*.sh' -print0 | xargs -0 -r -n1 bash -n"
