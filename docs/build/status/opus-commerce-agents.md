# Lane brief: opus-commerce-agents

**Bench:** Opus 5.5 (Claude Code) · **Branch:** `bench/opus-commerce-agents-20261005`
**Base:** `docs/brandme-full-experience-2026-10-05` · **Spec:** `docs/design/brandme/` + `contracts/`
**Work packages:** W06 (discovery + provider operations), W07 (assistant + bounded commerce)
**Position in merge order:** After `opus-foundation` merges. Independent of the other Opus lanes (disjoint files).

## What you are building
Commerce and agent infrastructure — quote canonicalization and hash binding, the purchase state machine with reconciliation, AP2/ACP protocol adapters, MCP authorization, the deterministic local provider, and the operator provider console. Read chapters 05, 03, 06 and the root `CLAUDE.md` first. Re-verify AP2 Checkout/Payment mandate (v0.2 per spec table — confirm against current official docs) and MCP authorization at build time; record actual pinned versions here.

## You own exclusively (no other lane may touch these)
- `brandme_core/domains/{commerce,providers}/` — full domain logic
- `brandme_core/mcp/` — retire fake tool aliases (including `ap2.create_intent_mandate`); implement the ch.05 tool table; decide and document the explicit interface between the Python tool executor and the gateway MCP transport in your first status update
- `brandme_core/orchestrator/` — task runtime
- `brandme-agents/`, `brandme-governance/` — agent review surfaces
- `brandme-data/spanner/migrations/` — `V006_providers.sql`, `V007_commerce.sql` ONLY
- `brandme-gateway/src/routes/v1/{commerce,catalog,providers,assistant,delegations}.ts` — unmounted router files; never touch `index.ts`, `middleware/`, `types/`
- `packages/provider-contracts/` — you are the SOLE writer after Lane 1 merges (Lane 1 creates interfaces only)
- `tests/test_{commerce,providers,mcp}*.py`, `tests/fixtures/{commerce,providers}/`
- `brandme-console/app/(ops)/{providers,commerce}/**` — check Lane 5's shell layout contract in `docs/build/status/astra-consumer-ui.md` before building pages

## Read-only for you
`packages/contracts` (generated clients), gateway shared files, `docs/build/*`.

## Forbidden
`packages/contracts` (any edits), `docs/design/brandme/**`, `contracts/**`, any `brandme-frontend/` files, other lanes' domains/routes/migrations.

## Exit evidence (from ch.06 §2, W06–W07)
- Deterministic local provider covering ALL 8 required failure behaviors: stock loss, price change, rejected auth, timeout-after-accept, duplicate webhook, partial fulfillment, refund, expired quote — each with retained references
- Quote canonical hash + approval binding: price change after approval → new quote required, old approval rejected; all quote components in one ISO currency with integer arithmetic
- An agent can research and prepare; CANNOT purchase without valid authority; CANNOT mutate approved material terms; CANNOT overspend through concurrency; unknown outcome reconciles without duplicate purchase/charge
- AP2 v0.2 Checkout/Payment mandate conformance against official schemas (version pinned); A2A only for an actual approved integration need, otherwise explicitly unconfigured with contract tests
- MCP: audience-bound tokens; agent reading a product description containing instructions → text stays data, no scope change or unauthorized tool call
- Nordstrom = Impact publisher/deep-link path ONLY unless richer access is actually verified — no guessed retailer APIs, no unauthorized scraping; setup checklist + link-only path complete, missing approval recorded as an explicit integration gate
- Order reconciliation connects real observations to wardrobe states; return/refund handling tested

## Status protocol
Record status ONLY in this file. Propose deviations here. Publish dependency pins here. Document the MCP executor/transport interface decision in your first update.

## Global rules (all lanes)
Never edit another lane's owned files. Never edit `docs/design/brandme/**` or `contracts/**`. Fixtures stay in per-lane `tests/fixtures/<domain>/`. No `latest` tags — pin everything. Demo adapters carry visible simulation labels. No real money movement, no production provider credentials in the repo.
