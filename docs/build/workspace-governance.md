# Workspace governance

**Owner:** foundation lane. **Written:** 2026-10-23. **Enforced by:** [`scripts/check-workspace.mjs`](../../scripts/check-workspace.mjs) (tests: [`scripts/check-workspace.test.mjs`](../../scripts/check-workspace.test.mjs)), run by [`.github/workflows/workspace-guard.yml`](../../.github/workflows/workspace-guard.yml) on every pull request and on push to `main`, and before the install in [`.github/workflows/module-regression.yml`](../../.github/workflows/module-regression.yml).

This page covers how a package joins the pnpm workspace, how the lockfile is kept honest, and how the pnpm and Node pins stay single-sourced. Pin values and their sources live in [`compatibility-lock.md`](./compatibility-lock.md); this page does not repeat them.

Why it exists: `pnpm install --frozen-lockfile` does **not** fail on a tracked `package.json` that no workspace glob matches, or on a lockfile importer whose package was deleted. Both were reproduced on 2026-10-23 with pnpm 10.34.6 (see [Known blind spots of frozen installs](#known-blind-spots-of-frozen-installs)). The failure shows up later as `tsc: not found` or `Cannot find module`, far from its cause. It has now happened three times (W00 F13 on 2026-10-05, the 2026-10-08 triage, the 2026-10-23 astra lanes; see [What went wrong 2026-10-23](#what-went-wrong-2026-10-23)).

## Rules

1. **Every `package.json` is a workspace member by default.** Membership is the `packages:` list in [`pnpm-workspace.yaml`](../../pnpm-workspace.yaml) and nothing else. A new shared package goes under `packages/<name>` (already matched by `packages/*`). A new top-level app needs a foundation edit to `pnpm-workspace.yaml`. A directory that must stay outside the workspace needs a [STANDALONE exception](#standalone-exceptions).
2. **Manifest shape.** Name `@brandme/<name>`, `"private": true`, no `packageManager`, no `engines.pnpm`, no `pnpm` field. (`brandme-frontend` keeps its unscoped name for now because CI and scripts filter on `brandme-frontend`; `@brandme/chain` and `@brandme/gateway` still lack `private` and three nested manifests still carry `engines.pnpm >=8`. The guard reports these as warnings, not errors.)
3. **Exact pins, one tuple.** Dependencies use exact versions that match [`compatibility-lock.md`](./compatibility-lock.md). A change to a dependency tuple (React/Next/R3F/Three/Midnight, test tools, TypeScript) goes through `compatibility-lock.md` with foundation approval in the same PR; a lane does not pick its own tuple.
4. **Internal dependencies use `workspace:*`.** Never a version range or a `file:`/`link:` path to another workspace package.
5. **Install only from the repo root**, with the pnpm that corepack provides from `packageManager` (`corepack enable`). Never run `pnpm --dir <pkg> install` or `cd <pkg> && pnpm install`: for a directory inside the repo that is not a member, pnpm silently operates on the root workspace instead (verified in the 2026-10-23 audit), and with `--ignore-workspace` it writes a nested lockfile. The only exception is a STANDALONE directory, below.
6. **Manifest and lockfile change in one commit.** Edit the manifest, run `pnpm install --lockfile-only` (or a full `pnpm install`) from the root, commit `package.json` and `pnpm-lock.yaml` together.
7. **Never hand-merge `pnpm-lock.yaml`.** See [Resolving lockfile conflicts](#resolving-lockfile-conflicts).
8. **pnpm settings live only in `pnpm-workspace.yaml`:** the lifecycle-script allowlist (`onlyBuiltDependencies`), `overrides` and `packageExtensions`. Not in the root `package.json` (`pnpm`, `resolutions`), not in `.npmrc`. An override or extension changes every importer, so it needs foundation approval like a tuple change.
9. **One pnpm pin, one Node pin.** The root `packageManager` (`pnpm@x.y.z`) is the only pnpm pin: `pnpm/action-setup@v4` steps take no `version:`, Dockerfiles use `corepack enable` or exactly that version, and root `engines.pnpm`, if present, equals it. `.nvmrc` is the only Node pin: `actions/setup-node` uses `node-version-file: .nvmrc`, and `.node-version`, Dockerfile `ARG NODE_VERSION` defaults and `node:<tag>` images name the same version.
10. **Lanes on pre-foundation bases merge `main` first.** A branch cut from the 2026-10-05 docs base `4511236` (pnpm 8.15.0, lockfile v6, three workspace globs, no `brandme-frontend`) must merge `main` before any toolchain or dependency work, then follow rules 6 and 7. Copying foundation's files by hand is what produced the 2026-10-23 failure chain.
11. **STANDALONE exceptions need a foundation entry**: a reasoned entry in the `STANDALONE` map in `scripts/check-workspace.mjs` and a row in the table below, in the same PR.

Verify every change with:

```bash
corepack enable
node scripts/check-workspace.mjs --with-pnpm
pnpm install --frozen-lockfile
```

## Adding a package

1. Create `packages/<name>/package.json` with `"name": "@brandme/<name>"`, `"private": true`, exact pins and `workspace:*` for internal dependencies. For a new top-level directory, get the foundation edit to `pnpm-workspace.yaml` first.
2. If a dependency runs a lifecycle script that is genuinely needed, add it to `onlyBuiltDependencies` in `pnpm-workspace.yaml` (foundation review).
3. From the repo root: `pnpm install --lockfile-only` (or `pnpm install`).
4. `node scripts/check-workspace.mjs --with-pnpm` must print `workspace guard: clean`.
5. Commit the manifest, `pnpm-lock.yaml` and any `pnpm-workspace.yaml` change together. `.gitignore` ignores `*.json` but re-includes `package.json`, so a new manifest is picked up by `git add`; other new JSON files need `git add -f`.

## Resolving lockfile conflicts

1. Take the base branch's `pnpm-lock.yaml` unchanged: `git checkout --theirs pnpm-lock.yaml` during a merge of the base into your branch, or `git checkout <base> -- pnpm-lock.yaml`.
2. Resolve the conflicts in the `package.json` files and `pnpm-workspace.yaml` by hand. These are small and readable.
3. Run `pnpm install --lockfile-only` from the repo root with the pinned pnpm. pnpm recomputes the lockfile from the resolved manifests and keeps the base's resolutions wherever they still satisfy them.
4. Run `node scripts/check-workspace.mjs --with-pnpm` and `pnpm install --frozen-lockfile`, then commit.

Never resolve `pnpm-lock.yaml` hunks by hand, and never regenerate it from scratch on a branch that lacks some workspace packages (both astra lanes regenerated a 5-importer lockfile; foundation's has 9).

## STANDALONE exceptions

A STANDALONE directory has a tracked `package.json` that is intentionally not a workspace member. It installs with `pnpm --dir <dir> install --ignore-workspace` using the root-pinned pnpm, may commit its own `pnpm-lock.yaml` (v9), and may not declare a different `packageManager`. The guard runs its frozen check with `--ignore-workspace` under `--with-pnpm`.

| Directory | Reason | Approved |
|---|---|---|
| _none_ | | |

Pending decision: the spatial lane's `scripts/assets` (`@brandme/spatial-asset-tools`, own lockfile, `packageManager: pnpm@11.25.0`) on `origin/bench/astra-spatial-ar-20261005`. At integration it either becomes STANDALONE (drop or align its `packageManager`, regenerate its lockfile with the root pnpm and `--ignore-workspace`, add the entry here) or moves to `packages/spatial-asset-tools`. Until then the guard reports it as `E_UNREGISTERED`, `E_NESTED_LOCKFILE` and `E_PM_NESTED`.

## The guard

`scripts/check-workspace.mjs` uses Node built-ins only and never writes to the checkout. It reads the git-tracked files (`git ls-files`); untracked `package.json` files only produce a warning, but if a workspace glob matches one it is checked like a member, because pnpm sees it too.

- **Offline (default):** about 40 ms of checks on this repo, under 0.1 s wall clock. Membership, importer key and dependency-name sets, lockfile version, nested lockfiles, and every pnpm and Node pin.
- **`--with-pnpm`:** about 1 s in total and needs no `node_modules`. It checks that `pnpm --version` equals `packageManager`, then runs `pnpm install --frozen-lockfile --lockfile-only --ignore-scripts` (pnpm's own check of specifiers, overrides and `packageExtensions`; verified to write nothing) and `pnpm ls -r --depth -1 --json` (pnpm's project list, compared with the guard's).
- **`--json`** prints the result as JSON. Inside GitHub Actions every finding is also printed as an `::error` or `::warning` annotation on the file and line.
- **Exit codes:** 0 clean (warnings allowed), 1 any error, 2 bad arguments.

The guard compares importer dependency **names and sections** only (pnpm precedence: `optionalDependencies` > `dependencies` > `devDependencies`; `peerDependencies` may appear in any section because of `autoInstallPeers`). It never compares specifiers itself, because overrides rewrite them: `brandme-frontend/package.json` declares `postcss ^8.4.32`, but the lockfile records `8.5.23` from the `postcss@8` override. Specifier staleness is left to pnpm under `--with-pnpm`.

### Error codes

| Code | What it means | Fix |
|---|---|---|
| `E_UNREGISTERED` | A tracked `package.json` matches no `packages:` glob and is not STANDALONE, so `pnpm install` never installs it. | Add a glob (or move the package under `packages/<name>`), `pnpm install --lockfile-only`, commit manifest and lockfile together; or get a STANDALONE entry. |
| `E_ALLOWLIST_CONFLICT` | A STANDALONE directory is also matched by a workspace glob. | Remove the entry, or exclude the directory with a `!<dir>` glob. |
| `E_ALLOWLIST_STALE` | A STANDALONE entry has no tracked `package.json`, no reason, or a non-normalized path. | Fix or delete the entry. |
| `E_WS_CONFIG` | `pnpm-workspace.yaml` is missing, or `packages:` is absent, empty, inline/flow style, or uses unsupported glob syntax (extglobs, groups, escapes, `{1..3}`). | Use a block list of simple globs: `*`, `**`, `?`, `{a,b}`, `[...]`, `!negation`. |
| `E_MANIFEST_JSON` | A `package.json` does not parse, or the root one is untracked. | Fix the JSON. |
| `E_LOCK_MISSING` | No tracked root `pnpm-lock.yaml`. | `pnpm install --lockfile-only` and commit it. |
| `E_LOCK_VERSION` | `lockfileVersion` is not `'9.0'` (fail closed: the reader knows only v9). | Take the base branch's lockfile, `corepack enable`, `pnpm install --lockfile-only`. |
| `E_LOCK_PARSE` | No readable `importers:` block. | Regenerate it; do not hand-edit. |
| `E_IMPORTER_MISSING` | A registered package has no importer, including a zero-dependency one (frozen installs accept that, but pnpm writes `{}` on the next install). | `pnpm install --lockfile-only`, commit with the manifest. |
| `E_IMPORTER_ORPHAN` | An importer has no registered package (frozen installs accept that). | `pnpm install --lockfile-only` drops it; commit. |
| `E_IMPORTER_STALE` | An importer's dependency names or sections differ from its manifest. | `pnpm install --lockfile-only`, commit with the manifest. |
| `E_PM_FORMAT` | Root `packageManager` is not an exact `pnpm@x.y.z` (optionally `+sha…`). | Set the exact pin. |
| `E_PM_ENGINES` | Root `engines.pnpm` is present and not equal to the `packageManager` version. | Make it equal, or remove it. |
| `E_PM_NESTED` | A nested `package.json` declares a `packageManager` that differs from the root's. | Remove it. |
| `E_ACTION_PNPM_VERSION` | A `pnpm/action-setup` step has any `version:` input, even an equal one (workflows and composite actions under `.github/`). | Delete the input. With both set, action-setup@v4 refuses to start ("Multiple versions of pnpm specified", run [39961921035](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39961921035)); an equal copy drifts later. |
| `E_PNPM_PIN` | `corepack prepare/use/install pnpm@X`, `npm i -g pnpm[@X]`, `npx pnpm@X` or `pnpm dlx pnpm@X` with X unequal to `packageManager`, or with no version. Scanned: Dockerfiles, YAML, shell scripts, Makefiles, `.tool-versions`, `package.json` scripts; not `docs/`, comment lines, `echo`/`printf` lines or `$VAR` values. | Use `corepack enable` (or `corepack install`), or pin exactly the `packageManager` version. |
| `E_NODE_LITERAL` | `actions/setup-node` has a `node-version:` input (a literal or a matrix expression), no `node-version-file`, or a file other than `.nvmrc`/`.node-version`. | `node-version-file: .nvmrc`. |
| `E_NODE_FILES` | `.nvmrc` is missing or not an exact `x.y.z`, or `.node-version`, `.tool-versions`, a Dockerfile `ARG NODE_VERSION=` default, a `FROM node:<tag>` or a YAML `image: node:<tag>` names a different version (`node:lts`, `node:20-alpine`). | Make them all name the `.nvmrc` version. |
| `E_NESTED_LOCKFILE` | Any `pnpm-lock.yaml`, `package-lock.json`, `npm-shrinkwrap.json`, `yarn.lock` or `bun.lock(b)` other than the root `pnpm-lock.yaml` and a STANDALONE directory's own `pnpm-lock.yaml`. | Delete it; install from the root only. |
| `E_PNPM_FIELD` | Root `package.json` has `pnpm`, `resolutions` (pnpm applies it as overrides) or `workspaces` (pnpm ignores it). | Move settings into `pnpm-workspace.yaml`; membership is `packages:`. |
| `E_GIT` | Not a git checkout. | Run inside a checkout, or pass `--root`. |
| `E_PNPM_RUNTIME` | `--with-pnpm`: `pnpm` is missing or `pnpm --version` differs from `packageManager`, so the pnpm checks were not run. | `corepack enable`; in CI, `pnpm/action-setup@v4` with no `version:`. |
| `E_PNPM_FROZEN` | `--with-pnpm`: pnpm's frozen `--lockfile-only` check failed (stale specifier, override or extension). | `pnpm install --lockfile-only`, commit with the manifest. |
| `E_PNPM_PROJECTS` | `--with-pnpm`: pnpm's project list differs from the guard's. | Commit or delete the listed manifests; on a clean tree this is a guard bug, so report it. |

Warnings (exit 0): `W_ENGINES_PNPM` (nested `engines.pnpm`), `W_NOT_PRIVATE` (a member without `"private": true`), `W_UNTRACKED` (an untracked `package.json`), `W_STANDALONE_NO_LOCK` (a STANDALONE directory with dependencies but no lockfile).

### Running it locally

```bash
node scripts/check-workspace.mjs               # offline, < 0.1 s
node scripts/check-workspace.mjs --with-pnpm   # + pnpm's own frozen check, ~1 s, no node_modules needed
node scripts/check-workspace.mjs --json        # machine-readable
node scripts/check-workspace.mjs --root ../other-checkout
node --test scripts/check-workspace.test.mjs   # 34 tests; the --with-pnpm ones skip without the pinned pnpm
```

To check another branch without switching: `git worktree add --detach /tmp/wt <ref>`, run the guard with `--root /tmp/wt`, then `git worktree remove /tmp/wt`.

A pull_request run checks the merge ref, i.e. the tree that would land. A lane that never touched a stale file therefore gets `main`'s version there, even when the guard flags the stale file on the lane tip itself.

## Known blind spots of frozen installs

Reproduced on 2026-10-23. Rows 1 and 2 used pnpm 10.34.6 on scratch copies of `744d593` (`git archive`, no `node_modules`); row 3 a temporary worktree of `a37ec2b` with the pnpm 8.15.0 that corepack selects from its `packageManager`; row 4 the synthetic workspace in the test suite.

| Change | `pnpm install --frozen-lockfile --lockfile-only` | Guard |
|---|---|---|
| Add `scripts/foo/package.json` with a dependency, no glob | passes ("Scope: all 9 workspace projects") | `E_UNREGISTERED` |
| Delete `packages/design-system`, keep its importer | passes ("all 8 workspace projects") | `E_IMPORTER_ORPHAN` |
| `a37ec2b` (frontend unregistered) | passes | `E_UNREGISTERED`, `E_LOCK_VERSION` and others |
| Change only a specifier (`workspace:*` to `workspace:^`) | fails | clean offline; `E_PNPM_FROZEN` with `--with-pnpm` |

The last row is why `--with-pnpm` exists: offline checks deliberately ignore specifiers.

## What went wrong 2026-10-23

1. **The lanes were cut from a pre-foundation base.** Both astra lanes (consumer-ui and spatial-ar) branched from the docs base `4511236` (2026-10-05). That base has `packageManager: pnpm@8.15.0`, `lockfileVersion: '6.0'`, workspace globs for gateway, chain and console only, and a module-regression workflow with `node-version: '20'` and `pnpm/action-setup@v4` `version: 8`. Foundation registered `brandme-frontend` in `4f9f4bc` (2026-10-05), which is not in `4511236`. The consumer-ui brief treated the workspace and lockfile as foundation-owned and left them untouched (`astra-consumer-ui.md:65` on `origin/bench/astra-consumer-ui-20261005`).
2. **The two pnpm pins collided.** With both `version: 8` and `packageManager: pnpm@8.15.0` set, `pnpm/action-setup@v4` refused to start: "Multiple versions of pnpm specified" (Module Regression run [39961921035](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39961921035), job 120441774344, per the 2026-10-23 audit of the Actions logs). The spatial status records the failed run (`astra-spatial-ar.md:260`).
3. **PR #55 fixed the symptom only.** Its head `1144700` (branch `triage/pnpm-version-conflict-20261023`, parent `6899d88` on the spatial lane) removed `with: version: 8`. Setup pnpm then passed, but the frontend was still unregistered, so `pnpm install --frozen-lockfile` passed without installing its dependencies and the suite failed in `scripts/regression/modules/brandme_frontend.sh` with `ERR_PNPM_RECURSIVE_EXEC_FIRST_FAIL Command "tsc" not found` (check-run 120440746876, per the audit). PR #55 was closed unmerged as insufficient.
4. **The lanes then registered the frontend themselves.** Consumer-ui `da2f430` and spatial `e576558` copied foundation's `pnpm-workspace.yaml` and root pins and regenerated a v9 lockfile with 5 importers (foundation's has 9). Spatial then found a second hidden problem: an ignored `node_modules` symlink from the frontend into the asset tools had masked spatial imports that `brandme-frontend/package.json` never declared (`astra-spatial-ar.md:262`). It declared them, and added a root `package.json` `pnpm.packageExtensions` entry for `@react-three/fiber@9.4.0` (`astra-spatial-ar.md:263`). Module Regression then passed on `e576558` (run [39973210496](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39973210496), `astra-spatial-ar.md:273`).
5. **The same class had happened twice before.** W00 recorded `pnpm install --frozen-lockfile` passing "frontend not in workspace, so not installed" and finding F13 ([`baseline-test-report.md:22`, `:42`](./evidence/w00/baseline-test-report.md)) on 2026-10-05. The 2026-10-08 triage branch `origin/triage/pnpm-workspace-frontend-20261008` (`64d5fd6`) tried again with pnpm 8 and a v6 lockfile.

**Root cause:** nothing failed at the point of the mistake. A tracked manifest outside the workspace globs passes a frozen install, and pnpm pins were duplicated across `packageManager`, `engines`, action inputs and Dockerfiles with no consistency check. The guard turns each step above into an immediate error with a fix: step 1 is `E_UNREGISTERED`, `E_LOCK_VERSION`, `E_NODE_LITERAL` and `E_NODE_FILES`; step 2 is `E_ACTION_PNPM_VERSION`; step 3 never reaches `tsc`, because the guard runs before the install; step 4's root `pnpm` field is `E_PNPM_FIELD`.

### What the guard reports on the historical refs

Run on 2026-10-23 from this branch with `--root <temporary worktree>` (offline counts; `--with-pnpm` added only the pnpm lines noted).

| Ref | Errors | Main findings |
|---|---|---|
| `a37ec2b` (consumer-ui, before repair) | 22 | `E_UNREGISTERED brandme-frontend`, `E_LOCK_VERSION '6.0'`, `E_PM_ENGINES >=8.0.0`, `E_ACTION_PNPM_VERSION` ×7 (`version: 8`), `E_NODE_LITERAL` ×7 (Node 18/20), `E_NODE_FILES` (no `.nvmrc`), `E_PNPM_PIN` ×4 (console `pnpm@8`, gateway unpinned) |
| `5acc8ee` (spatial, before repair) | 25 | as `a37ec2b`, plus `E_UNREGISTERED scripts/assets`, `E_NESTED_LOCKFILE scripts/assets/pnpm-lock.yaml`, `E_PM_NESTED pnpm@11.25.0` |
| `1144700` (PR #55 head) | 24 | as `5acc8ee` minus the module-regression `version: 8` that PR #55 removed; `E_UNREGISTERED brandme-frontend` is the failure its CI hit as `tsc: not found` |
| `origin/bench/astra-spatial-ar-20261005` (`a78433d`) | 23 | `E_UNREGISTERED scripts/assets`, `E_NESTED_LOCKFILE`, `E_PM_NESTED pnpm@11.25.0`, `E_PNPM_FIELD` (root `pnpm.packageExtensions`), stale `chain-tests.yml`/`ci-cd.yml` (`version: 8`, Node 18), module-regression Node 20, no `.nvmrc`, Dockerfile `pnpm@8.15.0`/`pnpm@8`/unpinned. pnpm frozen check and project list: pass (5 projects) |
| `origin/bench/astra-consumer-ui-20261005` (`264b6a0`) | 19 | membership and lockfile now clean; the same stale workflows, missing `.nvmrc` and Dockerfile pins. pnpm checks pass (5 projects) |
| commerce-agents lane tip (`3823ea5`) | 11 | membership and lockfile clean; stale Dockerfiles on the tip (`pnpm@8.15.0`, `pnpm@8`, unpinned `npm install -g pnpm`, `node:18-alpine`) |
| consumer-domains lane tip (`dafd3b1`) | 11 | same as commerce |
| midnight-rights lane tip (`ecece17`) | 0 | clean (5 warnings) |
| this branch (`744d593` + this change) | 0 | clean (5 warnings) |

The commerce, consumer-domains and midnight tips merge cleanly into `744d593` (`git merge-tree`), and the guard with `--with-pnpm` is clean on all three merge trees: the stale Dockerfiles exist only on the tips. The two astra tips conflict with `744d593` (consumer-ui on `pnpm-lock.yaml`; spatial on `brandme-frontend/package.json`, `package.json` and `pnpm-lock.yaml`), so they need rule 7.

### Conflicts this change set adds (2026-10-24), and how to resolve them

Merging this branch adds these textual conflicts on top of the ones above. Resolve
each in favour of `main` (this branch) and keep the lane's own additions:

| Lane | File | Resolution |
|---|---|---|
| consumer-domains (#52) | `.github/workflows/ci-cd.yml` | Keep **both** new jobs (`foundation-check` and the lane's `test-consumer-domains`); they sit at the same spot. |
| consumer-ui, spatial-ar | `.github/workflows/module-regression.yml` | Keep `main`'s `Workspace guard` step and `permissions: contents: read`. |
| consumer-ui, spatial-ar | `pnpm-workspace.yaml` | Keep `main`'s header comment and the `body-parser@1` / `fast-uri@3` security overrides; move any lane `pnpm.packageExtensions` here (`E_PNPM_FIELD`). |

Resolving these hunks as "theirs" would silently drop the guard step and two
security overrides; the guard then reports the missing pins only if the lockfile
is regenerated (rule 6).

## Limits

- The YAML readers are line-based. `pnpm-workspace.yaml` `packages:` and the lockfile fail closed on shapes they cannot read. The workflow reader finds `uses:` steps and their `with:` inputs in block or flow style, but a step written in an unusual layout could be missed.
- Glob matching follows pnpm 10.34.6 as verified on 2026-10-23: `*` is one segment, `**` is zero or more, wildcards never match a leading dot, `node_modules` and `bower_components` are never projects, and a negation excludes only the exact `<dir>/package.json`. `--with-pnpm` cross-checks the result against `pnpm ls`.
- The pin scan does not read JavaScript or TypeScript sources, `docs/`, or values built from variables.
- There is no CODEOWNERS file, so ownership of `pnpm-workspace.yaml`, `package.json`, `pnpm-lock.yaml`, `.nvmrc`, the workflows and this guard is enforced only by review.
