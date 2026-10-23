# W00 trust-path fixture inventory

Recorded 2026-10-05 on branch `claude/opus-foundation-w00-2hgiw5` (base `e4f1342`), by reading the cited lines. Nothing here was run against a live network. Each row is a place where application code fabricates trust evidence, or skips authority checks.

Enforcement: `brandme_core/config.py` `LEGACY_SIMULATED_ADAPTERS` registers each fabricating service as a **simulated** adapter with a visible label. `python -m brandme_core.config preflight --service <name>` runs before every Python service in compose, and it **refuses to boot** in `sandbox`/`production` while that service's registration remains (see `tests/foundation/test_mode_guard.py`). Lanes that replace a fake remove or upgrade its registration with evidence.

Key observations:
- `allow_stub_fallback` does not exist on this branch. `MIDNIGHT_ENABLED` (compose) is read by no code.
- Several fabrications are unconditional (no flag): `cardano-tx-builder.ts:73`, the whole Midnight client, `routes/tx.ts:109`, `orchestrator/main.py:84`, `orchestrator/worker.py:142`.
- `esg_verifier.py:163` and `burn_proof.py:154` switch to stubs implicitly on `ConnectError`. An unreachable host yields "verified" data.
- The chain `*_FALLBACK_MODE` defaults disagree: zod config says `true` (`brandme-chain/src/config/index.ts:28,34`), but `blockchain.ts:72,135` reads `process.env` (effectively off).

| Category | file:line | What it fabricates | Gate / default | Guard registration |
|---|---|---|---|---|
| Chain | brandme-core/orchestrator/main.py:83-84,89,106 | Transfer returns `cardano_tx_{transfer_id[:16]}`; nothing submitted | none | orchestrator / chain.cardano |
| Chain | brandme-core/orchestrator/worker.py:131-145 (186,194-201,218,234-236) | `tx_cardano_`/`tx_midnight_`/`root_` sha256 prefixes written to Spanner anchors and sent to compliance | none | orchestrator / chain.midnight |
| Chain | brandme-core/brain/main.py:148-157 | Orchestrator failure → `"status":"ok"` with `stub_` hashes | any exception | brain / chain.cardano |
| Chain | brandme-core/orchestrator/tasks.py:290-301, 561-568 | Posts to nonexistent `/tx/submit`; `sync_blockchain_state` no-op | none | orchestrator |
| Chain | brandme-chain/src/services/cardano-tx-builder.ts:67-75 | Always `simulated_cardano_${Date.now()}_…`; real build commented out (77+) | none | chain / chain.cardano |
| Chain | brandme-chain/src/services/blockchain.ts:71-75,302-316 / 134-138,318-328 | sha256 of payload presented as Cardano / Midnight tx | `CARDANO_FALLBACK_MODE` / `MIDNIGHT_FALLBACK_MODE` | chain; flags refused in strict modes |
| Chain | brandme-chain/src/services/midnight-client.ts:101-136,150-158,188-210,225-286 | Fake shielded tx hash, `encrypted_${sha256}`, always `confirmed` at block 12345, fake reveal IDs, fake Cardano anchor | none | chain / chain.midnight |
| Chain | brandme-chain/src/routes/tx.ts:107-118 | `/tx/verify-root` returns `is_consistent: true` | none | chain |
| Chain | brandme-chain/src/services/blockchain.ts:208-225,254,334-354 | Health checks `return true`; `verified: … \|\| true` | none | chain |
| Chain | brandme-chain/src/index.ts:54-70 | Starts in "fallback mode" without wallet/Blockfrost key | config presence | chain |
| Chain | brandme-agents/agentic/tools/blockchain_tools.py:42-44,69-71,130-132 | Returns `"Error: …"` in the tx-hash slot | none | (CLI, not a service) |
| Chain | brandme-agents/compliance/src/main.py:146-163 | `/audit/anchorChain` returns ok, persists nothing | none | compliance |
| Chain | brandme-frontend/lib/demoData.ts:45-80 | Passport `status:'verified'`, fake tx hashes, ESG `A+`, certifications | none | frontend lane must label/remove |
| Proof | brandme_core/zk/proof_of_ownership.py:143-199, 285-401 | "ZK proof" = JSON of sha256 commitments; `ownership_valid: True`; verifier checks self-consistency only | `ZK_PROOF_ENABLED` default `true` | identity / proof.ownership |
| Proof | brandme-agents/identity/src/main.py:561-616 | Verify endpoint rebuilds the proof from caller-supplied signals | `ZK_PROOF_ENABLED` | identity |
| Proof | brandme-chain/src/services/midnight-client.ts:166-181 | `proof_data: 'stub_proof_data'`, `proof_type: 'zk-snark'` | none | chain |
| Proof | brandme-agents/compliance/src/lifecycle/burn_proof.py:154-161,176-213 | On ConnectError any 64-hex string → `is_valid=True`, `material_recovery_pct=85.0` | implicit | compliance / chain.midnight |
| Proof | brandme-agents/compliance/src/lifecycle/state_machine.py:262-274 | `verify_burn_proof` returns True without a verifier | `burn_proof_verifier=None` | compliance |
| ESG | brandme-agents/compliance/src/lifecycle/esg_verifier.py:141-147,163-169,179-197 | Stub ESG score from hash (0.4-0.9), carbon 5.0 kg, water 100 L, `STUB_CERT`; missing fields default 0.5 | implicit on ConnectError | compliance / esg.oracle |
| ESG | brandme-agents/compliance/src/lifecycle/state_machine.py:131-142 | Invented REPAIR/REPRINT savings written to Spanner | none | compliance / esg.oracle |
| ESG | brandme_core/mcp/tools.py:832,841,848,857,620-633 | `esg_verified: True`, constant 0.1 / 85.0; ESG check skippable | none | mcp / esg.oracle |
| ESG | brandme-agents/knowledge/src/main.py:63-78 | Every passport gets "Sustainability certified", rating "A", fixed origin | none | knowledge / esg.oracle |
| ESG | brandme-cube/src/service.py:613,710,749 | `esg_verified` echoes request flag; material value placeholder 10.0 | request field | cube / esg.oracle |
| Trust score | brandme-agents/identity/src/main.py:153,160-171,183-192 | Unknown users get synthetic `trust_score: 0.5` | none | identity |
| Commerce | brandme_core/mcp/tools.py:801-859 | Empty search, "Sample Garment", uuid4 rental/listing/repair/dissolve IDs | none | mcp |
| Commerce | brandme_core/mcp/tools.py:861-923 | AP2 intent/cart/payment "mandates" are uuid4 with `status:"issued"`; ACP cart/checkout `completed` with no merchant/payment | none | mcp / commerce.mandate, commerce.checkout |
| Commerce | brandme-core/policy/main.py:652-659 | `canTransferOwnership` allows any transfer ≤ 10000 with no ownership/consent check | none | policy / auth.identity |
| Commerce | brandme-core/orchestrator/tasks.py:476-491,502-506 | Notification "queued" but only logged | none | orchestrator |
| Reprint | brandme_core/firestore/wardrobe.py:102, 286 (555) | `reprint_eligible` defaults `True` on model and new docs | none | cube / rights.reprint |
| Reprint | brandme-cube/src/service.py:543-576, 558-564 | DISSOLVE→REPRINT without burn proof; calls nonexistent `compliance.verify_esg` | none | cube / rights.reprint |
| Auth | brandme-gateway/src/middleware/auth.ts:45,48 | HS shared-secret JWT, no algorithm allowlist/audience; issuer `accounts.google.com` (RS256) cannot verify | `JWT_SECRET` | **replaced in this lane** by OIDC/JWKS + session middleware |
| Auth | docker-compose.dev.yml:94-96 | `dev-client-id`, `dev-client-secret`, literal JWT secret | env fallback | **removed in this lane** |
| Auth | brandme_gateway/src/middleware/auth.ts:52-79,95-137 | `parseJWTMock` accepts any 10+ char token; logs raw user IDs (orphan dir) | none | not imported anywhere |
| Auth (log) | brandme-gateway/src/middleware/auth.ts:59; brandme-gateway/src/routes/scan.ts:67-72 | Raw user IDs logged | none | auth.ts replaced; scan.ts owned elsewhere |
| Auth | brandme_core/mcp/tools.py:553-558,586-593,667 | Executor trusts `user_id` from tool params | none | mcp / auth.identity |
| Auth | brandme-cube/src/main.py:153-178; api/cubes.py:18,35; api/faces.py:24; main.py:306,234,272 | No auth; `request.state.get` (not a Starlette API); owner checks against body values | none | cube |
| Auth | brandme-core/policy/main.py:558-569 | `canViewFace` trusts payload `viewer_id`/`owner_id`; `fetch_owner_and_consent` undefined (NameError) | none | policy / auth.identity |
| Auth | brandme-agents/identity/src/main.py:359-360,406-407,450-451,561-562,651-652 | Consent/ZK endpoints act on path `user_id` without auth | none | identity / auth.identity |
| Auth | brandme-agents/agentic/orchestrator/agents.py:108-111 | Hardcoded `policy_decision="allow"` | none | CLI |
| Auth | brandme-chain/src/index.ts:42-43 | `/tx` routes unauthenticated | none | chain |
| Placeholder | brandme-gateway/src/routes/scan.ts:75-79,103-114 | POST 202 `processing` without a record; GET always `processing` | none | gateway legacy route (not mine to change) |
| Placeholder | brandme-cube/src/api/cubes.py:50-59 | `/cubes/search` "implementation pending" | none | cube |

## Environment switches

| Flag | Read at | Default | Strict-mode treatment |
|---|---|---|---|
| `ENABLE_STUB_MODE` | brandme_core/config.py (read by nothing else) | was `"true"`, now `"false"` | refused if truthy |
| `CARDANO_FALLBACK_MODE` / `MIDNIGHT_FALLBACK_MODE` | brandme-chain blockchain.ts:72,135; config/index.ts:28,34 | effectively off / config says true | refused if truthy |
| `ZK_ALLOW_STUB_FALLBACK` / `ALLOW_STUB_FALLBACK` | not read (reserved names) | — | refused if truthy |
| `MIDNIGHT_ENABLED` | not read | compose `"false"` | removed from compose |
| `ZK_PROOF_ENABLED` | brandme-agents/identity/src/main.py:25 | `"true"` | identity service refused regardless (registration) |

## Test-only mocks (not production paths)

`brandme-chain/tests/mocks/cardano-mocks.ts:141`, `midnight-mocks.ts:50,56,68`, `tests/setup.ts:17-18`, `tests/services/blockchain.test.ts:22-23,202,211` force fallback flags on. The suite `tests/integration/cardano-testnet.test.ts` is gated on `INTEGRATION=true` plus real credentials.
