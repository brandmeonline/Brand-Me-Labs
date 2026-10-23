#!/usr/bin/env python3
"""Rewrite a staged pnpm lockfile's importer keys for a single-service Docker build.

Background: the repo-root pnpm-lock.yaml has one importer per workspace package
(e.g. `brandme-chain:`). The Docker build uses the service dir as its build root
and runs `pnpm install --frozen-lockfile` there, so pnpm expects a single `.`
importer matching the staged service package.json. A verbatim copy of the
repo-root lockfile fails with ERR_PNPM_OUTDATED_LOCKFILE because the specifiers
never match.

Usage:
    python3 docker-lockfile-importer-fix.py <repo-lockfile> <importer-key> <output-lockfile>

Example:
    python3 docker-lockfile-importer-fix.py pnpm-lock.yaml brandme-chain \
        brandme-chain/pnpm-lock.yaml

Everything outside `importers` (lockfileVersion, settings, packages, snapshots)
is preserved byte-for-byte in structure; only the importer map is replaced with
a single `.` entry taken from the named workspace importer.
"""
import sys

import yaml


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    src, importer_key, dest = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(src, encoding="utf-8") as f:
        lock = yaml.safe_load(f)
    importers = lock.get("importers") or {}
    if importer_key not in importers:
        print(
            f"importer {importer_key!r} not found; available: {sorted(importers)}",
            file=sys.stderr,
        )
        return 1
    lock["importers"] = {".": importers[importer_key]}
    with open(dest, "w", encoding="utf-8") as f:
        yaml.safe_dump(lock, f, sort_keys=False, default_flow_style=False)
    print(f"wrote {dest} with single '.' importer from {importer_key!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
