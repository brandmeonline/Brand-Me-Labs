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
    - `Build Docker Images (gateway)`, `Build Docker Images (core)`, `Build Docker Images (agents)`,
      `Build Docker Images (chain)`, `Build Docker Images (console)`

    The five image jobs are the `build-images` matrix of the same workflow (`needs:` the six jobs above, no path
    filter, so they run on every pull request). Each builds the root-context image and runs
    `.github/scripts/smoke-image.sh` against the packaged runtime; a packaging regression that leaves the
    source-level jobs green (a dropped runtime `COPY`, a missing package in the image) fails only there, so they
    are required too.

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

## Ruleset 3: protected tags (immutability)

- Target: tags matching `archive/**`, `baseline/**` and `v*`.
- Rules: restrict updates and restrict deletions. Bypass list: **empty**, so no one, administrators included,
  can move or delete a preserved tag.
- Do **not** add "restrict creations" to this ruleset: GitHub permits creation of a creation-restricted ref only
  to actors on the bypass list, so with an empty list nobody could create the archive, baseline or release tags
  at all. Repository write access already limits who can create tags here (one collaborator).

## Ruleset 4 (optional): who may create protected tags

- Only if tag creation must be narrower than write access: a separate ruleset on the same tag patterns with
  "restrict creations" on and a bypass list of exactly the maintainers who cut releases and archive refs
  (Repository admin role). Keeping it separate from Ruleset 3 means those maintainers can create such tags but
  still cannot update or delete them.

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
ruleset message, a pull request without a green `Foundation check` or a red `Build Docker Images (core)` shows
"Merging is blocked", `git push origin --delete archive/<name>` is refused for both the branch and the tag, and
a maintainer can still create a new `baseline/<date>-<topic>` tag.
