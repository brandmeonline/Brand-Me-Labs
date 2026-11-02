# Static journey wiring trace — brandmeonline/Brand-Me-Labs @ `ed19dc151d103b108cf972e6d37971c55d5dcf60`

Audit date 2026-11-01, second (independent) audit run. Every claim cites `file:line` at this SHA; quotes are
≤160 characters and verbatim. "Breaks at" names the exact boundary at which a journey stops being wired.
Runtime observations (screenshots, 503 responses) come from the audit's own local run with the frontend only;
see `../runtime/commands.md` and `../../visuals/screenshots/manifest.json`.

Legend for each chain: **UI entry → BFF/gateway route → domain handler → store**.

---

## 1. Route inventory

### brandme-frontend (`app/**/page.tsx`, 31 pages + 4 route handlers)

| Route | File | Data source at this SHA |
|---|---|---|
| `/` | `app/page.tsx` | static marketing; no gateway call (observed: no `/api/v1` requests) |
| `/start` | `app/start/page.tsx` | static; guest onboarding entry |
| `/today` | `app/today/page.tsx` → `features/persona/today.tsx:9-10` | `useResource('/recommendations')`, `useResource('/wardrobe/items?collection=owned&limit=6')` |
| `/add`, `/add/scan` | `app/add/page.tsx:5-7`, `app/add/scan/page.tsx` | guest IndexedDB closet (see §3); scan page states "Scanning is not connected yet" (observed) |
| `/closet`, `/closet/settings`, `/closet/items/[itemId]` | `app/closet/page.tsx:5-7` | guest IndexedDB closet (see §3) |
| `/style`, `/style/outfits/[outfitId]` | `features/closet/StylePage.tsx:20` | IndexedDB `brandme.spatial.guest-outfits.v1` |
| `/discover` | `app/discover/page.tsx` → `features/commerce/catalog.tsx:59-60` | `useResource('/catalog/search?q=…')` (unmounted at gateway, §6) |
| `/products/[productId]` | `features/commerce/catalog.tsx:153` | `useResource('/catalog/products/<id>')` (unmounted at gateway, §6) |
| `/circle`, `/circle/decisions/new`, `/circle/decisions/[decisionId]` | `features/social/circle.tsx:16-17,33,38,49` | `/decisions`, `/relationships`, `/wardrobe/items`, `command('/decisions')` |
| `/rewards` | `features/rewards/rewards.tsx:45-46` | `/rewards`, `/benefits` (+ `/rewards/reservations`, observed) |
| `/inbox` | `features/social/inbox.tsx:32,64` | `/notifications`, `command('/notifications/read')` |
| `/me` | `app/me/page.tsx` | static directory of links; hard-coded guest copy (see §7) |
| `/me/style` | `features/persona/looking-glass.tsx:15,37,50` | `/me/persona`, `/me/persona/evidence`, `command('/me/persona/preview')` |
| `/me/data`, `/me/data/exports/[jobId]`, `/me/data/deletion/[jobId]` | `features/privacy/my-data.tsx:81,84,118,252,327` | `/me/data`, `/me/exports/capability`, `/me/exports`, `/me/exports/<id>`, deletion receipt |
| `/me/connections` | `app/me/connections/page.tsx:4` → `features/privacy/connections.tsx` | `/me`, `command('/session/dev')`, `DELETE /session` |
| `/orders` | `app/orders/page.tsx` | static `AvailabilityState`: "Orders are not connected in this preview." |
| `/assistant` | `app/assistant/page.tsx` | static `AvailabilityState`: "Your assistant is not connected in this preview." |
| `/settings` | `app/settings/page.tsx` | localStorage experience preferences (`lib/client/experience-preferences.tsx:23`) |
| `/scan` | `app/scan/page.tsx:1` | `import { resolveScanAndFetchPassport } from '@/lib/demoData'` — hard-coded mock ("Mock backend response data", `lib/demoData.ts:2`) |
| `/governance` | `app/governance/page.tsx:1` | `import { getEscalations } from '@/lib/demoData'` — hard-coded mock |
| `/try/[itemId]`, `/try/device-test`, `/try/photo/api` | `features/spatial/*` | device-local AR/photo preview; `BRANDME_TRYON_PROVIDER` unset → "photo_preview_not_configured" (`brandme_core/domains/persona/app.py:26-27`) |
| `/dev/[example]` | `app/dev/[example]/page.tsx` | component gallery |
| `/api/v1/[...path]` | `app/api/v1/[...path]/route.ts:1-8` | same-origin BFF proxy → `lib/server/gateway-proxy.ts` |
| `/shop`, `/stash` | `app/shop/route.ts`, `app/stash/route.ts:4` | redirects (`/stash` → 307 `/closet`) |

Build evidence: `next build` lists all 36 routes (`../runtime/logs/frontend-build.txt`).

### brandme-console (`app/**/page.tsx`, 13 pages)

`/` (`app/page.tsx`), `/dashboard`, `/dashboard/scans`, `/proof/[scanId]`, `/(ops)/commerce/operations`,
`/(ops)/moderation`, `/(ops)/providers`, `/(ops)/providers/[id]`, `/(ops)/providers/[id]/health`,
`/(ops)/providers/[id]/setup`, `/(ops)/rewards-disputes`, `/(ops)/rewards-disputes/members/[memberId]`.
Build evidence: 13 routes in `../runtime/logs/console-build.txt`. Wiring in §8.

---

## 2. Sign-in: how does the browser get a session?

**Chain (demo/development only):**
`features/privacy/connections.tsx:13` `command('/session/dev',{test_identity:identity})`
→ BFF `lib/server/gateway-proxy.ts:62-64` (allowed only when `BRANDME_MODE` ∈ {demo, development} and `NODE_ENV!=='production'`)
→ gateway `brandme-gateway/src/routes/v1/index.ts:86-105` `POST /session/dev`
→ `store.resolveMember(DEV_IDENTITY_ISSUER, test_identity, 'dev', …)` and `store.createSession(...)` (`index.ts:94-95`)
→ Spanner identity tables via `middleware/identity/store.ts`; cookie `bm_session` set (`index.ts:96`), header
`X-Brandme-Simulation: "Simulated sign-in: fictional test identity, not a verified account"` (`mode.ts:25`).

**Strict modes (sandbox/production):**
- `index.ts:89`: `if (isStrict(cfg.mode) || cfg.identityProvider !== 'dev') throw problems.notFound();` — `/session/dev` is a 404.
- `middleware/mode.ts:53-55`: `identity provider '${cfg.identityProvider}' is a simulation; set IDENTITY_PROVIDER=oidc`, `OIDC_ISSUER is required`, `OIDC_AUDIENCE is required` — the gateway refuses to boot otherwise (`assertGatewayMode`, `index.ts:82`).
- The only OIDC path is **bearer verification**: `middleware/session.ts:11-12` "Agents/API clients: `Authorization: Bearer <JWT>` verified against the OIDC issuer's JWKS…", implemented at `session.ts:79-85` (`jwtVerify(... issuer: cfg.oidcIssuer, audience: cfg.oidcAudience)`).
- **No authorization-code / PKCE / callback route exists.** `grep -rniE 'authoriz(e|ation_endpoint)|/callback|pkce|code_verifier|code_challenge|nonce|redirect_uri' brandme-gateway/src` (non-test) matches only comments (`mode.ts:12`, `tryon.ts:14`), an unrelated 401/403 message (`services/rights.ts:31`) and a zod field `nonce` in the unmounted commerce schema (`commerce.ts:194`). The frontend has no sign-in page or redirect logic either (`connections.tsx` is the only sign-in UI).

**Frontend behaviour:** `app/me/connections/page.tsx:4` computes `allowDev` from `NODE_ENV!=='production' && ['demo','development'].includes(BRANDME_MODE)`; otherwise `connections.tsx:27` renders "Account sign-in is not configured for this deployment. You can continue exploring as a guest."

**Breaks at:** for strict modes, the **browser has no way to obtain a session** — the gateway only verifies bearer JWTs minted elsewhere and the dev session endpoint is disabled; the UI has no OIDC flow. In demo/development the chain is complete to Spanner, but requires the gateway + Spanner emulator (`docker-compose.yml:157-186`).

Observed (no backend): `/me/connections` → `GET /api/v1/me → 503`, sign-in attempt → `GET /api/v1/session → 503`, status "This service is not connected or temporarily unavailable. No result is confirmed." (`me-connections-after-signin-attempt-*.png`).

---

## 3. Wardrobe / closet

**UI chain:** `app/closet/page.tsx:5-7` and `app/add/page.tsx:5-7` wrap `ClosetPage`/`AddItemPage` in `SpatialModeGate`
→ `features/closet/useCloset.ts:10-12` `useCloset(injected?: ClosetRepository)` … `injected ?? createGuestClosetRepository()`
→ `features/closet/repository.ts:267-268` `export function createGuestClosetRepository(namespace = "brandme.spatial.guest.v1")`
→ **IndexedDB only**: `repository.ts:284-286` `indexedDB.open(namespace, 1)` / `createObjectStore("closet")`; `persistenceLabel: "Guest demo · Saved on this device"` (`repository.ts:296`).
- The repo says so itself: `repository.ts:265-266` "Guest demo only. … A production host must inject an authenticated API implementation of ClosetRepository." No caller injects one (`grep createGuestClosetRepository|ClosetRepository` → only `useCloset.ts`, `PhotoPreview.tsx:224`, `photoMedia.ts:5`, prop types in `AddItemPage.tsx:29`, `ClosetPage.tsx:25`).
- `SpatialModeGate.tsx:12-23`: in `production`/`sandbox` it renders "Your wardrobe connection is not ready." instead of the closet.
- The `/add` page makes **no gateway call**: the only `fetch` in `features/closet/*` is an asset prefetch (`AddItemPage.tsx:97` `void fetch(prefetchUrl, { signal: abort.signal, cache: "force-cache" })`).

**Server wardrobe API exists but is not used by the closet UI:**
- Gateway `brandme-gateway/src/routes/v1/wardrobe.ts:62-135` defines `/wardrobe/items` (GET/POST), `/wardrobe/items/:itemId` (GET/PATCH), `/wardrobe/items/:itemId/duplicates/:otherId`, `/wardrobe/items/:itemId/worn`, `/closet/layout` (GET), `/closet/layout/theme` (PUT), `/closet/placements/:itemId` (PUT), `/closet/placements/batch` (POST), forwarded via `forwardTo(client, …)` to the consumer-domain service. The file header still says "UNMOUNTED router" (`wardrobe.ts:4`) but `routes/v1/index.ts:143-145` **does mount** `wardrobeRouter` (header comment stale).
- Domain: `brandme_core/domains/persona/app.py:71-72` `app.include_router(create_wardrobe_router(WardrobeService(database), OutfitService(...)))` → Spanner.
- Only two UI reads touch it: `features/persona/today.tsx:10` and `features/social/circle.tsx:33` (`/wardrobe/items`), both for display in Today/Circle — never the closet/add screens.

**Breaks at:** the **UI ↔ server boundary**: closet/add/style/try pages persist exclusively in the browser (`brandme.spatial.guest.v1`, `brandme.spatial.guest-outfits.v1`, `brandme.spatial.preview-media.v1`); the mounted gateway/domain wardrobe API has no closet-UI consumer, so items added in the closet never reach Spanner and items in Spanner never appear in the closet.

Observed: `/closet` renders a guest 3D room "Guest demo · Saved on this device · Fictional starter pieces" with zero `/api/v1` requests (`closet-desktop-1440x900.png`).

---

## 4. Persona / recommendations

**Chain:** `features/persona/today.tsx:9` `useResource('/recommendations')`
→ BFF proxy (root `recommendations` allowed, `gateway-proxy.ts:3`)
→ gateway `routes/v1/persona.ts` (mounted at `index.ts:143-145`) forwards to the consumer-domain service with a signed principal assertion (`services/domains.ts:38-43`)
→ `brandme_core/domains/persona/app.py:69-70` `persona = PersonaService(database)` / `create_persona_router(persona, …)`
→ `service.py:1148-1158` `recommendations(...)`: `result = recommend(self.candidate_source(principal), req).to_dict()`.

**Candidate sources are empty in the deployed composition:**
- `service.py:133-134` `candidate_source: Optional[CandidateSource] = None, wardrobe_source: WardrobeSource = _no_wardrobe,`
- `service.py:139` `self.candidate_source = candidate_source or (lambda _p: ())`
- `service.py:96-97` `def _no_wardrobe(_txn, _member_id) -> Sequence[WardrobeRef]: return ()`
- `app.py:69` passes **neither** (`PersonaService(database)`); the test harness does the same (`brandme-frontend/lib/testing/dev-domains.py:85`). Real sources are injected **only in tests** (`tests/test_persona_service.py:57`, `tests/test_wardrobe_service.py:307` `candidate_source=lambda _p: cands, wardrobe_source=svc.wardrobe_refs`).
- The recommender itself is real and deterministic (`recommender.py:1-20`, `recommend()` at `:220`), but with `()` candidates every call ranks nothing. No catalog-backed `CandidateSource` implementation exists in `brandme_core/domains/persona/` (grep `CandidateSource` → type alias and tests only).

**Breaks at:** **domain composition** (`app.py:69`): `/recommendations` is fully wired UI → gateway → domain → Spanner for the persona profile, but the candidate and wardrobe sources are no-ops, so the response can never contain products.

Observed (no backend): `/today` → `GET /api/v1/recommendations → 503`, `GET /api/v1/wardrobe/items → 503` (`today-*.png`).

---

## 5. Social decisions + rewards (outbox consumers)

**Write path (wired):** `features/social/circle.tsx:38` `command('/decisions', …)` → gateway `routes/v1/decisions.ts` (mounted `index.ts:143`) → `app.py:73-74` `create_social_router(... DecisionService(database) ...)` → Spanner, which also writes outbox rows (`brandme_core/events/outbox.py`).

**Who closes decisions and settles rewards?**
- Closing due decisions is a scheduled job: `brandme_core/domains/persona/jobs.py:5` `python -m brandme_core.domains.persona.jobs [--once]`, `:7-8` "`decisions.close_due`: close decisions whose server deadline passed and settle their counts".
- Applying event effects (rewards ledger etc.) is a Pub/Sub subscriber: `persona/ingress.py:1-2` "Pub/Sub ingress for this lane's event consumers (dev form)", `:159` `rewards = rewards or RewardsConsumer(database)`, run via `python -m brandme_core.domains.persona.ingress [--once]` (`ingress.py:27`).
- The foundation worker only **publishes**: `brandme_core/events/worker.py:1-4` "No wallet, chain submission, topic creation, or application side effects. This process only publishes registered committed events…". It does load the lane catalogs (`events/catalogs.py:32` `Catalog("consumer-domains", "brandme_core.domains.persona.lane", loader="load_domains")`).

**Where is any of this deployed?**
- `docker-compose.yml`: services are `spanner-emulator, firestore-emulator, spanner-migrate, brain, policy, orchestrator*, knowledge*, compliance*, identity*, governance*, cube*, node-install, gateway, consumer-domains, consumer, nats*` (`*` = `profiles: [legacy]`/`[events]`, lines 110-150, 230-235). **No jobs, ingress or outbox-worker service.** `docker-compose.dev.yml:7-36` adds only `console` and env overrides.
- Helm `brandme-infra/helm/brandme/templates/core-workloads.yaml:3-9` deploys `read-api`, `exports-api`, `exports-worker`, `events-worker` (`python -m brandme_core.events.worker`), `events-retention` CronJob, `consumer-domains` (API only, `values.yaml:191` `enabled: false` by default). **No Deployment/CronJob runs `persona.jobs` or `persona.ingress`.**
- `scripts/brandme.mjs` invokes `OutboxDispatcher(...).run_once()` only inside `smoke` (`brandme.mjs:258`) with a validating no-op `deliver`.
- The only process that wires `RewardsConsumer` to a dispatcher loop is the **test harness**: `brandme-frontend/lib/testing/dev-domains.py:92-96` `dispatcher = OutboxDispatcher(database, RewardsConsumer(database).handle)` … `worker = threading.Thread(target=settle_rewards, daemon=True)`.
- `grep -rn 'RewardsConsumer('` outside `tests/` → only `dev-domains.py:92` and `ingress.py:159`.

**Breaks at:** the **event-consumer boundary**: decisions are created and outbox rows are written, but in every deployable topology (compose, Helm) nothing closes due decisions or consumes the events, so rewards never settle; the end-to-end behaviour exists only in `dev-domains.py` (CI's `consumer-ui.yml` "live-domains" harness).

Observed (no backend): `/circle` → `GET /api/v1/decisions → 503`, `GET /api/v1/relationships → 503`; `/rewards` → `GET /api/v1/rewards → 503`, `GET /api/v1/benefits → 503`.

---

## 6. Commerce / assistant / providers

**Gateway routers exist but are not mounted.** `brandme-gateway/src/routes/v1/index.ts:18-33` imports only `me, chain, rights, ownership, assets, privacy, persona, wardrobe, outfits, social, decisions, rewards, media, tryon`; mounts at `:132-145`. The commerce family — `createCommerceRouter` (`commerce.ts:204`), `createCommerceOpsRouter` (`:239`), `createCommerceWebhookRouter` (`:255`), `createCatalogRouter` (`catalog.ts:22`), `createAssistantRouter` (`assistant.ts:27`), `createProvidersRouter` (`providers.ts:121`), `createCapabilitiesRouter` (`:140`), `createDelegationsRouter` (`delegations.ts:78`) — is imported **only by `commerce.test.ts:13-21`** ("Router boundary tests for the unmounted commerce routers", `commerce.test.ts:2`). The catch-all at `index.ts:147` returns `problems.notFound()` for `/catalog/*`, `/assistant/*`, `/providers/*`, `/delegations/*`, `/commerce/*`.

**UI side:** `features/commerce/catalog.tsx:59-60,153` calls `/catalog/search` and `/catalog/products/<id>`; the BFF allows those roots (`gateway-proxy.ts:3-5`) and blocks `commerce/ops` and provider writes (`:58-61`). `/assistant` and `/orders` pages are static placeholders (`app/assistant/page.tsx`, `app/orders/page.tsx`: "…not connected in this preview").

**Python side:** `brandme_core/domains/commerce/http_api.py:638` `def create_commerce_app(api: CommerceHttpApi) -> FastAPI:` is called only by `tests/test_commerce_http.py:41` and `tests/test_commerce_payments_flow.py:1097`. No `__main__`, no compose service, no Helm workload references `brandme_core.domains.commerce` or `brandme_core.orchestrator` (`grep` over `docker-compose*.yml`, Helm templates/values → no match). `commerce/composition.py:1` documents provider selection ("simulated (default) or stripe_test; demo/development only") but nothing starts it.

**MCP:** `brandme_core/mcp/` contains `authz.py, consent.py, refs.py, schemas/, tools.py` — a tool registry and executor (`tools.py:83` `TOOLS`, `:122` `UNAVAILABLE_TOOLS`, `:134` `RETIRED_TOOLS`) with **no server/transport**: no `def main`, no `__main__`, no `mcp.server`/`FastMCP` import. Its only non-test importers are `brandme_core/orchestrator/{runtime,composition,anthropic_adapter,model_adapter,runlog}.py`, which likewise have no entrypoint. There is **no `mcp-server` service** anywhere (`.mcp.json` is the Claude Code `@21st-dev/magic` dev tool, unrelated).

**Breaks at:** the **gateway mount** (`index.ts:132-145`) for catalog/assistant/providers/delegations, and the **process boundary** for the commerce domain and MCP executor (code exists, no runnable service, no deployment). CLAUDE.md's note that commerce handlers "exist" in `tools.py` is accurate; they are reachable only from tests.

Observed: `/discover` renders the search box with no request until a query is typed; `/assistant` and `/orders` render the static "not connected" copy.

---

## 7. Account / privacy

**`/me` for a signed-in member:** `app/me/page.tsx:52-86` is a static directory; the identity block is hard-coded guest copy regardless of session: `:66-69` "You're exploring without an account. No style profile has been inferred or saved." It never calls `/me`. The signed-in view lives on `/me/connections` (`connections.tsx:15-21`: display name, environment, `identity_provider`, member id, capabilities list) and `/me/data`.

**Gateway `/me` family (mounted):**
- `routes/v1/me.ts:89-98` `GET /me`, `PATCH /me` (Spanner identity store).
- `routes/v1/privacy.ts` (mounted at `index.ts:136` under `/me`): `GET /me/data` (`:40`), `GET /me/exports/capability` (`:58`), `POST /me/exports` (`:69`), `GET /me/exports/:jobId` (`:83`), `GET /me/exports/:jobId/download` (`:92`), `POST /me/deletion` (`:104`), `GET /me/deletion/:jobId` (`:116`). Exports require `deps.upstream.exports` (`:62,77,88,97` → `problems.unavailable('Exports are not configured.')`) i.e. `PRIVACY_EXPORT_SERVICE_URL`+token (`services/rights.ts:84`); `/me/data` and deletion go through the rights/privacy client (`services/rights.ts:13` `if (!base || (authenticated && !token)) throw problems.unavailable('This service is not configured.')`). Those backends are `python -m brandme_core.read_api` / `brandme_core.privacy_exports` (Helm `core-workloads.yaml:4-6`), **absent from docker-compose.yml**.

**"Clear guest data" coverage:** `connections.tsx:20` on sign-out calls `clearGuest()` when the switch is on; `features/persona/onboarding.tsx:37` `export function clearGuest() { localStorage.removeItem(KEY);localStorage.removeItem(PENDING) }` with `KEY='brandme:guest:v1'` (`:11`) and `PENDING='brandme:guest-migration:v1'` (`:12`).

Every browser store created by the frontend (grep `indexedDB|localStorage|sessionStorage`, non-test):

| Store | Created at | Cleared by `clearGuest()`? |
|---|---|---|
| localStorage `brandme:guest:v1` | `features/persona/onboarding.tsx:11,48` | yes |
| localStorage `brandme:guest-migration:v1` | `onboarding.tsx:12,29` | yes |
| IndexedDB `brandme.spatial.guest.v1` / store `closet` (whole guest closet) | `features/closet/repository.ts:268,284-286` | **no** |
| IndexedDB `brandme.spatial.guest-outfits.v1` / store `outfits` | `features/closet/StylePage.tsx:20-22` | **no** |
| IndexedDB `brandme.spatial.preview-media.v1` / store `media` (intake photos) | `features/spatial/previewMedia.ts:12-14` | **no** |
| localStorage `brandme:guest:spatial:fit-history:v1` (+ `…:reset-generation:v1`) | `features/spatial/fitHistory.ts:2-4`, used by `FitLadder.tsx:39-88` | **no** (own "clear history" button only, `FitLadder.tsx:77`) |
| localStorage `brandme.spatial.camera.v1:<room>` | `features/spatial/cameraPreferences.ts:11,57` | **no** |
| sessionStorage `brandme.ar.return` | `features/spatial/ModelPreview.tsx:108-109`, `NativeDeviceSession.tsx:41` | **no** (session-scoped) |
| localStorage `brandme:experience:v1` (theme/motion/contrast) | `lib/client/experience-preferences.tsx:23,114`; read by inline bootstrap `preference-bootstrap.ts:2` | **no** (per-device display preference; arguably not guest data) |

**Breaks at:** (a) `/me` never reflects the signed-in member (static copy at `app/me/page.tsx:66-69`); (b) "clear guest data on this device" clears 2 of 9 stores — the guest closet, outfits, intake photos and fit history survive sign-out; (c) data inventory/export/deletion need the read API and privacy-exports services, which have no local compose definition and are 503 (`problems.unavailable`) until configured.

Observed (no backend): `/me/data` → `GET /api/v1/me/data → 503`; `/me` shows the hard-coded "You're exploring without an account" block (`me-*.png`, `me-data-*.png`).

---

## 8. Governance console and ops routes

- **brandme-console → gateway:** `app/(ops)/moderation/_lib/ops-gateway.ts:47` `res = await fetch(`${base}/api/v1/ops${path}`, …)` with `base = process.env.BRANDME_GATEWAY_INTERNAL_URL` (`:32`), used by moderation and rewards-disputes (`rewards-disputes/actions.ts:38,52` → `/rewards/disputes/<id>/resolve`, `/rewards/members/<ref>/entries/<id>/reverse`). Providers pages use `providers/_data/gateway.ts:53,63` `fetch(`${base}/api/v1${path}`)` with `BRANDME_GATEWAY_URL` and require an operator `Bearer` header (`:56-58`).
- **Gateway:** `routes/v1/index.ts` mounts **no** `/ops` router and **no** providers router. The ops routers exist unmounted: `rewards.ts:85` `export function rewardsOpsRouter(client)` (`/ops/rewards/disputes`, `/ops/rewards/members/:memberRef/ledger`, `/ops/benefits`, `/ops/rewards/contributions`, `:90-140`), `social.ts:175` `export function moderationOpsRouter(client)` (`/ops/moderation/reports`, `:179-183`), `commerce.ts:239` `createCommerceOpsRouter`, `providers.ts:121` `createProvidersRouter`. Index imports only `socialRouter`/`rewardsRouter` (`index.ts:29,31`) → `/api/v1/ops/*` and `/api/v1/providers/*` hit the catch-all `problems.notFound()` (`index.ts:147`).
- **Domain:** `brandme_core/domains/persona/app.py:13-14` "Not mounted: the `/ops` moderation and dispute routers. Operator authority needs the console's own authentication (ch.03 §3), which does not exist yet." (`create_moderation_ops_router` at `social/api.py:176`, `create_rewards_ops_router` at `rewards/api.py:71` are never included.)
- **Console's own auth:** `ops-gateway.ts:8-14` "The console shell is not an authorization boundary… How the console's session reaches the gateway … is an integration decision (proposal PD-18)."
- Legacy console pages `/dashboard`, `/dashboard/scans`, `/proof/[scanId]` have no gateway fetch (only `NEXT_PUBLIC_CARDANO_EXPLORER_URL` link at `proof/[scanId]/page.tsx:159`); the frontend's own `/governance` page uses `lib/demoData.ts` mocks (§1).
- Python `brandme-governance` (port 8006) is a separate legacy FastAPI service under `profiles: [legacy]` (`docker-compose.yml:138-143`); nothing in brandme-console calls it.

**Breaks at:** the **gateway mount** (`/api/v1/ops/*` and `/api/v1/providers/*` → 404) and, behind it, the **domain mount** (`app.py:13-14`); additionally no operator authentication exists. Every console ops screen therefore ends in `unconnected`/`error` states (`ops-gateway.ts:38,54,59-67`).

---

## 9. docker-compose vs. docker-compose.dev.yml; Helm/K8s

**`docker-compose.yml` (242 lines, 16 services, 0 `healthcheck:` blocks, 0 commented-out services):**

| Service | Profile | Image/command | Notes |
|---|---|---|---|
| `spanner-emulator` | default | `gcr.io/cloud-spanner-emulator/emulator:1.5.45` (`:75`) | ports 9010/9020 |
| `firestore-emulator` | default | `google-cloud-cli:587.0.0-emulators` (`:82-83`) | port 8080 |
| `spanner-migrate` | default | `python brandme-data/spanner/migrations/runner.py up --create-database --wait 60` (`:96`) | gate for Python services (`:61-63`) |
| `brain` 8000, `policy` 8001 | default | `uvicorn main:app` after `python -m brandme_core.config preflight` (`:101,:107`) | real |
| `orchestrator` 8002, `knowledge` 8003, `compliance` 8004, `identity` 8005, `governance` 8006, `cube` 8007 | **`legacy`** (`:112,119,126,133,140,147`) | not started by default | |
| `node-install` | default | `corepack enable && pnpm install --frozen-lockfile` (`:155`) | one-shot |
| `gateway` 3001 | default | `pnpm --filter @brandme/gateway dev` (`:159`); `IDENTITY_PROVIDER: ${IDENTITY_PROVIDER:-dev}` (`:171`); `CONSUMER_DOMAIN_SERVICE_URL: http://127.0.0.1:8010` (`:176`) | needs gitignored dev key env file (`:178-180`) |
| `consumer-domains` 8010 | default | `python -m brandme_core.domains.persona.app` in the gateway's network namespace (`:200,:211`) | refuses to start without `CONSUMER_DOMAIN_ASSERTION_JWKS` (`:211` "no dev key pair; run node scripts/dev/consumer-domain-keys.mjs"); media/try-on unmounted (`:193-194`) |
| `consumer` 3000 | default | `next dev -p 3000` with `BRANDME_GATEWAY_URL: http://gateway:3001` (`:220-222`) | |
| `nats` | **`events`** (`:232`) | legacy `/scan` publisher only | |

Absent from compose entirely: `brandme-chain`, `brandme-console` (base file), read API, privacy exports, outbox worker, persona jobs/ingress, commerce domain, MCP/orchestrator, any Cardano/Midnight stub.

**`docker-compose.dev.yml` (36 lines):** overrides `BRANDME_MODE=development` for `brain`, `policy`, `gateway`, `consumer-domains` (`:8-21`) and adds `console` on 3002 (`:23-36`, `next dev -p 3002`, `BRANDME_GATEWAY_URL: http://gateway:3001` but **not** `BRANDME_GATEWAY_INTERNAL_URL`, which the ops pages read at `ops-gateway.ts:32`). Note: CLAUDE.md's statement that the console block is "commented out in `docker-compose.dev.yml:168-184`" is stale at this SHA — the file has 36 lines and the console service is active.

**Helm (`brandme-infra/helm/brandme/`, Chart.yaml:8 "strict-mode foundation workloads for GKE (gateway, chain, console, read API, privacy exports, outbox worker and retention, migrations)"):** templates deploy `gateway` (`gateway.yaml:14`), `chain` (`chain.yaml:13`), `console` (`console.yaml:14`), core workloads `read-api`, `exports-api`, `exports-worker`, `events-worker`, `consumer-domains` (`core-workloads.yaml:3-9`, `_core.tpl:23`), `events-retention` CronJob (`core-workloads.yaml:87`), `migrations` Job (`migrations-job.yaml:51`), plus `ingress.yaml` (disabled, `values.yaml:313`), `networkpolicy.yaml`, `pdb.yaml`, `serviceaccounts.yaml`, `validate.yaml`. Defaults (`values.yaml`): gateway/chain/console/readApi/exportsApi/exportsWorker/eventsWorker/eventsRetention/migrations `enabled: true`; `consumerDomains.enabled: false` (`:191`, comment `:189-190` "While it is off the gateway answers 503 on every consumer-domain route."). No workload for brain/policy/orchestrator/cube/agents/governance, persona jobs/ingress, commerce, or MCP. `brandme-infra/helm/brandme-umbrella/` is marked legacy (`LEGACY.md`). `infrastructure/helm/brandme/templates/cube-service.yaml:3` is a lone legacy cube Deployment; `infrastructure/kubernetes/namespace.yaml` plus observability configs (loki, otel, prometheus, redis) have no workloads.

**Breaks at:** compose's default profile reaches `consumer → gateway → consumer-domains → Spanner emulator` only after a manual key-pair step, with no event consumers; Helm's strict profile ships the publisher side (events-worker) and read/export APIs but leaves `consumerDomains` off by default and has no consumer/jobs workloads at all.

---

## Summary of break points (most consequential first)

1. **Closet is browser-only.** `features/closet/useCloset.ts:12` `injected ?? createGuestClosetRepository()` + `repository.ts:265-266`; the mounted `/wardrobe/*` API (`routes/v1/wardrobe.ts`, `persona/app.py:71`) has no closet-UI consumer.
2. **Recommendations rank nothing.** `persona/app.py:69` `PersonaService(database)` leaves `service.py:139` `candidate_source or (lambda _p: ())` and `:134` `_no_wardrobe` in force; only tests inject sources.
3. **No deployed event consumer or decision closer.** `persona/jobs.py:5`, `persona/ingress.py:27` are CLI-only; `events/worker.py:3-4` is publish-only; compose/Helm define no such workload; `RewardsConsumer` is wired only in `brandme-frontend/lib/testing/dev-domains.py:92`.
4. **Commerce/catalog/assistant/providers/delegations and all `/ops` routers are unmounted** at `routes/v1/index.ts:132-145` (imported only by `commerce.test.ts:13-21`), and `/ops` is also unmounted in the domain (`persona/app.py:13-14`); `create_commerce_app` (`commerce/http_api.py:638`) and the MCP executor (`brandme_core/mcp/tools.py`) have no process entrypoint or deployment.
5. **No browser sign-in outside dev.** `routes/v1/index.ts:89` disables `/session/dev` in strict modes; `middleware/session.ts:79-85` verifies bearer JWTs only; no authorize/callback/PKCE route or page exists.
6. **Guest-data cleanup is partial.** `onboarding.tsx:37` clears 2 localStorage keys; three IndexedDB databases and the spatial localStorage keys persist after sign-out.
