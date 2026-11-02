# Contributing to Brand-Me-Labs

This repository is kept in a state where every change is small, reviewed, verified by the same gates CI runs, and
described truthfully. The rules below are what keep it that way. `CLAUDE.md` is the map of what actually runs;
`docs/build/implementation-status.md` is the program roll-up; the design package under `docs/design/brandme/` is
the build contract.

## Branches and pull requests

- Branch from `main`. Name branches `<area>/<topic>-<yyyymmdd>` (for example `foundation/outbox-retry-20261105`);
  tool-driven sessions keep their generated names. There are no long-lived `bench/`, `lane/` or `develop`
  branches any more; every pull request targets `main`.
- One change per pull request: one fix, one feature slice, one documentation consolidation. A PR that needs the
  words "and also" in its title is two PRs.
- Open as a draft; mark it ready when CI is green on the exact head and the description is complete. Merge with a
  merge commit (history is preserved; nothing is squashed or rebased after review starts). Never force-push a
  branch someone else may have checked out.
- Delete the branch after merge. A branch whose content is fully in `main` is retired. Anything unique that is
  being retired is preserved first under `archive/<topic>-<yyyy-mm-dd>` (a tag, or a branch of the same name when
  the actor cannot create tags; the owner converts those to tags). Archive refs are never moved or deleted.
- Lane work that touches files owned by another lane (the gateway mount file, the migration registry, foundation
  tests) states so in the PR under "Needs foundation" instead of self-applying it, as `docs/build/orchestration/`
  describes.

## Gates

`pnpm check` is the CI foundation gate and must pass locally before a PR is marked ready. It runs the workspace and
toolchain guard, the spec package validator, contract and token drift checks, the credential-manifest guard, type
checks, the gateway and package suites, the full Python suite (with emulators) and the `docs/build` link checker.
CI adds the Docker image builds, the repo-wide Trivy secret scan and, for frontend and spatial paths, the browser
and visual-baseline workflows.

- Never skip, quarantine or weaken a test to get green. Known-broken tests are quarantined by name in
  `tests/conftest.py` with an owner and a blocker, and are reported as xfail, never as passing.
- A red check is root-caused; "flake" is not a cause. If the cause is a non-deterministic input, fix the input.
  (Known open case: the full-page height in `brandme-frontend/lib/testing/verify-visual.mjs` captures is not yet
  deterministic; the fix belongs in the capture, not in the baseline.)
- Re-run a job at most once, and only to confirm a failure is not the change's own.
- Visual baselines (`brandme-frontend/lib/testing/baselines/`) change only in a commit whose message states which
  captures were inspected and why every difference is intended.

## Secrets and configuration

- No credentials, tokens, seeds, keys or connection strings in the tree, in fixtures, in evidence or in
  documentation. The Trivy scan blocks the pipeline and has its test/example/markdown allow rules turned off.
- Every secret-shaped environment variable the code reads (`KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `CREDENTIAL`,
  `PRIVATE`, `SEED`, `MNEMONIC`, `DSN`) has a row in `docs/build/security/credential-manifest.yaml`
  (`docs/build/security/secrets-conventions.md`). The guard fails on an unlisted name.
- Credential-shaped JSON file names and every dotenv file except committed `*.example` templates are ignored by
  `.gitignore`; there is deliberately no blanket `*.json` rule, so a new fixture or schema shows up in
  `git status` and is reviewed.

## Database migrations

- GoogleSQL only, `brandme-data/spanner/migrations/V<NNN>_<name>.sql`, applied by the checksum-ledger runner.
- Claim a version number before writing the migration: add it to `RESERVED` in
  `tests/foundation/test_migrations.py` and to the reservation row of `brandme-data/spanner/migrations/README.md`
  in the same PR. Two open PRs must never claim the same number; the one that merges second renumbers.
- Never edit an applied migration; write a new one.

## Documentation

- `CLAUDE.md` is the honest map of what runs. A PR that changes what a service does, mounts or depends on updates
  its row in the same PR, with a file:line reference.
- `docs/build/implementation-status.md` is refreshed when a merge moves a lane, a blocker or the baseline.
  Lanes keep their own append-only `docs/build/status/<lane>.md`.
- Deviations from the design package are recorded in `docs/build/deviations.md`; the design package itself is
  edited only through that process.
- Superseded documents are moved (never copied) into a dated set under `docs/archive/`, with a row in
  `docs/archive/README.md` naming the successor. Nothing under `docs/archive/` describes the current tree.
- Readiness is stated as evidence (which gate, which run, which counts), never as a percentage.

## Commit messages

`<type>(<scope>): <what>` on the first line, then *why* and *what was verified*. Types: `feat`, `fix`, `docs`,
`ci`, `chore`, `refactor`, `test`. Reference the PR, plan stage or audit finding the change answers.

## Tags and milestones

`main` is tagged at each accepted milestone: `baseline/<yyyy-mm-dd>-<topic>` for cleanup and audit baselines, and
`v0.<n>.<m>` once releases begin. The protection that keeps `main`, `archive/**` and `baseline/**` from being
rewritten is specified in `docs/build/security/branch-protection.md`.
