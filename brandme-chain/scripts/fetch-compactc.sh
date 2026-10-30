#!/usr/bin/env bash
# Fetch the pinned Compact compiler by direct release-asset URL and verify sha256.
# Installs into $COMPACT_HOME (default: brandme-chain/.compact/<version>).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
ver="$(node -e "console.log(require('$here/contracts/toolchain.json').compactc.version)")"
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) key=x86_64-linux ;;
  *) echo "No pinned compactc asset for $(uname -s)-$(uname -m); add one to contracts/toolchain.json" >&2; exit 2 ;;
esac
url="$(node -e "console.log(require('$here/contracts/toolchain.json').compactc.assets['$key'].url)")"
sha="$(node -e "console.log(require('$here/contracts/toolchain.json').compactc.assets['$key'].sha256)")"
dest="${COMPACT_HOME:-$here/.compact/$ver}"
if [[ -x "$dest/compactc" ]] && [[ "$("$dest/compactc" --version)" == "$ver" ]]; then
  echo "compactc $ver present at $dest"; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/c.zip" "$url"
echo "$sha  $tmp/c.zip" | sha256sum -c -
mkdir -p "$dest"; unzip -o -q "$tmp/c.zip" -d "$dest"
test "$("$dest/compactc" --version)" == "$ver"
echo "compactc $ver installed at $dest"
