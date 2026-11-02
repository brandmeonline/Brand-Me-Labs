# Evidence and reproduction

[Audit home](../README.md) · [Checkpoint](../AUDIT_STATE.md) · [Machine ledger](ledger.json) · [Final validation](final-validation.json)

This directory contains sanitized observations, source inventories and reviewer scope. Source/GitHub evidence was collected on 2026-11-01 unless a CI/event timestamp says otherwise. Immutable links identify the analyzed revision; metadata can change after collection.

| Evidence | Scope |
|---|---|
| [Baseline](baseline.json), [pre-fetch snapshot](local-baseline-before-fetch.txt), [ref delta](history-final-ref-delta.json) | Original clean checkout, isolated main pin, new-branch delta and unchanged initial tips |
| [Branches](branches.json), [final PRs](history-github-prs-final.json), [semantic comparisons](history-semantic-comparisons.json) | 35 remote heads plus local main, 70 PRs, ancestry/patch/tree evidence; behavior sampled |
| [Requirements](requirements-inventory.json), [requirement traceability](requirement-traceability.json), [capabilities](capabilities.json), [components](components.json) | All 150 IDs mapped to source/capability context, 20 capabilities, 39 components; individual requirement implementation/acceptance unassessed |
| [Integrations](integrations.json), [config names](security-config-names.json) | 24 integrations; names-only extractor includes constants, not 1,206 required environment variables |
| [Journeys](journeys.json), [findings](findings.json) | 17 journeys and 22 reconciled findings with shared IDs/work packages |
| [Files](files.json), [coverage](coverage.json) | All 1,340 tracked main files indexed; 27 full-file reads, 169 sampled, 1,144 indexed without semantic review |
| [Static checks](static-checks.json), [assets](assets.json), [curated manifest](assets-architecture.json) | 330 Python/105 JSON syntax parses, 154 asset records, 84 curated size/hash checks; no repo imports/execution |
| [CI runs](security-ci-runs.json), [log summaries](security-ci-log-summaries.json), [CI visual provenance](ci-visual-provenance.json) | Exact-main tests/publishing vs skipped deploy; historical composite development harness separate |
| [Secret candidates](security-secret-candidates.json), [advisory triage](security-advisory-triage.json), [alert metadata](security-github-advisory-metadata.json) | Redacted candidates and selected prerequisite-aware triage, not validity/exploitation tests |
| [Issues](github-issues.json), [closed issue #38](github-issue-38.json) | One issue returned by state-all listing; historical Midnight failure context, not current failure proof |
| [Runtime preflight](runtime-preflight.txt) | Host versions, unavailable Docker engine and incomplete alternative isolation; not application failure |

Reviewer scope: [architecture](coverage-architecture.json), [security areas](coverage-security.json), [security paths](coverage-security-paths.json), [journeys](coverage-ux.json), [branch review](../BRANCHES_CODE.md). The union does not upgrade sampled paths to exhaustive review. No acceptance percentage is invented from requirement counts.

## Commands and checks actually performed

| Check | Context and result |
|---|---|
| `git status --porcelain=v1`, `rev-parse`, `for-each-ref`, `worktree list`, config inspection | Original checkout before clone and after audit: clean unchanged local main `0f5f58a9eecaca46b367c9bd96f89654343fa5fb`; refs not refreshed |
| Isolated clone/fetch without pruning; merge-base/cherry/range/tree/patch comparisons | Disposable audit clone only, detached main `ed19dc151d103b108cf972e6d37971c55d5dcf60`. Branch commands/outcomes in history evidence. Additional CI merge object fetched for provenance. |
| `git fsck --connectivity-only` | Exit 0; only dangling fetched merge `d657103ee21674ef14d6182572a78d75d0241b29` reported, no missing reachable objects. Not a durable backup. No submodule entries or main-tree LFS pointers found. |
| `python -I work/audit_static_inventory.py work/brand-me-labs-audit outputs/.../evidence` | Auditor parser, exit 0; exact cwd/SHA/Python version in JSON; no application test executed |
| Read-only connector / `gh api` / `gh run view` | Paginated branch/PR/control/alert metadata and bounded sanitized logs; per-call history API outcomes retained. Dependabot inaccessible 403. |
| Download artifact 12998005788 + SHA-256 | Archive digest matched published metadata; six allowlisted PNGs and result JSON retained; temporary signed download URL omitted; no artifact code run |
| Auditor-authored Pillow rendering and visual inspection | PNG/SVG/Mermaid diagrams, wireframe and annotated sheets; originals separate; no repository code imported |
| Pack validator below | JSON/IDs/relative links/immutable source bounds/CI image hashes plus redacted credential-pattern review; final-validation.json records outcome |

Observed host tools: Git 2.54.0.windows.1, gh 2.97.0, Node 22.21.0, npm 10.9.4; Docker client 28.0.4 had no selected engine. Host versions do not prove repository-pin alignment. Repository/CI toolchains are recorded in [security/reliability](../SECURITY_RELIABILITY.md). No hook, package install, repository build/test/server, migration or provider operation ran in this audit.

## Reproduce non-executing checks

Use a clean isolated checkout of the same pinned commit and an existing new evidence directory. Inspect the scripts; use a trusted Python executable with `-I` to exclude current-directory imports. Examples:

```text
python -I evidence/checks/audit_static_inventory.py ABSOLUTE_AUDIT_CLONE EXISTING_NEW_EVIDENCE_DIRECTORY
python -I evidence/checks/validate_pack.py ABSOLUTE_AUDIT_DIRECTORY ABSOLUTE_AUDIT_CLONE
```

The [static inventory](checks/audit_static_inventory.py) and [pack validator](checks/validate_pack.py) require Python standard library and Git only; neither imports application code. Branch reproduction helpers are retained beside history evidence. Review their commands before use. [Roadmap](../ROADMAP.md) tests require adequate disposable isolation and synthetic accounts.

“Confirmed missing” describes an inspected composition or successful metadata result, never inaccessible cloud state. “Failing” names an observed check. Untested, skipped, mocked, inaccessible and unknown are separate. Historical CI uses both a separate backend SHA and a custom development composition; it does not establish canonical ingress/schedulers or deployment. No raw credentials/customer data/private signing material are intended in this pack.
