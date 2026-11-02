# Branch and tag protection

Status: **to be applied by the repository owner** in GitHub → Settings → Rules → Rulesets. Nothing below is active
until it is applied; the 2026-11 cleanup session had no API access to rulesets (its token could create branches
and merge pull requests but was refused on tag creation and branch deletion, HTTP 403 from `receive-pack`).

Why: the audits found no protection on `main` with a single admin collaborator (codex-01 F-SEC-003; claude-opus-02
INDEPENDENT_REVIEW), so a mistaken push or force-push could rewrite the baseline unnoticed, and the preserved
`archive/*` refs could be deleted by any push.

## Ruleset 1: `main` (branch)

- Target: the default branch (`main`).
- Bypass list: **empty** (administrators included; the owner merges through pull requests like everyone else).
- Rules:
  - Restrict deletions: on.
  - Block force pushes: on.
  - Require a pull request before merging: on. Required approvals: 0 for now (single maintainer); "dismiss stale
    approvals on push": on; "require conversation resolution before merging": on.
  - Require status checks to pass: on. "Require branches to be up to date before merging": **off** (it would force
    a merge from `main` into every PR; the path-filtered workflows make that noisy and the merge result is tested on
    the `main` push anyway). Required checks, exactly the job names of `.github/workflows/ci-cd.yml`, which runs
    on every pull request:
    - `Foundation check`
    - `Test Core (Python/FastAPI)`
    - `Test Gateway (Node/TypeScript)`
    - `Test Chain (Node/TypeScript)`
    - `Test Frontend (Next.js)`
    - `Security Scan`

    Do **not** require `shell`, `live-domains`, the spatial jobs, `Module Regression`, `Chain Service Tests` or
    `Deploy manifests`: those workflows are path-filtered and would block PRs that do not trigger them.
  - Require linear history: **off** (merge commits are the convention; preserved-then-retired checks rely on them).
  - Require signed commits: off for now (no signing set up for the automation accounts).
- Merge method allowed on the repository: merge commit only (Settings → General → Pull Requests: disable squash
  and rebase merging) so history matches the convention.

## Ruleset 2: preserved refs (branches)

- Target: branches matching `archive/**` and `baseline/**`.
- Rules: restrict updates (no pushes), block force pushes, restrict deletions. Bypass list: **empty**.
- These refs exist as branches because the cleanup session could not create tags. Once the owner has converted
  them to tags (`scripts` in the owner hand-off: `git tag -a archive/<name> <sha>` then `git push origin
  refs/tags/archive/<name>`, then delete the branch), this ruleset keeps protecting any that remain.

## Ruleset 3: protected tags

- Target: tags matching `archive/**`, `baseline/**` and `v*`.
- Rules: restrict creations to maintainers, restrict updates, restrict deletions. Bypass list: **empty**.

## Also recommended (owner actions)

- Settings → General → Pull Requests → "Automatically delete head branches": on.
- Settings → Actions → General → Fork pull request workflows: "Require approval for all outside collaborators"
  (the repository is public; workflows run with the repository's secrets only on `push` to `main`).
- Settings → Code security → Dependabot alerts: on; Dependabot security updates: on. Version-update PRs are
  optional and noisy; if enabled, group them monthly and keep the frozen lockfiles authoritative.
- Image publishing: replace the `GCP_SA_KEY` secret with workload identity federation once the publish project is
  confirmed (`docs/build/deploy/gke-verification-packet.md` C-checklist; audit WP-02).
- Secret scanning and push protection (Settings → Code security): on. The CI Trivy scan is the blocking gate; push
  protection stops the commit before it exists.

## How to verify it is applied

With the rulesets active, `git push origin :refs/heads/main` and a force-push to `main` are refused with a
ruleset message, a pull request without a green `Foundation check` shows "Merging is blocked", and
`git push origin --delete archive/<name>` is refused.
