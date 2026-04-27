#!/usr/bin/env bash
set -euo pipefail

: "${REGRESSION_TIMEOUT:=600}"
: "${CI:=1}"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "❌ required command missing: $cmd"
    return 127
  fi
}

run_step() {
  local name="$1"
  shift
  echo "▶ ${name}"
  if timeout "${REGRESSION_TIMEOUT}" "$@"; then
    echo "✅ ${name}"
  else
    local code=$?
    echo "❌ ${name} (exit ${code})"
    return "${code}"
  fi
}
