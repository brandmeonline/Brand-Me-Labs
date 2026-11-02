# Brand.Me Labs

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Brand.Me is a consumer platform for garment identity, social shopping, loyalty and verifiable ownership: a Next.js
consumer app and an Express gateway in front of Python domain services on Google Cloud Spanner and Firestore, with
a Midnight (Compact) rights contract for private ownership and licensed reprint.

This README is the entry point only. Three documents carry the truth about this repository:

| Question | Read |
|---|---|
| What is actually wired up today, per service, with file references | [`CLAUDE.md`](./CLAUDE.md) |
| What is being built, in what order, with acceptance criteria | [`docs/design/brandme/README.md`](./docs/design/brandme/README.md) (the build contract) and its [kickoff prompt](./docs/design/brandme/CLAUDE_BUILD_PROMPT.md) |
| Where the program stands right now: baseline, lanes, evidence, blockers, next action | [`docs/build/implementation-status.md`](./docs/build/implementation-status.md) |

Everything else is indexed in [`docs/README.md`](./docs/README.md). Documents that described earlier platforms live
under [`docs/archive/`](./docs/archive/README.md) and are not a description of this tree.

## Start here (local)

The verified path from a fresh checkout is native, not containers
([`docs/build/local-setup.md`](./docs/build/local-setup.md)):

```bash
pnpm setup:demo   # runtimes, .venv from the hashed lock, frozen install, .env.local, Spanner emulator, migrations
pnpm dev:demo     # brain :8000, gateway :3001, consumer :3000  (BRANDME_MODE=demo)
pnpm smoke        # gateway → brain → Spanner, session, PATCH /me, restart persistence, outbox dispatch
pnpm check        # the CI foundation gate: spec validator, contract drift, guards, type checks, full test suite, doc links
```

`docker compose up -d` starts the same default set plus the Firestore emulator and the consumer-domains service;
`--profile legacy` adds the stubbed legacy services (see `CLAUDE.md`).

Pinned toolchain: Node 24.21.0 (`.nvmrc`), pnpm 10.34.6 (`packageManager`), Python 3.11, Spanner emulator 1.5.45.
The full tuple is in [`docs/build/compatibility-lock.md`](./docs/build/compatibility-lock.md); the workspace guard
refuses other versions.

## Repository layout

```
brandme-frontend/     Next.js consumer app (port 3000)
brandme-gateway/      Express edge gateway: sessions, CSRF, rate limits, consumer routers (port 3001)
brandme_core/         Python shared library and the consumer domains (persona, wardrobe, social, rewards,
                      media, providers, commerce, rights, privacy), events outbox, read API, MCP executor
brandme-core/         Legacy Python services: brain (8000), policy (8001), orchestrator (8002, stub)
brandme-agents/       Legacy Python services: identity, knowledge, compliance (stubs); agentic CLI
brandme-cube/         Legacy Product Cube service (8007, unverified)
brandme-governance/   Legacy governance console service (8006, stub)
brandme-chain/        Midnight rights contract (Compact) and chain service
brandme-console/      Next.js operator console (port 3002, dev compose only)
brandme-data/         Spanner migrations (V001…) and the migration runner
brandme-infra/        Helm chart and GKE deployment assets (nothing deployed yet)
packages/             Generated contracts, design tokens, Firestore rules, provider contracts
scripts/              brandme.mjs (check/smoke/migrate), guards, regression harness, dev tooling
tests/                Python test suite (foundation, domains, journeys), run with emulators in CI
docs/                 design contract, live build record, audits, archive
```

## How changes land

- Branch from `main`; one change per pull request; CI must be green on the exact head.
- `pnpm check` is the same gate CI runs. Known-broken tests are quarantined by name in `tests/conftest.py` and never
  reported as passing.
- No credentials in the tree: a repo-wide Trivy secret scan blocks the pipeline, and
  `docs/build/security/credential-manifest.yaml` must name every secret-shaped environment variable the code reads.
- Lane ownership, deviations and evidence conventions: [`docs/build/workspace-governance.md`](./docs/build/workspace-governance.md),
  [`docs/build/deviations.md`](./docs/build/deviations.md).

## Claude Code setup

The repo ships a project-scoped skill at `.claude/skills/ui-ux-pro-max/` and declares the 21st.dev Magic MCP server
in `.mcp.json`. The Magic server needs an API key: copy `.claude/.env.local.example` to `.claude/.env.local`, set
`MAGIC_API_KEY`, and start a new session; `.claude/.env.local` is gitignored.

## License

Proprietary and confidential. Unauthorized copying or distribution is prohibited.
