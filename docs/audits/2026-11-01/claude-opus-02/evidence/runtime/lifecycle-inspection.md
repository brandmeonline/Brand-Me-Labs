# Lifecycle inspection (before any install or run)

- Repository: brandmeonline/Brand-Me-Labs
- Commit audited: `ed19dc151d103b108cf972e6d37971c55d5dcf60` (remote `main`, "Merge pull request #68 from brandmeonline/mia/pipeline-seed-20261030")
- Audit date: 2026-11-01. Evidence collected by the second (independent) audit run.
- Working copy: an isolated git worktree of the audit clone at
  `/tmp/claude-0/-home-user-Brand-Me-Labs/1bf61dcf-0f4d-53ea-917a-a94fd3490bcc/scratchpad/wt-main`
  (`git rev-parse HEAD` = `ed19dc151d103b108cf972e6d37971c55d5dcf60`). The primary checkout
  `/home/user/Brand-Me-Labs` received no `node_modules`, no venv and no source change (`git status --short`
  shows only the untracked `docs/audits/` output directory).
- Rules observed: no application source modified; nothing committed or pushed; synthetic data only; no
  production credentials; no outbound calls other than package registries through the pre-configured proxy.

## 1. Repo-authored lifecycle scripts

| Package | `preinstall` | `postinstall` | `prepare` | Other notes |
|---|---|---|---|---|
| root `package.json` (`brandme-monorepo`) | none | none | none | Only task scripts (`check`, `dev`, `smoke`, `build`, `test`, ...). `packageManager: pnpm@10.34.6`, `engines.node >=20.0.0 <25`. |
| `brandme-gateway` (`@brandme/gateway`) | none | none | none | `test: vitest`, `lint: eslint src --ext .ts`, `type-check: tsc --noEmit`, `build: tsc`. |
| `brandme-chain` (`@brandme/chain`) | none | none | none | `compact:fetch` runs `scripts/fetch-compactc.sh` (downloads the Compact compiler zip by URL from `contracts/toolchain.json`, sha256-verified). **Not a lifecycle hook; only runs when invoked explicitly. Not run in this audit.** |
| `brandme-console` (`@brandme/console`) | none | none | none | `lint: next lint` (interactive when no ESLint config exists, see commands.md). |
| `brandme-frontend` | none | none | none | `test:ui`, `test:gateway` (node --test), `test:browser` (Playwright against a running dev server). |
| `packages/contracts`, `packages/design-system`, `packages/firestore-rules`, `packages/provider-contracts`, `scripts/assets` | none | none | none | `node --test` suites and generators. |

Conclusion: **no repo-authored install-time hook exists**, so `pnpm install --frozen-lockfile` was run without
`--ignore-scripts`, exactly as CI does (`.github/workflows/ci-cd.yml:92,251`).

## 2. Dependency build scripts gated by pnpm 10

`pnpm-workspace.yaml` allowlists dependency lifecycle scripts (`onlyBuiltDependencies`): `esbuild`,
`unrs-resolver`, `protobufjs`, `@parcel/watcher`, `sharp`. Observed during install: `protobufjs postinstall`,
`esbuild@0.28.2 install.js`, `esbuild@0.25.12 install.js`, `unrs-resolver postinstall` ran; pnpm reported
"Ignored build scripts: @firebase/util@1.15.3, classic-level@3.0.0, cpu-features@0.0.10, msgpackr-extract@3.0.4,
ssh2@1.17.0". These are third-party package scripts that at most fetch platform binaries from the npm registry;
they were accepted because the repository's own workspace policy and CI accept them.

## 3. Workspace / toolchain pins

- `pnpm-workspace.yaml` packages: `brandme-gateway`, `brandme-chain`, `brandme-console`, `brandme-frontend`, `packages/*`, `scripts/assets`; `engineStrict: false`; `overrides` for `@midnight-ntwrk/*`, `tinypool`, `minimatch@9`, `postcss@8`, `@babel/core@7`, `@grpc/grpc-js@1.9`, `body-parser@1`, `fast-uri@3`, `qs@6`; `packageExtensions` for `lucide-react`, `framer-motion`, `@react-three/fiber`, `next@15.5.28`.
- `.npmrc`: absent. `.husky/`: absent.
- `.nvmrc` and `.node-version`: `24.21.0`. `.python-version`/`.tool-versions`: absent. Python 3.11 is required by `scripts/python/requirements.in` and `scripts/brandme.mjs checkRuntimes()` (line 106-107).
- `pnpm-lock.yaml`: `lockfileVersion: '9.0'`, importers for the 9 workspace packages.
- `pytest.ini`: `asyncio_mode = auto`, `pythonpath = .`.

## 4. Repo scripts that download or execute remote content

| Script | What it fetches | Runs automatically? | Run in this audit? |
|---|---|---|---|
| `scripts/brandme.mjs check` (`provisionEmulators`, lines 353-425) | Pinned Firestore, Pub/Sub and GCS emulator binaries into `.cache/` via `scripts/python/fetch_*_emulator.py` (sha256-verified) | Yes, when `pnpm check` runs without `--no-provision` | **No** — run as `pnpm check --no-provision` (probe only) |
| `scripts/python/fetch_firestore_emulator.py`, `fetch_pubsub_emulator.py`, `fetch_gcs_emulator.py`, `_fetch.py` | Google emulator archives | Only via the above or CI | No |
| `brandme-chain/scripts/fetch-compactc.sh` (`pnpm compact:fetch`) | Compact compiler zip from `contracts/toolchain.json` URL | No (explicit script) | No |
| `scripts/validate-helm.sh` | helm and kubeconform release tarballs (checksummed) | No (explicit script) | No |
| `.mcp.json` | `npx -y @21st-dev/magic@latest` MCP server (needs `MAGIC_API_KEY`) | Only when a Claude Code session loads project MCP servers | No |
| `.claude/hooks/session-start.sh` (wired by `.claude/settings.json` `SessionStart`) | Reads gitignored `.claude/.env.local` and exports its lines into `$CLAUDE_ENV_FILE` | On Claude Code session start only | Not relevant to the build; exits 0 when the file is absent |
| `docker-compose.yml` `node-install`/`gateway`/`consumer` | `corepack enable && pnpm install --frozen-lockfile` inside `node:24.21.0-bookworm-slim` | Only under Docker | No (no Docker daemon) |

No script executes arbitrary remote code at install time. The `check` provisioning step is the only
automatic downloader and was disabled with `--no-provision`.

## 5. Makefile targets (informational)

`help install install-gateway install-core install-agents install-chain install-console dev-up dev-down dev-logs
db-migrate db-seed db-reset test test-core test-gateway test-chain lint ... format ... type-check ... build-all
... push-all ... deploy-dev deploy-prod clean clean-all infra-init infra-plan infra-apply infra-destroy`.
`make test` = `pnpm check`; `make test-core` = `$(PYTHON) -m pytest tests -q --timeout=300 -ra --continue-on-collection-errors`.
Note: `install-core`/`install-agents`/`lint-core`/`type-check-core` reference `brandme-core/requirements.txt`,
`src/` directories that do not match the current tree (not exercised here).

## 6. Toolchain available in this environment vs. pins

| Tool | Available | Pin / CI | Note |
|---|---|---|---|
| node | v22.23.4 | `.nvmrc` 24.21.0; `engines >=20 <25` | Within `engines`; **not** the exact pinned minor. `scripts/brandme.mjs checkRuntimes()` (used by `setup`/`dev`, not `check`) would flag it. Recorded as a toolchain deviation. |
| pnpm | 10.34.6 | `packageManager` pnpm@10.34.6 | Exact match. |
| python | 3.11.18 (`/usr/bin/python3.11`); default `python3` is 3.13.18 | 3.11 | venv built with `uv 0.11.32` from `scripts/python/requirements.lock` (hashed) at `<scratchpad>/venv`, outside the worktree. |
| docker | CLI 29.9.2, **daemon not running** (`/var/run/docker.sock` missing) | Spanner emulator image in compose/CI | Spanner emulator could not be started. |
| java | openjdk 21.0.12.1 | needed by Firestore/Pub/Sub emulators | Present but emulators not fetched (no provisioning). |
| playwright | 1.63.0 pre-installed, chromium-1243 at `/opt/pw-browsers` | repo pins playwright@1.58.2 for its own browser checks | Used only for audit screenshots; `playwright install` was **not** run. |
| git | 2.43.0 | — | — |
