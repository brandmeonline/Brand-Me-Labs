# Brand.Me documentation index

Consolidated 2026-11-02. Three kinds of document live here: the frozen build contract, the live build record, and
dated history. If two documents disagree, the order of precedence is `CLAUDE.md` (what runs), then
`docs/build/` (what was done and measured), then the design package (what is intended). Nothing under
`docs/archive/` describes the current tree.

## The build contract: `design/brandme/`

[`design/brandme/README.md`](./design/brandme/README.md) is the product and engineering specification
(2026-10-05): product experience, visual/motion/spatial contracts, architecture and API, Midnight ownership
lifecycle, commerce and connectors, delivery and verification, the repository audit it was written against, and the
machine-readable contracts (`contracts/`) with 150 acceptance criteria. It is validated by `pnpm check` and is
edited only through the deviation process.

## The live build record: `build/`

| File | Role |
|---|---|
| [`build/implementation-status.md`](./build/implementation-status.md) | Program roll-up: baseline SHA, lanes, acceptance evidence, blockers, next action |
| [`build/local-setup.md`](./build/local-setup.md) | Verified fresh-checkout setup and the four commands |
| [`build/compatibility-lock.md`](./build/compatibility-lock.md) | Pinned toolchain and framework tuple |
| [`build/deviations.md`](./build/deviations.md) | Accepted deviations from the contract (D-001…) |
| [`build/workspace-governance.md`](./build/workspace-governance.md) | Workspace rules, guard error codes, lane ownership |
| [`build/status/`](./build/status/) | One append-only status log per lane (foundation, consumer-domains, consumer-ui, spatial-ar, commerce-agents, midnight-rights) |
| [`build/orchestration/pipeline-state.md`](./build/orchestration/pipeline-state.md) | The continuous-build loop's state and queue; open round-03 plans sit beside it |
| [`build/evidence/`](./build/evidence/) | Acceptance ledger (`results.json`, read by `pnpm evidence:report`) and raw evidence |
| [`build/deploy/gke-verification-packet.md`](./build/deploy/gke-verification-packet.md) | First-deploy facts, gaps and the founder checklist (nothing is deployed yet) |
| [`build/security/`](./build/security/) | Secrets conventions, the credential manifest (a CI guard reads it), lane service accounts, vulnerability triage |
| [`build/runbooks/credential-rotation.md`](./build/runbooks/credential-rotation.md) | Rotation and exposure runbook |

## Audits: `audits/`

[`audits/2026-11-01/`](./audits/2026-11-01/) holds two independent code-level audits of the repository at
`ed19dc15` (`codex-01` and `claude-opus-02`) and the second audit's reconciliation of the first. Their findings
drove the 2026-11 cleanup.

## Service and package READMEs

Each service directory has a short README stating what it is, its status per `CLAUDE.md`, and how it runs:
`brandme-frontend/`, `brandme-gateway/`, `brandme-console/`, `brandme-chain/`, `brandme-core/`,
`brandme-agents/`, `brandme-cube/`, `brandme-data/`, `brandme-infra/`, the domain packages under
`brandme_core/domains/`, `brandme_core/events/`, `brandme_core/read_api/`, `brandme_core/privacy_exports/`,
and the packages under `packages/`.

## History: `archive/`

[`archive/README.md`](./archive/README.md) lists every superseded document in dated sets, with the document that
replaced it. Version labels (v6–v9), readiness percentages, PostgreSQL/Celery/Neo4j, service ports 8100–8103 and
gateway port 3000 found there belong to earlier platforms.
