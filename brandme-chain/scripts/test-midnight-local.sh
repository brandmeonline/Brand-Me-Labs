#!/usr/bin/env bash
# pnpm test:midnight:local — exit evidence for W09 (local, no network):
#   1. pinned compactc present and correct version
#   2. contracts compile (TS + zkir; proving keys too unless SKIP_ZK=1)
#   3. compiled artifacts match contracts/artifact-manifest.json
#   4. constraint, property and adversarial suites against the compiled contract
#   5. adapter/private-state/operation unit tests
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
bash scripts/fetch-compactc.sh
if [[ "${SKIP_ZK:-0}" == "1" ]]; then
  echo "SKIP_ZK=1: compiling without proving keys; manifest check covers non-key artifacts only"
  ver="$(node -e "console.log(require('./contracts/toolchain.json').compactc.version)")"
  for src in contracts/src/*.compact; do
    out="$(mktemp -d)"; "${COMPACT_HOME:-.compact/$ver}/compactc" --skip-zk "$src" "$out"
    name="$(basename "$src" .compact)"
    cmp "$out/contract/index.js" "contracts/managed/$name/contract/index.js" || { echo "compiled $name differs from committed artifacts" >&2; exit 1; }
  done
else
  bash scripts/compile-contracts.sh
  git diff --exit-code -- contracts/artifact-manifest.json || { echo "artifact manifest changed — commit it with the contract change" >&2; exit 1; }
fi
node scripts/verify-artifacts.mjs
npx vitest run ../tests/contracts tests/midnight
