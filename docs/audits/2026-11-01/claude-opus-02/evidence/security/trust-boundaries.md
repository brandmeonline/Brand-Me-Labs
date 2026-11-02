# Trust boundaries — independent static review (S2)

Repository: `/home/user/Brand-Me-Labs`, branch `claude/busy-dirac-nhm16m`, HEAD `ed19dc151d103b108cf972e6d37971c55d5dcf60` (== origin/main). Audit date 2026-11-01. Static review only; no code executed, nothing modified. Prior audit material under `docs/audits/` was not read.

Legend: **Enforced** = present in code at the cited lines. **Missing** = not present, or present only as a comment/plan. **Gated** = unsafe behaviour exists but is refused by a mode guard at boot.

---

## A. Gateway (`brandme-gateway/src`)

### Coverage
- **Read fully:** `index.ts`, `config/index.ts`, `config/logger.ts`, `middleware/session.ts`, `middleware/mode.ts`, `middleware/auth.ts`, `middleware/rateLimiter.ts`, `middleware/errorHandler.ts`, `middleware/problem.ts`, `middleware/requestLogger.ts`, `middleware/logPath.ts`, `middleware/validation.ts`, `middleware/identity/store.ts`, `routes/health.ts`, `routes/scan.ts`, `routes/v1/index.ts`, `routes/v1/commerce.ts`, `routes/v1/chain.ts`, `routes/v1/privacy.ts`, `routes/v1/me.ts`, `routes/v1/persona.ts`, `routes/v1/rights.ts`, `routes/v1/ownership.ts`, `routes/v1/assets.ts`, `services/rights.ts`, `services/domains.ts`, `services/nats.ts`, `types/index.ts`, `Dockerfile`, `.env.example`, `package.json`.
- **Sampled (grep only):** `routes/v1/{wardrobe,outfits,social,decisions,rewards,media,tryon}.ts` (confirmed they are mounted and import the shared `requirePrincipal`/`requireScope`/`objectBody` helpers from `persona.ts`); test files for `mode`, `rateLimiter`, `v1-routes` (to confirm guard tests exist).
- **Not reviewed:** `routes/v1/{delegations,providers,catalog,assistant,read-query}.ts` bodies beyond confirming they are **unmounted** (no import in `routes/v1/index.ts`); `brandme-frontend`, `brandme-console` beyond an env-variable grep.

### Route mounting and middleware order — `index.ts:30-79`
1. `app.disable('x-powered-by')` (`:32`); `app.set('trust proxy', cfg.trustProxy)` (`:35`, default **off**).
2. `helmet` with an explicit CSP (`:36-42`).
3. `cors` with an allowlist callback; unknown origins get **no** CORS headers; `credentials: true`; explicit header lists (`:43-58`).
4. `requestLogger` (`:59`) → `requestContext(cfg.mode)` (`:60`: X-Request-Id normalisation, `Cache-Control: private, no-store`).
5. `/healthz`, `/health` mounted **before** the limiter (`:63-64`).
6. `ipRateLimiter(cfg)` — pre-auth, per client address (`:65`).
7. `/api/v1` → `apiV1()` (`:66`), which internally applies `express.json({limit:'256kb'})`, `principalMiddleware`, `principalRateLimiter` (`routes/v1/index.ts:62-65`).
8. `/scan` → `express.json({limit:'1mb'})`, `principalMiddleware`, `authMiddleware` (requires principal), `principalRateLimiter(cfg,'scan')` (`:68-75`).
9. `errorHandler` (`:77`).

**Enforced:** body-size limits (256 KB API, 1 MB legacy scan); helmet/CSP; CORS allowlist; request-id sanitisation (`problem.ts:74-83`: inbound X-Request-Id accepted only if UUID). **Missing:** app-level 404 handler outside `/api/v1` (Express default response); graceful shutdown (`index.ts:106-107` → `process.exit(0)` on SIGTERM; see S2-SEC-009).

### Identity — `middleware/session.ts`
- **Bearer (agents):** refused unless `identityProvider==='oidc'` and issuer+audience configured (`:80`). `jose.jwtVerify` with `issuer`, `audience`, `algorithms: cfg.oidcAlgorithms` (default `RS256,ES256`, `config/index.ts:81`), `clockTolerance: 30` s (`:83-88`). JWKS: `createRemoteJWKSet(uri, { cooldownDuration: 30_000, cacheMaxAge: 600_000 })` (`:72`); URI defaults to `<issuer>/.well-known/jwks.json` (`:71`). Verified `(iss, sub)` → member via `store.resolveMember` which **JIT-creates** a member (`identity/store.ts:162-215`). Scopes copied from the token `scope` claim (`:94`); `assuranceLevel: 'aal1'` hardcoded (`:101`); `clientId` from `azp`/`client_id` (`:99`). No client allowlist (S2-SEC-014).
- **Cookie (browser):** `bm_session` → server-side `Sessions` row by `sha256(secret)`; only unrevoked, unexpired and **same-environment** rows load (`identity/store.ts:238-248`). Cookie flags: `HttpOnly; SameSite=Lax; Secure` (Secure omitted in demo/development) (`session.ts:51-55`). First-party sessions receive the full member scope list including `privacy:manage`, `rights:transfer` (`:130-132`).
- **CSRF:** on POST/PUT/PATCH/DELETE with a cookie session: `Origin`, **when present**, must be in `PUBLIC_ORIGINS`; `X-CSRF-Token` is **always required** and compared constant-time to the stored hash (`:116-121`). The token is only obtainable via same-origin `GET /api/v1/session` (rotates it; `routes/v1/index.ts:109-118`). Absent-Origin requests pass on token alone (acceptable: double-submit-equivalent).
- **Dev identity:** `POST /api/v1/session/dev` returns 404 when `isStrict(mode)` or provider != `dev` (`routes/v1/index.ts:89`); otherwise mints a session for any `test_identity` matching `^[a-z0-9_-]{1,40}$` with `assurance_level: 'simulated'` and sets `X-Brandme-Simulation` (`:90-103`). **Gated** by `mode.ts:53` (strict modes refuse `IDENTITY_PROVIDER!=oidc` at boot) and tested (`mode.test.ts:19-21`).
- `middleware/auth.ts` is now only an adapter that copies `principal.memberId` onto `req.user` for the legacy `/scan` route (`:16-21`).

### Mode guard — `middleware/mode.ts`
Strict (`sandbox|production`) refuses: non-OIDC identity; missing/plaintext `OIDC_ISSUER`/`OIDC_JWKS_URI`; any non-`RS|PS|ES(256|384|512)|EdDSA` algorithm; `JWT_SECRET`; stub flags (`ENABLE_STUB_MODE`, `MIDNIGHT_FALLBACK_MODE`, `CARDANO_FALLBACK_MODE`, `ALLOW_STUB_FALLBACK`, `ZK_ALLOW_STUB_FALLBACK`, truthy = 1/true/yes/on); non-https `PUBLIC_ORIGINS`/`CORS_ORIGINS`; `SPANNER|FIRESTORE|PUBSUB_EMULATOR_HOST`; a backend URL without its token; identical service tokens (`:45-77`). Non-strict only checks OIDC completeness (`:47-52`). **Missing:** no check of `TRUST_PROXY` plausibility or of `CONSUMER_DOMAIN_ASSERTION_KEY` presence in strict modes.

### Rate limiting — `middleware/rateLimiter.ts`
Token buckets, **in-memory per process**, LRU-bounded (`RATE_LIMIT_MAX_KEYS`, default 10 000) (`:24-30`, `:55-108`). Tier 1 keyed by `req.ip` (IPv6 by /64) for every route except health probes (`:206-217`); Tier 2 keyed by member when a principal exists, exempting read-only, export and sign-out (`:139-152`, `:219-230`). 429 is problem+json with `Retry-After`; logs carry key *kind*, never the key (`:189-196`). **Bypass via X-Forwarded-For:** only if `TRUST_PROXY` is set wider than the real hop count; `true` is refused at config parse (`config/index.ts:53-56`); covered by `rateLimiter.test.ts:143-149`. See S2-SEC-017.

### Error handling / logging
`problem.ts:133-143`: unknown errors → generic 500 problem; only `errName` and templated path logged. `requestLogger.ts:41-57`: templated path (identifier segments → `:id`, `logPath.ts:30-40`), no query string, no UA. Pino redaction list `config/logger.ts:13-41`. Exception: `services/nats.ts:19` logs the raw NATS URL (S2-SEC-010). Some v1 routers return plain JSON errors with zod `issues` (S2-SEC-012).

### Health / readiness
`/healthz` always 200 (`routes/health.ts:16-22`). `/api/v1/system/health` (unauthenticated) checks Spanner + brain and returns `environment` (`routes/v1/index.ts:68-83`) (S2-SEC-013). Dockerfile HEALTHCHECK hits `/healthz` (`Dockerfile:21`).

### Commerce and downstream clients
- `routes/v1/commerce.ts` is **unmounted** (header `:4`; no import in `routes/v1/index.ts`). Its design rejects identity fields in body/query (`:48-49,96-104`), distinguishes first-party sessions from agents (`:53-54,62-73`), requires the trusted surface for approvals (`:86-94`), requires `Idempotency-Key` 16–128 chars for money-moving calls (`:116-123`), and signs an ES256 assertion (`aud brandme:commerce-domain`, ≤60 s, unique `jti`) per request (`:308-320`).
- Mounted routers never read `user_id`/`member_id` from request fields (grep for `req.(body|query|params).(user_id|member_id|owner_id|subject)` in non-test gateway sources returned nothing; `persona.ts:53,91-93` rejects identity keys in bodies).
- `services/rights.ts:11-55`: fixed-token upstream client; strips provider error bodies, caps responses at 1 MB, `redirect: 'error'`, never forwards the caller's token; passes the member as `x-subject-ref` (S2-SEC-025). `services/domains.ts:28-35`: ES256 assertion (`aud brandme:consumer-domains`, 30 s TTL, random `jti`), private key from `CONSUMER_DOMAIN_ASSERTION_KEY` (PKCS#8 in env; compose loads it from a gitignored env file outside the repo, `docker-compose.yml:177-180`).

---

## B. Python services and shared library

### Coverage
- **Read fully:** `brandme-core/brain/main.py`, `brandme-core/policy/main.py`, `brandme-core/orchestrator/main.py`, `brandme-governance/governance_console/main.py`, `brandme_core/boot.py`, `brandme_core/config.py`, `brandme_core/mcp/tools.py`, `brandme_core/mcp/authz.py`, `brandme_core/domains/persona/assertion.py`, `brandme_core/cors_config.py`.
- **Sampled (targeted reads/greps):** `brandme-core/orchestrator/worker.py` (head + hash sites), `brandme_core/orchestrator/{runtime,budget,anthropic_adapter,model_planner}.py`, `brandme_core/domains/commerce/{service,delegation,http_api}.py`, `brandme_core/domains/providers/{url_guard,catalog,payments/stripe_wire}.py`, `brandme_core/domains/privacy/privacy.py`, `brandme_core/events/retention.py`, `brandme_core/read_api/app.py`, `brandme_core/privacy_exports/{app,service}.py`, `brandme_core/domains/persona/app.py`, `brandme_core/spanner/{idempotent,pii_redactor}.py`, `brandme_core/logging.py` (redact_user_id), `brandme-cube/src/{main,api/faces,api/cubes,clients/policy_client}.py`, `brandme-agents/identity/src/main.py`, `brandme-agents/compliance/src/lifecycle/{esg_verifier,burn_proof}.py`, every `execute_sql`/f-string SQL site in `brandme_core` (grep).
- **Not reviewed:** full bodies of `brandme_core/domains/{wardrobe,social,rewards,media,rights}/*`, `brandme_core/spanner/consent_graph.py`, `brandme_core/firestore/*`, `brandme-agents/knowledge`, `brandme-data` migrations content, `tests/`.

### Boot guard (strict-mode refusal) — `brandme_core/boot.py`, `brandme_core/config.py`
`guard(service)` runs at import time and raises `BootRefused(SystemExit(3))` (`boot.py:56-67`). `enforce_boot_guard` (`config.py:646-674`): requires `BRANDME_MODE`; `ENVIRONMENT` may only echo it (`:145-160`); refuses legacy stub flags in strict modes (`:226-243`); refuses `SIMULATED` adapters in sandbox/production and `REAL`-only in production (`:185-190`); **unknown services are refused in strict modes** (`:667-669`). Inventory of simulated adapters: brain, orchestrator, identity, compliance, cube, mcp (legacy tools), policy, knowledge, governance (`:261-345`). Audited processes with configuration-derived classification: chain, read_api, privacy_exports, events_worker, events_retention, consumer_domains, gateway (`:556-602`). Compose runs `python -m brandme_core.config preflight --service X` before every Python service (`docker-compose.yml:101-149`), and the CI image smoke verifies sandbox `--check` refusals (`.github/scripts/smoke-image.sh:39-45`).

**Enforced:** fail-closed in sandbox/production for every legacy service. **Caveat:** `uvicorn --reload` would keep the port open after the child refuses (`boot.py:22-24`).

### Legacy services (brain, policy, orchestrator, governance, cube, identity, compliance)
- No caller authentication; identities come from bodies/paths (`brain/main.py:39-43`, `policy/main.py:41-52`, `identity/src/main.py:240-241`). **Gated** (S2-SEC-023).
- Governance decision endpoint writes body `reviewer_user_id` as `human_approver_id` (`governance_console/main.py:119-151`); list endpoint unauthenticated (`:71-72`). **Gated** (S2-SEC-002).
- Brain fabricates `stub_` hashes on orchestrator failure and discards the commit result (`brain/main.py:156-165, 278`); orchestrator returns `cardano_tx_<uuid>` (`orchestrator/main.py:91-92`); worker returns `tx_cardano_/tx_midnight_` (`worker.py:151-152`). **Gated** (S2-SEC-003).
- Policy: duplicate route definitions with a permissive shadowed transfer check and an undefined helper (`policy/main.py:203/548, 331/637, 577-581`) (S2-SEC-005). Policy fails **closed** to `escalate` on exceptions (`:185-200, 310-328, 444-459`) — good.
- Cube: no identity middleware; `request.state.get(...)` would raise (`cube/src/api/faces.py:24`, `main.py:168-175`) (S2-SEC-019).
- Compliance: stub ESG/burn-proof fallbacks (S2-SEC-020). `MIDNIGHT_ENABLED` is not referenced anywhere in code at this HEAD (grep over `brandme*`/`brandme_core`/compose returned nothing); the CLAUDE.md claim about `docker-compose.yml:304` is stale (the file is 242 lines).
- CORS: `brandme_core/cors_config.py:35-41` refuses `*` in strict modes; `allow_credentials: True`.
- SQL: all Spanner statements use `@param` bindings for values; f-strings interpolate only code-constant identifiers, except `pii_redactor.py:233-241` (`include_fields`) (S2-SEC-022).

### MCP executor — `brandme_core/mcp/tools.py`, `authz.py`
- Principal comes only from a verified gateway assertion (`tools.py:251-261`; `authz.py:149-232`): ES256 only, `kid` must be known, issuer/audience checked, `exp-iat ≤ 60 s`, ±30 s skew, `jti` single-use (in-memory), `environment` must match, session principals refused on the MCP hop (`authz.py:181-217`).
- Tool arguments: closed schemas (`additionalProperties: false`, `tools.py:54-55`); identity/scope/approval argument names rejected (`:50-51, 352-355`); payment card numbers and CVV-like strings rejected (`:356-361`); scopes = `spec.scopes ⊆ principal.scopes ∩ delegation.scopes` and a **member-granted delegation is mandatory** (`:367-379`); `Idempotency-Key` required for `cart.create` and `purchase.execute` (`:380-383`); audit record per call with keyed digests only (`:318-332`). Handlers at `:394-444` delegate to `CommerceService` (budgets: `service.py:851-933, 1396-1405`; idempotency scope per principal+operation `:274-283`).
- Retired fake tools return 410 with a replacement (`:133-156, 343-346`); unwired tools 501 (`:120-131, 347-348`).
- **Missing:** replay cache is per process (S2-SEC-018); no rate limit at the executor itself (relies on gateway).

### Consumer-domain hop — `brandme_core/domains/persona/assertion.py`, `persona/app.py`
ES256/kid/issuer/audience, TTL ≤ 60 s, bounded replay cache (`REPLAY_CACHE_MAX = 100_000`, `:31, 80-87`), environment match (`:89-90`), public-key-only JWKS (`:50-57`). App binds `127.0.0.1` in demo/development (`app.py:130`) and shares the gateway's network namespace in compose (`docker-compose.yml:200`); Spanner emulator required in dev and refused in strict (`app.py:91-92`).

### Internal read/export APIs — `brandme_core/read_api/app.py`, `privacy_exports/app.py`
Per-path static bearer compared with `hmac.compare_digest`, exactly one `Authorization` and one `X-Subject-Ref` header required (`read_api/app.py:70-81`; `privacy_exports/app.py:24-33`); `Cache-Control: no-store`, `Vary: Authorization, X-Subject-Ref`. Export download additionally requires `X-Reauth-At` (`privacy_exports/app.py:80-85`). Subject is client-chosen by the gateway (S2-SEC-025).

### Privacy and retention — `brandme_core/domains/privacy/privacy.py`, `events/retention.py`
Export/deletion need re-auth (`_check_reauth`, `privacy.py:93`; gateway enforces ≤ 600 s, `routes/v1/privacy.ts:19,69,92,104`); export links expire (`:226`); deletion writes tombstones and re-applies them after restores (`:276-316, 410-467`); backup retention 30 days (`:84-85`). Outbox: delivered rows purged after 7 days, erased-subject sweep window 30 days (`retention.py:49-50, 244-257, 295`). Logging: Python `redact_user_id` pseudonymises (`logging.py:298-306`); grep for logger calls carrying email/user_id/token in service code found none outside redaction helpers.

---

## C. Chain / wallet (`brandme-chain/src`)

### Coverage
- **Read fully:** `config/index.ts`, `index.ts`, `cardano/anchor.ts`, `midnight/adapter.ts`, `midnight/network.ts`, `midnight/capability.ts`, `routes/operations.ts`, `.env.example`.
- **Sampled:** `scripts/test-midnight-preprod.mjs` (lines 1-13), `scripts/fetch-compactc.sh` (checksum lines), `scripts/local-network.sh` (grep for seeds: none).
- **Not reviewed:** `midnight/{spanner-store,reconciler,reconciliation-worker,projection,private-state,rights-contract,redaction,indexer-query,operations}.ts`, `routes/{midnight,health}.ts`, `contracts/src/brandme_rights.compact`, test suites.
- **Note:** `brandme-chain/src/services/midnight-client.ts` (cited in CLAUDE.md) **does not exist** at this HEAD; `adapter.ts:5` says it replaced that stub.

### Keys, seeds, network
- No signing seed or private key is read by the service: proving/signing is done by a caller-supplied wallet (`ConnectedWallet`, `adapter.ts:91-98, 105-139`) or a loopback proof server (`:116-120`); a remote prover requires an explicit consent record (`:125-128`). Operator test wallets come only from `MN_PREPROD_SEEDS` in the Preprod script, which refuses to run without them and redacts them from output (`scripts/test-midnight-preprod.mjs:6-13`).
- Blockfrost project token from `MIDNIGHT_BLOCKFROST_PROJECT_ID`, shape-validated (`network.ts:36-38`) and embedded as `?project_id=` in URLs (S2-SEC-015).
- Network id checks: `assertWritable` refuses Mainnet writes with **no override switch** (`network.ts:79-86`); `assertSameNetwork` compares the wallet's reported network before proving, before balancing, before broadcast and after the journal commit (`adapter.ts:239, 266, 278, 289`).
- Replay protections: operation bound to owner, network, contract and request digest; state must be `ReadyToProve`; expiry honoured; tx identifier persisted **before** broadcast; provider-returned id must match (`adapter.ts:229-236, 280-293`); the reconcile route accepts only a tx id already persisted by the guarded submitter (`routes/operations.ts` reconcile handler).
- Fallback flags: `MIDNIGHT_FALLBACK_MODE`/`CARDANO_FALLBACK_MODE` throw when `=== 'true'` (`config/index.ts:33-38`) — narrower than the gateway/Python truthy set (S2-SEC-016). `ENVIRONMENT` defaults to `development` (`:15`).
- Stubbed/unavailable: Cardano anchoring is `UnavailableCardanoAnchor` (`cardano/anchor.ts:64-75`); `/tx/anchor-scan` and `/tx/verify-root` return 410 (`index.ts:58-63`); capability reports `writesAuthorized = false` and "member command submission is not configured" (`capability.ts:149-151`).
- Internal operations API: constant-time bearer check plus UUID `x-subject-ref`; 503 when unconfigured (`routes/operations.ts` middleware); graceful shutdown with 10 s deadline (`index.ts:81-91`).

---

## D. CI/CD — see `ci-cd-review.md`.

## E. Developer tooling

- `.mcp.json:4-9`: `npx -y @21st-dev/magic@latest API_KEY="${MAGIC_API_KEY}"` (S2-SEC-004). `.claude/settings.json:4-9` runs `.claude/hooks/session-start.sh` at SessionStart; the hook exports every `KEY=VALUE` line of gitignored `.claude/.env.local` into `$CLAUDE_ENV_FILE` (`:21-38`); no network access, no `curl|sh`.
- `curl|sh`/`wget|sh`: none in `*.sh`, `Makefile`, Dockerfiles, `*.mjs`, workflows (grep).
- Lifecycle scripts: no `preinstall/postinstall/prepare/husky` in any of the 10 tracked `package.json` files; no `.husky`, `.npmrc`, `.pnpmfile.cjs`. pnpm blocks dependency build scripts except an allowlist (`pnpm-workspace.yaml:13-19`).
- Dockerfiles: CI images (`brandme-gateway`, `brandme-chain`, `brandme-console`: `node:24.21.0-bookworm-slim`, `USER node`; `brandme-core` runtime: `python:3.11.15-slim`, `USER 10001:10001`; `brandme-agents`: `python:3.11-slim`, `USER brandme`) vs seven legacy root Dockerfiles on floating `python:3.11-slim` (S2-SEC-008). No Dockerfile copies `.env`, keys or secrets (grep).
- `docker-compose.yml`: emulators published on `0.0.0.0:9010/9020/8080` (local dev); Python containers mount the repo read-only (`:41`); gateway loads the assertion private key from `~/.config/brandme/dev-keys/*.env` (`:177-180`), never from the tree; no default passwords. `init.sql` is an orphan PostgreSQL schema (no Postgres service in compose).
- Makefile / `deploy-brandme.sh` / `agents/*.sh` / `scripts/{backup,db-init}.sh`: legacy path with `source .env.deploy`, SA key file, `--from-literal` secrets, default DB password (S2-SEC-021).

## F. Secrets — see `secret-scan.md`.

## G. Dependencies

- JS: single `pnpm-lock.yaml`; `packageManager: pnpm@10.34.6`; root `engines node >=20 <25`; `.nvmrc`/`.node-version` `24.21.0`; Dockerfiles default `NODE_VERSION=24.21.0`; advisories handled via `overrides` (`pnpm-workspace.yaml:21-44`); CI runs `pnpm audit --prod` and `--audit-level=critical` for the frontend (`ci-cd.yml:120-123`).
- Python: CI and compose install **only** `scripts/python/requirements.lock` (`--require-hashes`, 1341 `sha256:` lines, 90 packages); 17 `requirements*.txt` files remain (sampled: `==` pinned, unhashed) and are used only by legacy Dockerfiles/Makefile. No `.python-version`; CI uses `3.11` / `3.11.15`; compose `python:3.11.15-slim`.
- Docker tags: all compose/CI images are version-tagged (no `latest`); Trivy image digest-pinned; Helm refuses `latest` (`_helpers.tpl:92`). Only the Makefile pushes `:latest` (S2-SEC-008).
- Machine reference (this audit host): node v22.23.4 (differs from `.nvmrc`), pnpm 10.34.6, Python 3.13.18; `gitleaks`/`trivy` not installed; no audit tools were run.

## H. AI/agent surface

- `brandme_core/mcp`: see B. No shell/eval/subprocess in `brandme_core/mcp`, `brandme_core/orchestrator` or `brandme-agents/agentic` (grep).
- Assistant runtime (`brandme_core/orchestrator/runtime.py`): hard budgets (`:63-67`), per-step proposal cap, wall-clock deadline (`:332-345`), provenance rule that tool arguments must be identifiers vouched for by earlier **structured** results — `untrusted_text` never counts (`:498-562`); approval ids can never be produced in-task (`:556-558`). Provider text is normalised, control-stripped, capped and labelled `untrusted_text` (`domains/providers/catalog.py:20-24`). Cost ledger with task/member/environment ceilings (`budget.py:64-88`). Model adapter pins `api.anthropic.com` over https, refuses non-`sk-ant-api` keys, disables SDK env/proxy reads (`anthropic_adapter.py:73-77, 142-149`).
- Legacy LangChain CLI (`brandme-agents/agentic`): `scanner-id` is an unauthenticated CLI option (`cli/main.py:48`); tools POST model-supplied dicts to fixed internal URLs (`tools/blockchain_tools.py:20-45`, targets a retired `/tx/cardano` route); Neo4j password defaults to a literal (`graph_db.py:315`); `enforce_boot_guard("agentic")` refuses strict modes because `agentic` has no inventory entry (`cli/main.py:37`; verified by `smoke-image.sh:17`). No persistent cross-user memory found (no checkpointer/memory classes; grep).

## I. Privacy — see B (privacy/retention) and the gateway `routes/v1/privacy.ts` summary above. PII logging: no Python or TS logger call carrying email/user ids/tokens outside redaction helpers was found (grep); gateway pino `REDACT_PATHS` and templated paths; legacy `/scan` logs only `scan_id` and region (`routes/scan.ts:68`).
