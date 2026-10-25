#!/usr/bin/env bash
# Compile every contract with the pinned compactc and write the artifact manifest.
# Usage: compile-contracts.sh [--skip-zk]
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
ver="$(node -e "console.log(require('$here/contracts/toolchain.json').compactc.version)")"
bin="${COMPACT_HOME:-$here/.compact/$ver}/compactc"
[[ -x "$bin" ]] || bash "$here/scripts/fetch-compactc.sh"
[[ "$("$bin" --version)" == "$ver" ]] || { echo "compactc version mismatch" >&2; exit 1; }
for src in "$here"/contracts/src/*.compact; do
  name="$(basename "$src" .compact)"
  out="$here/contracts/managed/$name"
  rm -rf "$out"
  "$bin" "$@" "$src" "$out"
done
node "$here/scripts/verify-artifacts.mjs" --write
