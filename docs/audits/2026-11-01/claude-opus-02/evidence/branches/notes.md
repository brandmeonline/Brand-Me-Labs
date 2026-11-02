# Branch / history evidence — brandmeonline/Brand-Me-Labs

- Audit date: 2026-11-01. Baseline `origin/main` = `ed19dc151d103b108cf972e6d37971c55d5dcf60` (confirmed: `git rev-parse origin/main`).
- Source: isolated full-history clone (no checkout) with `refs/remotes/origin/*` and `refs/pr/1..70`; git 2.43.0. No ref or working-tree file in the repository checkout was modified. No existing audit document was read; `git grep` hits were restricted to path:line and no `docs/audits/` path matched any grep.
- GitHub data came from the read-only MCP tools `list_pull_requests` (state=all, 71 PRs returned: #1–#37, #39–#72) and `pull_request_read` (get) for #29, #63, #66, #70, #71, #72. The list payload's `merged` boolean is unpopulated; merge state below is `merged_at != null` plus git ancestry.
- Companion files: `branch-inventory.json` (machine-readable, 36 rows), `commands.log` (every command with exit code and trimmed output). Scratch intermediates (patch-id cache, equiv.json, squash-check.txt) live under the session scratchpad `agent-branches/`.
- Vocabulary: **confirmed** = direct git/GitHub evidence quoted below; **unverified** = not checked; **n/a** = does not apply.

## Headline results

1. **No lost work in any squash-merged branch (confirmed).** For every merged PR whose head is not an ancestor of main (#18–#25, #26, #27, #28, #39–#50), the patch-id of the main squash commit equals the patch-id of `merge-base..head`, and `git diff <head> <squash> -- <touched paths>` is empty. The nine `codex/*-2026102x` branches, `fix/property-test-vacuity-guard-flake` and `codex/explain-execution-details-and-next-steps` therefore have their final content in main byte-for-byte; the per-commit "partial" readings from the added-line heuristic are later main edits or intra-branch supersession.
2. **Unique content NOT in main exists on exactly six branches (confirmed)**, all behind open PRs except one: `claude/opus-consumer-domains-1csp2g` (#66), `claude/midnight-rights-lifecycle-yhfyyu` (#70), `codex/consumer-design-preview` (#63), `claude/amazing-goodall-ntrljq` (#71), `claude/brand-me-lux-foundations-audit-8zywr3` (#29, draft since 2026-08-31), and the four un-PR'd design-audit commits on `claude/setup-design-system-cli-6iovG` (`.claude/skills/design-audit/**`, 23 files, blobs found nowhere in main).
3. **Migration collision (confirmed).** `V016_consumer_design.sql` (#66) and `V016_rights_transfer_invites.sql` (#70) share prefix `V016`. Both files can coexist in the directory (distinct names; git merge-tree reports no conflict on the .sql files), but `runner.py:98-99` raises `MigrationError("duplicate migration version V016")` at load, and the two branches conflict textually in `brandme-data/spanner/migrations/README.md` and `tests/foundation/test_migrations.py` (RESERVED dict: `16: "consumer_design"` vs `16: "rights_transfer_invites"`).
4. Closed-but-unmerged PRs: #2, #13, #37, #55. #13 has an empty diff; #37 and #55 have their intent already in main (confirmed by file contents); #2 (2025-10-25 stubs, two files) is the only "possible lost work", of low materiality: both paths exist in main with independently written content.
5. No tags (local or `ls-remote`), no `.gitmodules` anywhere in main history, no LFS (`filter=lfs` absent on every ref; the only `.gitattributes` sets `eol=lf`). No commit on main has a subject starting with `Revert`.
6. A 36th branch, `claude/exciting-hypatia-wl48op` (PR #72, draft, 1 commit), appeared in the clone at 15:10 UTC during this run; it is reported but was not among the 35 at start.

## Per-branch summary

Columns: ahead/behind are `git rev-list --left-right --count origin/main...<ref>` (behind = main-only, ahead = branch-only); cherry = `git cherry origin/main <ref>` (+ not patch-equivalent, - patch-equivalent). "Content in main" is the branch-level verdict.

| branch | tip | ahead / behind | cherry +/- | PRs (head) | content in main | class |
|---|---|---|---|---|---|---|
| bench/astra-consumer-ui-20261005 | cccfe7b 2026-10-24 | 0 / 90 | 0/0 | #56 merged | all (ancestor) | PRESERVE_THEN_RETIRE (workflow trigger consumer) |
| bench/astra-spatial-ar-20261005 | 1413178 2026-10-30 | 0 / 5 | 0/0 | #36, #60, #69 merged | all (ancestor) | PRESERVE_THEN_RETIRE (workflow trigger consumer) |
| bench/opus-commerce-agents-20261005 | 7c61afd 2026-10-06 | 0 / 344 | 0/0 | base of #35 | all (ancestor) | DELETION_CANDIDATE |
| bench/opus-consumer-domains-20261005 | d839267 2026-10-07 | 0 / 365 | 0/0 | base of #32 | all (ancestor) | DELETION_CANDIDATE |
| bench/opus-foundation-20261005 | 67327e4 2026-10-05 | 0 / 357 | 0/0 | base of #33 | all (ancestor) | DELETION_CANDIDATE |
| bench/opus-midnight-rights-20261005 | 44aacea 2026-10-06 | 0 / 356 | 0/0 | base of #34 | all (ancestor) | DELETION_CANDIDATE |
| claude/amazing-goodall-ntrljq | 8360813 2026-11-01 | 2 / 0 | 2/0 | #71 open draft | none | KEEP |
| claude/brand-me-lux-foundations-audit-8zywr3 | eed6737 2026-08-31 | 5 / 370 | 5/0 | #29 open draft | none (22/24 paths absent) | INTEGRATE (low) |
| claude/ci-repair-workflows | 512021c 2026-08-31 | 0 / 369 | 0/0 | #30 merged | all (ancestor) | DELETION_CANDIDATE |
| claude/exciting-hypatia-wl48op (extra) | e033950 2026-11-01 | 1 / 0 | 1/0 | #72 open draft | none | KEEP |
| claude/midnight-rights-lifecycle-yhfyyu | a05f2e0 2026-10-30 | 5 / 0 | 5/0 | #70 open draft; #34 #40 #41 #54 merged | none for the 5 commits | KEEP |
| claude/opus-commerce-agents-setup-szpmf7 | 161f6eb 2026-10-25 | 0 / 69 | 0/0 | #35 #51 #64 merged | all (ancestor) | DELETION_CANDIDATE (lane-reuse caveat) |
| claude/opus-consumer-domains-1csp2g | babb360 2026-10-30 | 18 / 17 | 16/0 | #66 open; #32 #52 #59 #61 merged | none for the 16 commits | KEEP |
| claude/opus-foundation-w00-2hgiw5 | f5c906a 2026-10-30 | 0 / 18 | 0/0 | #33 #53 #58 #62 merged | all (ancestor) | DELETION_CANDIDATE (lane-reuse caveat) |
| claude/setup-design-system-cli-6iovG | 8b9bd4a 2026-06-11 | 8 / 373 | 6/2 | #26 merged (squash) | partial: #26 head all; 4 later commits none | PRESERVE_THEN_RETIRE |
| codex/chain-projection-worker-20261022 | e96356e 2026-10-22 | 1 / 293 | 0/1 | #45 merged (squash 74e1375) | all (exact squash) | DELETION_CANDIDATE |
| codex/console-contract-publication | 06d8fc1 2026-10-24 | 0 / 88 | 0/0 | #65 merged | all (ancestor) | DELETION_CANDIDATE |
| codex/consumer-design-preview | 0ff12fb 2026-10-30 | 20 / 87 | 13/0 | #63 open draft | none (23/23 paths differ) | KEEP |
| codex/critical-dependency-repairs-20261022 | 542b52c 2026-10-22 | 2 / 292 | 2/0 | #46 merged (squash fbadf01) | all (exact squash) | DELETION_CANDIDATE |
| codex/docker-pipeline-20261022 | a5373d5 2026-10-22 | 7 / 296 | 7/0 | #42 merged (squash 1ac8f97) | all (exact squash) | DELETION_CANDIDATE |
| codex/durable-chain-reconciliation-20261022 | e2dcbdd 2026-10-22 | 2 / 294 | 2/0 | #44 merged (squash 238f65a) | all (exact squash) | DELETION_CANDIDATE |
| codex/durable-outbox-pubsub-20261022 | 6536778 2026-10-22 | 2 / 291 | 2/0 | #47 merged (squash 1a4cfd1) | all (exact squash) | DELETION_CANDIDATE |
| codex/explain-execution-details-and-next-steps | 15ae7bf 2026-04-26 | 1 / 371 | 0/1 | #28 merged (squash 0f5f58a) | all (exact squash) | DELETION_CANDIDATE |
| codex/midnight-integration-20261022 | 32e63d4 2026-10-22 | 3 / 295 | 3/0 | #43 merged (squash a2e625a) | all (exact squash) | DELETION_CANDIDATE |
| codex/privacy-recovery-safety-20261023 | e6274ef 2026-10-22 | 2 / 290 | 2/0 | #48 merged (squash f4a4015) | all (exact squash) | DELETION_CANDIDATE |
| codex/rights-export-worker | 02297b2 2026-10-23 | 2 / 288 | 2/0 | #50 merged (squash 5174ec2) | all (exact squash) | DELETION_CANDIDATE |
| codex/rights-privacy-read-api | 10a4683 2026-10-22 | 1 / 289 | 0/1 | #49 merged (squash 20bf3e9) | all (exact squash) | DELETION_CANDIDATE |
| docs/brandme-full-experience-2026-10-05 | b313731 2026-10-23 | 0 / 357 | 0/0 | #31 merged; base of #36 | all (ancestor) | DELETION_CANDIDATE (medium) |
| fix/property-test-vacuity-guard-flake | a699331 2026-10-10 | 1 / 300 | 0/1 | #39 merged (squash 49623e4) | all (exact squash) | DELETION_CANDIDATE |
| main | ed19dc1 2026-10-30 | 0 / 0 | 0/0 | — | — | KEEP |
| mia/next-plans-20261025 | 057320d 2026-10-25 | 0 / 78 | 0/0 | #67 merged | all (ancestor) | DELETION_CANDIDATE |
| mia/orchestration-20261023 | 27f3215 2026-10-23 | 0 / 276 | 0/0 | #57 merged | all (ancestor) | DELETION_CANDIDATE |
| mia/pipeline-seed-20261030 | 5e9eceb 2026-10-30 | 0 / 14 | 0/0 | #68 merged | all (ancestor) | DELETION_CANDIDATE |
| triage/pnpm-version-conflict-20261023 | 1144700 2026-10-23 | 1 / 363 | 0/1 | #55 closed unmerged | intent in main (pin absent) | DELETION_CANDIDATE |
| triage/pnpm-workspace-frontend-20261008 | 64d5fd6 2026-10-08 | 1 / 368 | 1/0 | #37 closed unmerged | intent in main (workspace + lockfile importer) | DELETION_CANDIDATE |
| w11/integration-20261008 | bec80b1 2026-10-08 | 0 / 319 | 0/0 | none | all (ancestor) | DELETION_CANDIDATE |

All 16 zero-ahead branches were additionally confirmed with `git merge-base --is-ancestor <ref> origin/main` (exit 0 for each).

### Notes on specific branches

- **claude/opus-consumer-domains-1csp2g** (#66): 16 non-merge + 2 merge commits (`a89df83` merges main 97d5447, `9770927` merges main 22ff053). Touches `brandme-console, brandme-data, brandme-gateway, brandme_core, docs, tests`; adds `brandme-data/spanner/migrations/V016_consumer_design.sql`. GitHub head == clone tip (`babb3604…`). `git merge-tree --write-tree origin/main <ref>` is clean on its own.
- **claude/midnight-rights-lifecycle-yhfyyu** (#70): 5 commits (Stages 11–15). Touches `brandme-chain, brandme-data, brandme-gateway, brandme_core, docs, tests` and root; adds `V016_rights_transfer_invites.sql`. GitHub head == clone tip (`a05f2e03…`), mergeable_state `clean` on its own. Previous PRs from this branch name (#34 into bench, #40, #41, #54 into main) are merged; #40/#41 were squashes (exact, see table in H).
- **codex/consumer-design-preview** (#63): 13 non-merge commits plus 7 merges pulling in `bench/astra-consumer-ui` history and `codex/console-contract-publication`; touches `brandme-frontend, docs`. 11 of 23 touched paths are absent in main (e.g. `brandme-frontend/app/social/{now,flow,editorial}/page.tsx`, `features/persona/persona-card.tsx`, `features/social/horizons.tsx`, `use-decision-heartbeat.ts`, `lib/client/haptic-preferences.ts`, three `verify-*.mjs` test scripts). Own tree references itself at `docs/build/status/astra-consumer-ui.md:455,656`.
- **claude/amazing-goodall-ntrljq** (#71): `45e157f` docs plan (`docs/build/stripe-connect-plan.md`, absent in main) and `8360813` Stripe Connect code/tests (9 files; 3 absent in main). No overlap with any other open branch.
- **claude/brand-me-lux-foundations-audit-8zywr3** (#29): 5 commits from 2026-08-31 adding `brandme_foundation/` (15 files), `docs/audit/{BRANDME_AUDIT,LUX_LIFT_AND_SHIFT}.md`, `.github/workflows/foundation.yml`, `tests/foundation/test_{broker,observability,runtime_config,tenancy}.py`, and editing `CLAUDE.md`. Check C: every added blob except the empty `tests/foundation/__init__.py` is absent from main at any path; `.github/workflows/foundation.yml` does not exist on main (main has chain-tests, ci-cd, consumer-ui, deploy-validate, module-regression, spatial-validation, workspace-guard). `git merge-tree` onto main is clean despite 370 commits of drift; it overlaps no other open PR.
- **claude/setup-design-system-cli-6iovG**: 8 unique commits. `8dd7aad`+`1733fcc` = PR #26 head, exact-squashed into main `2faae4c` (34 touched paths, tree diff 0). `d6207ad` and `e758afb` are patch-equivalent to main's `4335e27` (#27) and `0f5f58a` (#28) (cherry `-`). `12f5ee7`, `425918c`, `6de84d4`, `8b9bd4a` (2026-06-09..11) add the `design-audit` skill and its outputs; check C shows all 23 of those blobs absent from main at any path and never added on main. These four commits were never in any PR (PR #26 head is `1733fcc`).
- **codex/* (2026-10-22/23)**: see check F. All exact squashes; merge-bases chain (each branch's merge-base is the previous PR's squash commit), so `squash^ == merge-base` for every one.
- **bench/astra-consumer-ui / bench/astra-spatial-ar**: zero unique commits, but `.github/workflows/consumer-ui.yml:7` and `.github/workflows/spatial-validation.yml:5` list them as push-trigger branches, and `scripts/assets/evidence/round2-summary.json:5` records the spatial branch name. Deleting them makes those triggers dead; nothing in git is lost.
- **triage/pnpm-workspace-frontend-20261008** (#37 closed unmerged): adds `- 'brandme-frontend'` to `pnpm-workspace.yaml` and a lockfile importer. main's `pnpm-workspace.yaml` already lists `brandme-frontend` and `pnpm-lock.yaml:252` has `brandme-frontend:`; only regenerated lockfile bytes differ (132/246 added lines literally present).
- **triage/pnpm-version-conflict-20261023** (#55 closed unmerged, base was `bench/astra-spatial-ar`): deletes `with: version: 8` under `pnpm/action-setup` in `module-regression.yml`. main's file (`:39`) uses `pnpm/action-setup@v4` with no `with:` block; `git cherry` reports `-`. Intent already in main.
- **Lane-reuse caveat** for `claude/opus-commerce-agents-setup-szpmf7` and `claude/opus-foundation-w00-2hgiw5`: `docs/build/status/opus-commerce-agents.md:50` and `opus-foundation.md:134,174` describe these as session-designated working branches restarted from main each round. Zero unique commits today; a future round would recreate the name.

## Required checks

### A. Squash-merge / content detection for every branch with cherry+ > 0

Method per commit C (non-merge): `git diff --name-status C^ C`; `git diff-tree -p C | git patch-id --stable` compared with a cache of patch-ids for all 363 non-merge commits of `origin/main` (one empty-diff root commit skipped); `git diff --name-only C origin/main -- <paths>`; and an added/removed-line presence check against `origin/main:<path>`. Results in `branch-inventory.json` → `unique_commits[].method`. Branch-level, the decisive test for merged PRs was the squash comparison (F and H tables). Summary of branches with cherry+ > 0:

| branch | per-commit heuristic | branch-level verdict |
|---|---|---|
| claude/amazing-goodall-ntrljq | none / partial (22/988 added lines present) | not in main — open #71 |
| claude/brand-me-lux-foundations-audit-8zywr3 | 1/2492 added lines present (the empty `__init__.py`) | not in main — open #29 |
| claude/midnight-rights-lifecycle-yhfyyu | partial/none (≤24/1403 lines present per commit) | not in main — open #70 |
| claude/opus-consumer-domains-1csp2g | partial/none | not in main — open #66 |
| claude/setup-design-system-cli-6iovG | 8dd7aad all; 1733fcc 80/81; d6207ad/e758afb patch-equivalent; 4 design-audit commits none | #26 head exact squash; 4 commits not in main |
| codex/consumer-design-preview | partial/none | not in main — open #63 |
| codex/critical-dependency-repairs, docker-pipeline, durable-chain-reconciliation, durable-outbox-pubsub, midnight-integration, privacy-recovery-safety, rights-export-worker | partial (≥ 93% added lines present; residue = later main edits) | exact squash (F) |
| triage/pnpm-workspace-frontend-20261008 | 132/246 added lines present | intent in main (see notes) |

### B. Migration version collision

`git ls-tree --name-only <rev> brandme-data/spanner/migrations/`:

- `origin/main`: README.md, V001_identity … V015_commerce_quote_terms.sql, runner.py (15 migrations).
- `origin/claude/opus-consumer-domains-1csp2g`: main's 15 + `V016_consumer_design.sql` (header: "V016 consumer design alignment (lane: opus-consumer-domains; Ultra plan 02 items 2-7)"; ALTERs `Decisions`, `MemberReports`, creates `DecisionComments`, …).
- `origin/claude/midnight-rights-lifecycle-yhfyyu`: main's 15 + `V016_rights_transfer_invites.sql` (header: "V016: transfer invites and fixed offer terms (lane: opus-midnight-rights)"; `ALTER TABLE TransferIntents ADD COLUMN contract_address …`).

Collision: same `V016` prefix, different filenames (**confirmed**). Could both files coexist in one directory? As files, yes (distinct names; `git merge-tree --write-tree` of the two branches reports conflicts only in `brandme-data/spanner/migrations/README.md` and `tests/foundation/test_migrations.py`, not in the .sql files). At runtime, no: `runner.py` at `origin/main` (quoted with line numbers):

```
 91	def load_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
 92	    found: dict[int, Migration] = {}
 93	    for path in sorted(directory.glob("*.sql")):
 94	        m = FILE_RE.match(path.name)
 ...
 97	        version = int(m.group(1))
 98	        if version in found:
 99	            raise MigrationError(f"duplicate migration version V{version:03d}")
```

`FILE_RE = re.compile(r"^V(\d{3})_([a-z0-9_]+)\.sql$")` (line 36). Also relevant: `plan()` lines 195–202 refuse out-of-order pending versions unless `--allow-out-of-order`, which `main()` line 294–295 refuses in sandbox/production. `tests/foundation/test_migrations.py:23-27` `RESERVED` ends `15: "commerce_quote_terms"}` on main, `16: "consumer_design"}` on #66, `16: "rights_transfer_invites"}` on #70 — the same dict line, hence the merge conflict. The README reservation row (line 14) likewise differs; #70's README also adds a line 36 describing V016 as midnight-rights. The runner docstring (lines 18–21) lists reservations only through V013 (stale relative to V014/V015 on main).

### C. `claude/brand-me-lux-foundations-audit-8zywr3` and `claude/setup-design-system-cli-6iovG`

Method: `git diff --name-status <merge-base> <ref>`; branch blob via `git rev-parse <ref>:<path>`; presence of path in main via `git cat-file -e origin/main:<path>`; blob search across `git ls-tree -r origin/main`; first add on main via `git log origin/main --diff-filter=A -- <path>`. Full per-file table in `commands.log` (checkC).

- lux-foundations (24 files): 22 added files have no equivalent blob anywhere in main and the paths were never added on main (`brandme_foundation/**` 15, `docs/audit/*` 2, `.github/workflows/foundation.yml`, `tests/foundation/test_*.py` 4). `tests/foundation/__init__.py` is the empty blob (`e69de29`), present in main. `CLAUDE.md` is modified (branch blob ≠ main blob; 17/18 added lines absent from main's CLAUDE.md).
- setup-design-system (87 files vs merge-base 8f8a2b7): 59 files are byte-identical to main (same blob at same path: `.claude/skills/ui-ux-pro-max/**`, `.claude/settings.json`, `.claude/hooks/session-start.sh`, `.mcp.json`, `scripts/regression/**`, `pytest.ini`, …). 23 files under `.claude/skills/design-audit/**` have no blob match anywhere in main and were never added on main. The remaining 5 differ because main moved on (`CLAUDE.md`, `PLAN.md`, `README.md`, `.gitignore`, `.github/workflows/module-regression.yml`, `tests/conftest.py`, `brandme_core/mcp/tools.py`, etc.) or the path was later deleted on main (`brandme-chain/src/services/blockchain.ts`, `cardano-wallet.ts`, `tests/integration/cardano-testnet.test.ts`). These "modified" paths come from the branch's copies of #27/#28, which are patch-equivalent to main (cherry `-`).

### D. `bench/*` consumers

`git grep -n -e 'bench/' origin/main -- .github scripts docs '*.md' '*.yml' '*.yaml' '*.json' '*.mjs' '*.sh'` → 46 hits. Non-docs hits (the ones that execute):

- `.github/workflows/consumer-ui.yml:7` — `branches: ['bench/astra-consumer-ui-20261005']`
- `.github/workflows/spatial-validation.yml:5` — `branches: ['bench/astra-spatial-ar-20261005']`
- `.github/workflows/workspace-guard.yml:14` — comment only ("No branch filter on purpose: lane PRs into bench/* and docs/* bases …")
- `scripts/assets/evidence/round2-summary.json:5` — `"branch": "bench/astra-spatial-ar-20261005"` (evidence record)

Docs hits: `docs/build/orchestration/{oneshot,ultra}-plan-03-*.md` (6), `docs/build/status/{astra-consumer-ui,astra-spatial-ar,opus-commerce-agents,opus-consumer-domains,opus-foundation,opus-midnight-rights}.md` (33 lines), `docs/build/workspace-governance.md:56,129,146,147`. Full list with line numbers in `commands.log` (check D).

### E. `mia/*`, `triage/*`, `fix/*`, `w11/*`, `docs/brandme-full-experience-2026-10-05`

Consumers (main tree / own tree): `mia/next-plans-20261025` → `docs/build/orchestration/next-plans-20261025.md:75` (both trees); `mia/orchestration-20261023`, `mia/pipeline-seed-20261030`, `w11/integration-20261008`, `fix/property-test-vacuity-guard-flake` → none; `triage/pnpm-version-conflict-20261023` → `docs/build/workspace-governance.md:131` (main); `triage/pnpm-workspace-frontend-20261008` → `docs/build/workspace-governance.md:133` (main); `docs/brandme-full-experience-2026-10-05` → "Base:" lines in six `docs/build/status/*.md` files (main) and `astra-spatial-ar.md:4,233,274` (own tree). Content: `mia/*`, `w11/*`, `docs/*` are ancestors of main (0 ahead). `fix/*` exact squash (49623e4). `triage/*` intent present (see notes above).

### F. `codex/*` branches dated 20261022/23 — hunks not in main

Per branch: PR, squash commit on main, `squash^ == merge-base`, touched paths, `git diff <tip> <squash> -- <touched paths>` differing count, range patch-id equality.

| branch | PR | squash | parent==mb | touched | tip vs squash differ | patch-id equal |
|---|---|---|---|---|---|---|
| codex/docker-pipeline-20261022 | #42 | 1ac8f97 | yes | 13 | 0 | yes |
| codex/midnight-integration-20261022 | #43 | a2e625a | yes | 40 | 0 | yes |
| codex/durable-chain-reconciliation-20261022 | #44 | 238f65a | yes | 31 | 0 | yes |
| codex/chain-projection-worker-20261022 | #45 | 74e1375 | yes | 23 | 0 | yes |
| codex/critical-dependency-repairs-20261022 | #46 | fbadf01 | yes | 12 | 0 | yes |
| codex/durable-outbox-pubsub-20261022 | #47 | 1a4cfd1 | yes | 18 | 0 | yes |
| codex/privacy-recovery-safety-20261023 | #48 | f4a4015 | yes | 10 | 0 | yes |
| codex/rights-privacy-read-api | #49 | 20bf3e9 | yes | 29 | 0 | yes |
| codex/rights-export-worker | #50 | 5174ec2 | yes | 30 | 0 | yes |

**Hunks NOT in main: none, for all nine (confirmed).** Each branch's entire range diff is patch-identical to its squash commit and the branch tip's tree equals the squash tree on every touched path. The per-commit heuristic residue (e.g. `brandme-chain/src/midnight/spanner-store.ts` 2 removed lines "still in main", `pnpm-lock.yaml` 350/975 removed lines still present for #46, `.github/workflows/ci-cd.yml` lines for #42) is explained by later main commits re-editing those files after the squash (main has 288–296 commits past each merge-base), not by missing content. Note on cherry: for #45 and #49 (single-commit branches) `git cherry` already reports `-`; for multi-commit branches cherry reports `+` per commit because the squash combines them.

### G. Open PRs

From GitHub (`list_pull_requests`, `pull_request_read`):

| PR | title (short) | head ref | head sha | base | draft | mergeable_state | head == clone tip |
|---|---|---|---|---|---|---|---|
| #29 | Audit all repos; lift Lux platform foundation | claude/brand-me-lux-foundations-audit-8zywr3 | eed6737062da451a38114f8002159c1bed0e5cb5 | main | yes | unstable | yes |
| #63 | feat(consumer): preview three rooms… | codex/consumer-design-preview | 0ff12fbdbce2a8b4ea1391a02ef3ea821ae6a420 | main | yes | unstable | yes |
| #66 | consumer domains: Now, Flow, loyalty… | claude/opus-consumer-domains-1csp2g | babb3604ae2f33018edf0ad45270887d4b01945b | main | no | unstable | yes |
| #70 | midnight-rights round 03… | claude/midnight-rights-lifecycle-yhfyyu | a05f2e03e58e55cc2b392b8abc7b19f59659f820 | main | yes | clean | yes |
| #71 | Stripe Connect: plan + brands flow | claude/amazing-goodall-ntrljq | 8360813e238e20f78656700340c6c05927107ae0 | main | yes | unstable | yes |
| #72 | Pin follow-redirects and gaxios overrides | claude/exciting-hypatia-wl48op | e033950bc6c572616cfc0902d96a5c7ecaa78ea3 | main | yes | unstable | yes (ref appeared mid-run; no `refs/pr/72`) |

`refs/pr/63`, `/66`, `/70`, `/71`, `/29` in the clone equal the GitHub heads. PR #38 does not exist as a PR (number skipped by GitHub). `mergeable_state` for #29 and #72 came from `pull_request_read`, not the list.

### H. Closed-but-unmerged PRs

Of 65 closed PRs, 61 have `merged_at` set. Closed with `merged_at = null`: **#2, #13, #37, #55**.

| PR | title | head sha | closed | head ancestor of main | content check |
|---|---|---|---|---|---|
| #2 | Add policy check service and orchestrator worker stubs | 4e7a0bb74e | 2025-10-25 | no | 2 files (`brandme-core/orchestrator/worker.py` 230 lines, `brandme-core/policy/main.py` 61 lines); both paths exist in main with different blobs (first added by `1da0769`, last touched 2026-10-23); only 26/202 and 17/47 non-blank lines match exactly. **Possible lost work (low materiality: 2025-10 stubs superseded at the same paths).** |
| #13 | Claude/update brandme architecture… | 3d2ef63621 | 2025-10-26 | no | empty diff vs merge-base 5a03714 — nothing to lose |
| #37 | [triage] add brandme-frontend to pnpm workspace | 64d5fd6ca1 | 2026-10-08 | no | intent in main (`pnpm-workspace.yaml` lists brandme-frontend; `pnpm-lock.yaml:252` importer) — not lost |
| #55 | [triage] drop pnpm version pin | 114470007e | 2026-10-23 | no | intent in main (`module-regression.yml:39` has no pin; cherry `-`) — not lost |

Merged PRs whose head is not an ancestor of main (squash merges) and the exactness check (`range patch-id equal` / `tip vs squash tree diff on touched paths`): #18→0f69676, #19→7322f93, #20→3e3e350, #21→a2f9fb4, #22→3b8eeec, #23→ce80bf9, #24→c0419e5, #25→8f8a2b7, #26→2faae4c, #27→4335e27, #28→0f5f58a, #39→49623e4, #40→6044818, #41→b294e9e, #42–#50 (table F): **all equal / 0** (confirmed). For #40 `squash^ != merge-base` (one commit between), but the tree diff is still 0. No closed-merged PR lost content.

Heads of closed PRs that are ancestors of main (merge commits): #1, #3–#12, #14–#17, #30–#36, #51–#54, #56–#62, #64, #65, #67–#69.

### I. Reverts

`git log origin/main --grep='^Revert' --oneline` → no commits. Case-insensitive body search (`-i --grep=revert`) matches two commits whose bodies merely use the word (`4010ae8` "…(reverting the Q8 finish) passed all 48 tests…", `b61d572` "Each regression test fails with its fix reverted"); neither is a revert commit. **No reverts on main (confirmed).**

### J. Tags, submodules, LFS

- Tags: `git tag -l | wc -l` = 0; `git ls-remote --tags origin | wc -l` = 0 (**confirmed none**).
- Submodules: no `.gitmodules` in `origin/main` tree or in any commit of main's history (`git log origin/main -- .gitmodules` empty); no gitlink (`commit`) entries in `git ls-tree -r origin/main` (**confirmed none**).
- LFS: `git grep -l 'filter=lfs' <all origin and pr refs>` → nothing; no blob contains `version https://git-lfs.github.com/spec`. The only `.gitattributes` is `brandme-frontend/public/demo/.gitattributes` (`*.json text eol=lf`) (**confirmed no LFS**).

## Cross-branch conflicts

Method: pairwise `comm -12` of touched paths (merge-base..tip) and `git merge-tree --write-tree --name-only <a> <b>` among the six open-PR branches; plus each onto `origin/main`.

- **#66 `claude/opus-consumer-domains-1csp2g` × #70 `claude/midnight-rights-lifecycle-yhfyyu`: CONFLICT (confirmed).** Overlapping paths: `brandme-data/spanner/migrations/README.md`, `tests/foundation/test_migrations.py`; merge-tree reports content conflicts in both. Non-overlapping but semantically colliding: `V016_consumer_design.sql` vs `V016_rights_transfer_invites.sql` (runner raises on duplicate version; see B). Whichever merges second must renumber (main's README/test reserve through V015; #66's own text says "the next number is V017").
- Every other pair (15 pairs, including #29, #63, #71, #72): zero overlapping paths, merge-tree clean.
- Each open branch merges cleanly onto `origin/main` by itself (`git merge-tree --write-tree origin/main <ref>` exit 0 for all six), including #29 at 370 commits behind.
- Two independent `pnpm-workspace.yaml`/`pnpm-lock.yaml` edits exist on open branches: #72 (overrides for follow-redirects/gaxios) and, historically, #37. #72 overlaps no other open branch's paths.

## Things I could not determine

- Whether the lane branches with zero unique commits (`claude/opus-commerce-agents-setup-szpmf7`, `claude/opus-foundation-w00-2hgiw5`, `bench/*`) are still expected by an external process (CI dashboards, orchestration tooling outside this repo). Only in-repo consumers were grepped.
- Whether the four un-PR'd design-audit commits on `claude/setup-design-system-cli-6iovG` (2026-06) are still wanted; git shows only that the content exists nowhere else.
- GitHub `mergeable_state` is a point-in-time value; CI status (check runs) was not queried. "unstable" means a failing/pending status check, not a merge conflict (merge-tree is clean for all open branches).
- The `refs/pr/*` set in the clone stops at 70; PR #72's branch and a `refs/audit-delta/claude/exciting-hypatia-wl48op` ref appeared in the clone at 15:10 UTC (after my initial listing). I did not fetch anything myself; the source of that fetch is outside this run.
- The added-line heuristic is a proxy, not an exhaustive hunk-level proof, for the five open-PR branches (their content is expected to be absent from main anyway). For the squash-merged branches the branch-level patch-id + tree-diff test is exhaustive over the touched paths.
- `git range-diff` was not run (not applicable to squash merges; main has 288–373 commits past the relevant merge-bases).
- Three `codex/*` tips and `bench/astra-consumer-ui` are authored by "unknown" (author name as recorded in git); no attempt was made to resolve identities.
