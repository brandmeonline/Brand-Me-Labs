# Brand.Me Repository Audit

> Verified 2026-08-31 by code-level audit of all four repositories in scope.
> Every claim below cites `file:line` or a reproducible command. Where a claim
> could not be verified in this environment, it says so.

## Scope and scale

| Repo | Tracked files | Python LOC | TS/TSX LOC | Merged PRs | Verdict |
|---|---:|---:|---:|---:|---|
| `Lux_Real_Estate` | 774 | 111,668 | 17,054 | 85 | **Mature.** The only hardened codebase in the set. |
| `Brand-Me-Labs` | 339 | 20,934 | 5,653 | 28 | **Partial.** Consent/policy/provenance real; the rest stub. |
| `Brand-Me-Codex` | 45 | 472 | 209 | 1 | **Skeleton.** A spec-shaped scaffold, no implementation. |
| `Lux_Real_Agency` | 1 | 0 | 0 | 1 | **Empty.** A README containing the string `# -Lux_Real_Agency`. |

Reproduce: `git ls-files '*.py' | xargs wc -l`.

## Finding 1 — the test gap is the whole story

| | Brand-Me-Labs | Lux_Real_Estate |
|---|---:|---:|
| Python test LOC | **533** | **45,463** |
| Ratio | 1× | **85×** |
| Test : non-test source | 0.026 : 1 | **0.69 : 1** |

Brand-Me-Labs' 533 lines are three real suites (`tests/test_consent_graph.py`,
`tests/test_provenance.py`, `tests/test_wardrobe.py`) plus placeholders.
`brandme-cube/tests/test_api.py` is, in full, a `test_placeholder()` that
asserts `True` with the real assertions commented out.

This is the single largest driver of remaining development time. It is also
the thing a lift-and-shift can most directly buy, because tests port with the
code they cover.

## Finding 2 — Brand.Me's Python CI cannot fail

`.github/workflows/ci-cd.yml`, job `test-core` — **every** step is suffixed
with `|| echo`:

```yaml
run: pip install -r requirements-dev.txt || echo "requirements-dev.txt not found"
run: ruff check . || echo "Ruff not configured yet"
run: black --check . || echo "Black not configured yet"
run: pytest tests/ -v || echo "Tests not implemented yet"        # :89
```

The job reports green unconditionally. It has never gated anything. Worse, the
step's `working-directory` is `./brandme-core`, and `brandme-core/tests/` does
not exist — so even without `|| echo` it would collect zero tests.

`requirements-dev.txt` referenced on the line above does not exist either.

### The workflow it lives in has never passed

Worse than a job that cannot fail: **`ci-cd.yml` has failed on every `main`
run recorded, back to January 2026.** Six consecutive red runs, including the
current `main` tip (`0f5f58a`). `module-regression.yml`'s only `main` run is
also red. Nobody is reading these results.

Three distinct root causes, all environmental and all fixable in a few lines.
None is a code defect; every one is workflow configuration:

| Check | Root cause | Fix |
|---|---|---|
| `regression` | `module-regression.yml:28-30` pins `pnpm/action-setup@v4` to `version: 8` while `package.json:28` declares `packageManager: pnpm@8.15.0`. v4 errors on the conflict and the job dies before any test body runs. | Delete the `with: version: 8` block; the action reads `packageManager`. |
| `Test Gateway (Node/TypeScript)` | `brandme-gateway/src/config/index.ts:57` parses a zod schema at module load. `oauthClientId`, `oauthClientSecret` and `jwtSecret` have no defaults and are unset in CI, so `rateLimiter.test.ts` throws on import via `config/logger.ts` and collects zero tests. | Supply test values in the CI job. The fail-closed schema is correct — do not weaken it. |
| `Security Scan` | `ci-cd.yml` declares **no `permissions:` block at all**, so `github/codeql-action/upload-sarif` (`:233`) cannot write results: `Resource not accessible by integration`. The action is also pinned to `@v2`, which GitHub has deprecated and which logs its own hard error. Trivy itself scans clean — the job fails *uploading*, not on a finding. | Add `permissions: {contents: read, security-events: write}`, bump the action to `@v3`, and fix the duplicate-run bug below. |

### Every workflow run happens twice, and the two disagree

`Security Scan` looked intermittent until the cause turned up. On commit
`8aa8354` it **passed and failed simultaneously** — check runs 99621124080
(success) and 99621110182 (failure), same SHA, two concurrent workflow runs.

`ci-cd.yml:8-19` triggers on both `push` to `claude/**` *and* `pull_request`
to `main`, and declares **no `concurrency:` block**. So every push to a
`claude/**` branch with an open PR fires the entire pipeline twice, at once,
on the same commit. That is why the notification stream carries exactly two
`regression` and two `Test Gateway` failures per push.

The two runs do not get the same token. GitHub restricts `security-events:
write` on `pull_request`-triggered runs, so the `push` run uploads its SARIF
and the `pull_request` run gets `Resource not accessible by integration`. Same
commit, same code, opposite results — and whichever finishes last is the one
shown.

This doubles CI cost on every push and makes check results non-deterministic.
Fix it with a `concurrency` group (as `Lux_Real_Estate/.github/workflows/ci.yml:11-13`
already does) and by narrowing the triggers so a branch with an open PR builds
once, not twice.

What is certain from the logs regardless: Trivy produced and validated its
SARIF, and the job failed in the upload step, not on a finding.

The gateway one is worth dwelling on: that schema is doing exactly the right thing.
It refuses to boot without credentials, which is the same fail-closed contract
the ported `brandme_foundation/runtime/config.py` encodes. The bug is that CI
never gave it any, and because the job was already red nobody noticed.

## Finding 3 — the Makefile is substantially aspirational

Five of twelve paths that `make` targets depend on are absent:

| Path | Present? | Breaks |
|---|---|---|
| `brandme-core/src` | ✗ | `lint-core`, `type-check-core` |
| `brandme-agents/src` | ✗ | `lint-agents`, `type-check-agents` |
| `brandme-core/tests` | ✗ | `test-core`, `test-unit`, `test-int` |
| `brandme-agents/tests` | ✗ | `test-agents` |
| `brandme-data/manage.py` | ✗ | `db-migrate`, `db-seed`, `db-reset` |
| `brandme-core/requirements-dev.txt` | ✗ | `install-core` |

`make test`, `make lint`, `make type-check`, and `make db-migrate` all fail on
a clean checkout. `make install` fails at `install-core`.

## Finding 4 — no tenancy anywhere in Brand.Me

```
$ grep -l "tenant\|org" brandme-data/schemas/*.sql
(no matches)
```

No table carries a tenant or organization column. There is no row-level
security, no cross-tenant query barrier, and no test asserting that one
owner's data cannot reach another. The identifier inventory across the repo is
931 × `user_id`, 195 × `owner_id`, 2 × `brand_id` — so `owner_id` is the de
facto tenant key, but nothing enforces it.

For contrast, Lux treats this as unmergeable: `gates/tenant_isolation.py:5-7`
— *"asserts that no agent / MCP server / query path can return the other
realtor's data. Failure here is unmergeable."* — backed by 886 lines in
`tests/test_isolation.py` and a dedicated `isolation` CI job.

**This is the highest-severity gap.** Retrofitting tenancy after data exists is
materially harder than adopting it now.

## Finding 5 — no migration runner

`brandme-data/` holds eight raw `.sql` files and no runner: no ordering
guarantee, no applied-migration ledger, no checksums, no advisory locking, no
rollback path. `make db-migrate` calls a `manage.py` that does not exist.

Lux's `services/runtime/migrate.py` is 3,007 lines implementing exactly this
(checksum ledger, advisory lock, statement timeouts, safe baseline
verification), covered by `tests/services/runtime/test_migrate_postgres.py`
against live Postgres in CI.

## Finding 6 — CLAUDE.md is accurate; the marketing docs are not

The repo's `CLAUDE.md` self-describes as ground truth against the status docs.
Spot-checks confirm it is honest:

- Orchestrator returns a fabricated `f"cardano_tx_{transfer_id[:16]}"`
  (`brandme-core/orchestrator/main.py:99`). **Confirmed.**
- Cube tests are placeholders. **Confirmed** (see Finding 1).
- 107 occurrences of `placeholder|TODO|FIXME|NotImplemented|stub` across the
  Python and TypeScript sources.

The README's "95% enterprise-ready" claim is not defensible and `CLAUDE.md`
already says so. Keep trusting `CLAUDE.md`.

## Finding 7 — the two dormant repos

- **`Lux_Real_Agency`** is an empty repo. It has one commit and a one-line
  README. Nothing to audit; decide whether to populate or archive it.
- **`Brand-Me-Codex`** is a 45-file scaffold (`policy_safety`, `ai_brain_hub`,
  `orchestrator`, a gateway, Helm charts, one Terraform file, one SQL
  migration). It duplicates Brand-Me-Labs' service names at ~2% of the size.
  Its stated purpose is *"a separate repo … to test different LLM developers."*
  It is a comparison harness, not a production line — treat it accordingly and
  do not let it drift into a second source of truth.

## What is genuinely real in Brand-Me-Labs

Not everything is stub. The following carry real implementation:

- `brandme_core/spanner/consent_graph.py` (494 lines) — hierarchical consent
  resolution with a documented precedence order and a friendship check.
- `brandme_core/spanner/provenance.py` (530 lines) — provenance chain reads
  and integrity verification.
- `brandme_core/mcp/tools.py` (923 lines) — the MCP tool surface.
- `brandme_core/firestore/wardrobe.py` (745 lines).
- `brandme_core/zk/proof_of_ownership.py` (632 lines) — framework real, proofs
  still stubbed behind `allow_stub_fallback`.
- The three passing test suites named in Finding 1.

The shared library `brandme_core/` is the healthiest part of the repo. The
per-service code above it is where the stubs concentrate.

## Severity summary

| # | Finding | Severity | Cheapest fix |
|---|---|---|---|
| 4 | No tenancy or isolation barrier | **Critical** | Adopt ported foundation now, before data volume |
| 2 | Python CI cannot fail, and its workflow has been red since January | **Critical** | Fix the two root causes above, then delete the `\|\| echo` suffixes |
| 1 | 85× test gap | **High** | Port Lux suites with the code they cover |
| 5 | No migration runner | **High** | Port Lux's migrate.py (Wave 3) |
| 3 | Makefile targets absent | **Medium** | Repair paths or delete dead targets |
| 6 | Status docs overstate readiness | **Low** | Already documented in CLAUDE.md |
| 7 | Two dormant repos | **Low** | Decide: populate or archive |

## Verification notes

- All file, line, and count claims were checked against the working tree at
  `Brand-Me-Labs@0f5f58a` and `Lux_Real_Estate@1c4cd20`.
- The CI history in Finding 2 was read from the GitHub Actions API: six
  `ci-cd.yml` runs on `main` (2026-01-20 → 2026-04-27), all `failure`. The two
  root causes were read from the job logs of runs 33431603905 and 33431603933,
  and reproduce identically across two runs of this branch.
- **Lux's test suite was not executed.** Its dependencies (pytest, Postgres,
  Playwright) are not installed in this environment, so "hardened" rests on
  code inspection plus its CI configuration (8 jobs including live-Postgres
  persistence, browser E2E, a tenant-isolation gate, and merge gates), not on
  an observed green run here.
- The ported foundation described in `LUX_LIFT_AND_SHIFT.md` **was** executed:
  62 tests pass, and the port was mutation-checked. See that document.
