# Branch static evidence excerpts

Captured 2026-11-01T14:35:21.6709131Z

Read only with git show; no repository code executed. Line numbers are one-based in the named immutable commit. Environment values and credentials are not included.

## brandme-data/spanner/migrations/runner.py @ ed19dc151d103b108cf972e6d37971c55d5dcf60

https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-data/spanner/migrations/runner.py#L91

```text
91: def load_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
92:     found: dict[int, Migration] = {}
93:     for path in sorted(directory.glob("*.sql")):
94:         m = FILE_RE.match(path.name)
95:         if not m:
96:             raise MigrationError(f"{path.name}: migration files must be named V<NNN>_<name>.sql")
97:         version = int(m.group(1))
98:         if version in found:
99:             raise MigrationError(f"duplicate migration version V{version:03d}")
100:         raw = path.read_bytes()
101:         statements = tuple(split_statements(raw.decode("utf-8")))
102:         if not statements:
103:             raise MigrationError(f"{path.name}: no statements")
104:         found[version] = Migration(version, m.group(2), path, hashlib.sha256(raw).hexdigest(), statements)
105:     return [found[v] for v in sorted(found)]
```

## tests/foundation/test_migrations.py @ ed19dc151d103b108cf972e6d37971c55d5dcf60

https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/tests/foundation/test_migrations.py#L24

```text
24:             7: "commerce", 8: "rights", 9: "privacy", 10: "rights_projection_version", 11: "chain_operation_store",
25:             12: "chain_reconciliation", 13: "outbox_delivery", 14: "privacy_exports",
26:             15: "commerce_quote_terms"}
27: 
28: 
29: @pytest.fixture
30: def v001_only(runner, tmp_path):
31:     """Foundation behaviour is tested against V001 alone; lanes add their reserved numbers independently."""
32:     d = tmp_path / "v001"
33:     d.mkdir()
34:     shutil.copy(REPO / "brandme-data/spanner/migrations/V001_identity.sql", d)
35:     return runner.load_migrations(d), d
36: 
37: 
38: def test_only_reserved_numbers_are_used(runner):
39:     for m in runner.load_migrations():
40:         assert m.version in RESERVED, f"V{m.version:03d} is not a reserved migration number"
41:         assert RESERVED[m.version] in m.name, f"V{m.version:03d} must be the {RESERVED[m.version]} migration"
42: 
43: 
44: def test_packaged_versions_are_contiguous_and_reserved_once(runner):
45:     """A gap lets a lower number merge after a higher one is applied; the runner refuses that in sandbox."""
46:     versions = [m.version for m in runner.load_migrations()]
47:     assert versions == list(range(1, len(versions) + 1)), f"packaged versions are not contiguous from V001: {versions}"
48:     files = sorted(p.name for p in (REPO / "brandme-data/spanner/migrations").glob("V*.sql"))
49:     for number, name in RESERVED.items():
50:         matching = [f for f in files if f.startswith(f"V{number:03d}_")]
51:         assert matching == [f"V{number:03d}_{name}.sql"], f"V{number:03d} ({name}) must have exactly one file, found {matching}"
```

## brandme-data/spanner/migrations/V016_consumer_design.sql @ babb3604ae2f33018edf0ad45270887d4b01945b

https://github.com/brandmeonline/Brand-Me-Labs/blob/babb3604ae2f33018edf0ad45270887d4b01945b/brandme-data/spanner/migrations/V016_consumer_design.sql#L1

```text
1: -- V016 consumer design alignment (lane: opus-consumer-domains; Ultra plan 02 items 2-7).
2: -- Additive except two CHECK constraints that are replaced to widen what they allow.
3: 
4: -- Now loop: asker-set windows around the five-minute default, and the asker's stated "why".
5: ALTER TABLE Decisions DROP CONSTRAINT ck_dec_duration;
6: ALTER TABLE Decisions ADD CONSTRAINT ck_dec_window CHECK (duration_seconds IN (180, 300, 600, 900));
7: ALTER TABLE Decisions ADD COLUMN why STRING(280);
```

## brandme-data/spanner/migrations/V016_rights_transfer_invites.sql @ a05f2e03e58e55cc2b392b8abc7b19f59659f820

https://github.com/brandmeonline/Brand-Me-Labs/blob/a05f2e03e58e55cc2b392b8abc7b19f59659f820/brandme-data/spanner/migrations/V016_rights_transfer_invites.sql#L1

```text
1: -- V016: transfer invites and fixed offer terms (lane: opus-midnight-rights).
2: --
3: -- The sender's app generates a high-entropy invite and gives it to the recipient
4: -- privately; only its SHA-256 digest is stored, never the invite. The offer terms
5: -- are fixed when the intent is created, so the sender's wallet proves exactly what
6: -- the member reviewed: offerTransfer(entitlementId, nonce, recipientCommitment,
7: -- expiry, termsDigest) (brandme-chain/contracts/src/brandme_rights.compact:309).
8: -- The recipient's wallet computes its commitment locally; no witness is stored.
9: --
10: -- Rows written before V016 have NULL in every new column. The command service
11: -- never binds a recipient to such an intent; it can only expire.
12: ALTER TABLE TransferIntents ADD COLUMN contract_address STRING(128);
13: ALTER TABLE TransferIntents ADD COLUMN invite_digest STRING(64);
14: ALTER TABLE TransferIntents ADD COLUMN offer_nonce STRING(64);
15: ALTER TABLE TransferIntents ADD COLUMN terms_digest STRING(64);
16: ALTER TABLE TransferIntents ADD COLUMN recipient_subject_ref STRING(128);
17: 
18: -- Member-scoped privacy export/erasure for both parties.
19: CREATE INDEX TransferIntentsBySender ON TransferIntents(from_subject_ref);
20: CREATE INDEX TransferIntentsByRecipient ON TransferIntents(recipient_subject_ref);
```

## brandme_core/rights_commands/__main__.py @ a05f2e03e58e55cc2b392b8abc7b19f59659f820

https://github.com/brandmeonline/Brand-Me-Labs/blob/a05f2e03e58e55cc2b392b8abc7b19f59659f820/brandme_core/rights_commands/__main__.py#L25

```text
25:         config = CommandConfig.from_env(os.environ)
26:         # Shared trust-path inventory, in-process. This service has no audited
27:         # entry yet, so strict modes refuse it (exit 3, not caught here).
28:         from brandme_core.boot import guard
29: 
30:         guard("rights_commands")
31:         pool = BurstyPool()
32:         client = spanner.Client(project=config.project)
33:         db = client.instance(config.instance).database(config.database, pool=pool)
34:         verify_schema(db)
35:         if args.check:
36:             print('{"status":"ready","commands":true}', flush=True)
37:             return 0
38:         uvicorn.run(create_app(db, config), host="0.0.0.0", port=config.port, access_log=False,
39:                     proxy_headers=False, server_header=False, limit_concurrency=64, timeout_keep_alive=5)
40:         return 0
```

## brandme-gateway/src/routes/v1/index.ts @ a05f2e03e58e55cc2b392b8abc7b19f59659f820

https://github.com/brandmeonline/Brand-Me-Labs/blob/a05f2e03e58e55cc2b392b8abc7b19f59659f820/brandme-gateway/src/routes/v1/index.ts#L135

```text
135:   router.use('/assets', createAssetsRouter(rights));
136:   router.use('/me', createPrivacyRouter(rights));
137:   router.use('/me', meRouter(cfg, store));
138: 
139:   // Consumer domains (persona, wardrobe, outfits, social, decisions, rewards,
140:   // media, try-on): behind principalMiddleware, forwarded with a signed
141:   // principal assertion (services/domains.ts). Unconfigured → 503 per route.
142:   const domains = deps.domains ?? consumerDomainClient(cfg, doFetch);
143:   for (const mount of [personaRouter, wardrobeRouter, outfitsRouter, socialRouter, decisionsRouter, rewardsRouter, mediaRouter, tryOnRouter]) {
144:     router.use(mount(domains));
145:   }
146: 
147:   router.use((req: Request, res: Response) => problemHandler(problems.notFound(), req, res, () => undefined));
148:   router.use(problemHandler);
149:   return router;
150: }
```

## brandme-gateway/src/routes/v1/transfers.ts @ a05f2e03e58e55cc2b392b8abc7b19f59659f820

https://github.com/brandmeonline/Brand-Me-Labs/blob/a05f2e03e58e55cc2b392b8abc7b19f59659f820/brandme-gateway/src/routes/v1/transfers.ts#L1

```text
1: /**
2:  * Copyright (c) Brand.Me, Inc. All rights reserved.
3:  *
4:  * /v1/transfers/:transferId — a transfer intent's status and the recipient's binding.
5:  * Shipped unmounted: the mount file is foundation's (routes/v1/index.ts). Mount it
6:  * under /api/v1/transfers behind the gateway principal boundary.
7:  *
8:  * Accepting here binds the recipient's commitment, which their wallet computed
9:  * locally for the next epoch. The transfer is final only when the recipient's
10:  * acceptTransfer proof is observed and finalized on chain.
11:  */
12: 
13: import { handle } from '../../middleware/problem';
14: 
15: import { Router } from 'express';
16: import type { Router as IRouter } from 'express';
17: import { z } from 'zod';
18: import { recipientInvite, TRANSFER_REAUTH_SECONDS } from './assets';
19: import { commandHeaders, commandsOf, idempotencyKeyOr400, relay, subjectOr401, type V1Deps } from './chain';
20: 
21: const transferId = z.string().regex(/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
22: 
23: const acceptSchema = z.object({
24:   recipient_invite: recipientInvite,
25:   recipient_commitment: z.string().regex(/^[0-9a-f]{64}$/).refine((c) => c !== '0'.repeat(64)),
26: }).strict();
27: 
28: export function createTransfersRouter(deps: V1Deps): IRouter {
29:   const router: IRouter = Router();
30: 
31:   // Sender or recipient only; anyone else gets 404. The sender's view carries the exact
32:   // offerTransfer arguments once a recipient is bound; witnesses never leave the wallet.
33:   router.get('/:transferId', deps.requireScope('rights:read'), handle(async (req, res) => {
34:     const subject = subjectOr401(deps, req, res);
35:     if (!subject) return;
36:     const id = transferId.safeParse(req.params.transferId);
37:     if (!id.success) { res.status(400).json({ error: 'invalid_transfer_id' }); return; }
38:     relay(res, await commandsOf(deps).get(`/rights/transfers/${id.data}`, commandHeaders(deps, req, subject)));
39:   }));
40: 
41:   router.post('/:transferId/accept', deps.requireScope('rights:transfer'), deps.requireRecentAuth(TRANSFER_REAUTH_SECONDS),
42:     handle(async (req, res) => {
43:       const subject = subjectOr401(deps, req, res);
44:       if (!subject) return;
45:       const id = transferId.safeParse(req.params.transferId);
46:       const body = acceptSchema.safeParse(req.body);
47:       if (!id.success || !body.success) { res.status(400).json({ error: 'invalid_request', details: body.success ? undefined : body.error.issues }); return; }
48:       const idem = idempotencyKeyOr400(req, res);
49:       if (!idem) return;
50:       relay(res, await commandsOf(deps).post(`/rights/transfers/${id.data}/accept`, body.data,
51:         commandHeaders(deps, req, subject, { 'idempotency-key': idem })));
52:     }));
53: 
54:   return router;
55: }
```

## brandme_core/rights_commands/README.md @ a05f2e03e58e55cc2b392b8abc7b19f59659f820

https://github.com/brandmeonline/Brand-Me-Labs/blob/a05f2e03e58e55cc2b392b8abc7b19f59659f820/brandme_core/rights_commands/README.md#L1

```text
1: # Rights command service
2: 
3: A separate, authenticated HTTP process packaged in the core image, beside the
4: read-only [read API](../read_api/README.md). It creates transfer intents, binds
5: a recipient's commitment, evaluates reprint quotes and authorizes
6: ownership-proof challenges. It never holds a wallet, a witness or a prover, and
7: never broadcasts a transaction: the member's wallet proves and submits. Domain
8: rules live in `brandme_core/domains/rights/commands.py`.
9: 
10: | Public gateway path | Backend path | Gateway checks | Service re-checks |
11: | --- | --- | --- | --- |
12: | `POST /api/v1/assets/{assetId}/transfers` | `/rights/assets/{assetId}/transfers` | `rights:transfer`, recent auth (10 min), `Idempotency-Key` | scope, recent auth, key |
13: | `POST /api/v1/transfers/{transferId}/accept` | `/rights/transfers/{transferId}/accept` | `rights:transfer`, recent auth, `Idempotency-Key` | scope, recent auth, key |
14: | `GET /api/v1/transfers/{transferId}` | `/rights/transfers/{transferId}` | `rights:read` | scope |
15: | `POST /api/v1/assets/{assetId}/reprint-quotes` | `/rights/assets/{assetId}/reprint-quotes` | `rights:reprint` | scope |
16: | `POST /api/v1/ownership/challenges` | `/rights/challenges` | `rights:read` | scope |
17: 
18: The two `/transfers` routes are in `brandme-gateway/src/routes/v1/transfers.ts`
19: and are **not mounted**: the mount file is foundation's (`routes/v1/index.ts`).
20: Cookie sessions also pass the gateway's CSRF check before any of these calls.
21: 
22: ## Transfer flow
23: 
24: 1. The sender's app generates a high-entropy invite (43–128 base64url
25:    characters) and gives it to the recipient privately. The intent stores only
```

## brandme_core/rights_commands/README.md @ a05f2e03e58e55cc2b392b8abc7b19f59659f820

https://github.com/brandmeonline/Brand-Me-Labs/blob/a05f2e03e58e55cc2b392b8abc7b19f59659f820/brandme_core/rights_commands/README.md#L48

```text
48: 
49: ## Deploy explicitly
50: 
51: Apply and verify the repository migrations through V016 before startup; the
52: service checks the migration ledger and the columns it uses, and never applies
53: migrations. Configure through the deployment and secret manager:
54: 
55: ```text
56: BRANDME_MODE=development
57: ENVIRONMENT=development
58: SPANNER_PROJECT_ID=<project>
59: SPANNER_INSTANCE_ID=<instance>
60: SPANNER_DATABASE_ID=<database reserved for this environment>
61: RIGHTS_COMMAND_NETWORK=preprod
62: RIGHTS_COMMAND_CONTRACT_ADDRESS=<64 lowercase hex characters>
63: RIGHTS_COMMAND_SERVICE_TOKEN=<independent random service credential, 32–256 characters>
64: PORT=8000
65: ```
66: 
67: The credential differs from every other rights-lane service credential
68: (`RIGHTS_SERVICE_TOKEN`, `PRIVACY_SERVICE_TOKEN`, `PRIVACY_EXPORT_SERVICE_TOKEN`,
69: `CHAIN_SERVICE_TOKEN`); the service refuses an equal value. Configure the
70: gateway with `RIGHTS_COMMAND_SERVICE_URL` and the same credential. The process
71: writes only `TransferIntents`, `IdempotencyRecords` and `OutboxEvents`; it reads
72: the rights projections, the privacy ledger (freezes, deletion jobs, tombstones,
73: restore runs) and `SchemaMigrations`. Keep the listener private behind
74: authenticated ingress and TLS. Access logging is off; database errors are never relayed or logged.
75: 
76: ```sh
77: python -m brandme_core.rights_commands --check
78: python -m brandme_core.rights_commands
79: ```
80: 
81: **Strict modes refuse this process.** It has no audited entry in the shared
82: trust-path inventory (`brandme_core/config.py`), which is foundation's mode-guard
83: policy; `brandme_core.boot.guard("rights_commands")` therefore refuses sandbox
84: and production until that entry exists. There is no Mainnet mode.
85: 
86: ## Verification
87: 
88: `tests/test_rights_commands.py` runs the service against the Spanner emulator
89: with the real migration chain. `brandme-gateway/src/routes/v1/commands-backend.test.ts`
90: runs signed OIDC through the mounted gateway into the real Python process.
91: `brandme-gateway/src/routes/v1/v1-routes.test.ts` covers the route checks,
92: including the unmounted `/transfers` router.
```

## brandme_core/domains/persona/app.py @ babb3604ae2f33018edf0ad45270887d4b01945b

https://github.com/brandmeonline/Brand-Me-Labs/blob/babb3604ae2f33018edf0ad45270887d4b01945b/brandme_core/domains/persona/app.py#L45

```text
45: 
46: 
47: def create_app(database: Any, *, resolve_principal: Callable[[Any], Any], media_store: Any = None, providers: Any = None,
48:                catalog: Any = None) -> FastAPI:
49:     """``catalog`` is the houses port for Flow and standings; default ``CatalogHouses``."""
50:     load_domains()
51:     from brandme_core.domains.media.api import create_media_router
52:     from brandme_core.domains.media.providers import ProviderRegistry
53:     from brandme_core.domains.media.service import MediaService
54:     from brandme_core.domains.rewards.api import create_rewards_router
55:     from brandme_core.domains.rewards.benefits import BenefitService
56:     from brandme_core.domains.rewards.credits import CreditService
57:     from brandme_core.domains.rewards.service import RewardsService
58:     from brandme_core.domains.rewards.standing import StandingService
59:     from brandme_core.domains.rewards.surveys import SurveyService
60:     from brandme_core.domains.social.api import create_flow_router, create_rooms_router, create_social_router
61:     from brandme_core.domains.social.decisions import DecisionService
62:     from brandme_core.domains.social.flow import FlowService
63:     from brandme_core.domains.social.houses import CatalogHouses, HouseService, catalog_piece_exists
64:     from brandme_core.domains.social.notifications import NotificationService
65:     from brandme_core.domains.social.relationships import RelationshipService, friendship_proposal_policy
66:     from brandme_core.domains.social.reports import ReportService
67:     from brandme_core.domains.social.rooms import RoomService
68:     from brandme_core.domains.social.shares import ShareService
69:     from brandme_core.domains.wardrobe.api import create_wardrobe_router
70:     from brandme_core.domains.wardrobe.outfits import OutfitService
71:     from brandme_core.domains.wardrobe.service import WardrobeService
72: 
73:     from brandme_core.domains.wardrobe.visibility import ClosetVisibilityService
74: 
75:     from .api import create_card_router, create_persona_router
76:     from .card import PersonaCardService
77:     from .onboarding import GuestMigrationService
78:     from .service import PersonaService
79: 
80:     app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
81:     persona = PersonaService(database)
82:     app.include_router(create_persona_router(persona, GuestMigrationService(database, persona), resolve_principal))
83:     houses = catalog if catalog is not None else CatalogHouses()
84:     app.include_router(create_wardrobe_router(WardrobeService(database), OutfitService(database, proposal_policy=friendship_proposal_policy),
85:                                               resolve_principal, ClosetVisibilityService(database, catalog=houses)))
86:     app.include_router(create_card_router(PersonaCardService(database, persona=persona, catalog=houses), resolve_principal))
87:     app.include_router(create_social_router(RelationshipService(database), DecisionService(database, catalog_check=catalog_piece_exists),
88:                                             ShareService(database),
89:                                             NotificationService(database), resolve_principal, ReportService(database)))
90:     app.include_router(create_rooms_router(RoomService(database, catalog_check=catalog_piece_exists), resolve_principal))
91:     app.include_router(create_flow_router(FlowService(database, catalog=houses, persona=persona), HouseService(database, catalog=houses),
92:                                           resolve_principal))
93:     app.include_router(create_rewards_router(RewardsService(database), BenefitService(database), resolve_principal,
94:                                              StandingService(database, catalog=houses), SurveyService(database), CreditService(database)))
95:     if media_store is not None:
```

## brandme_core/domains/rewards/credits.py @ babb3604ae2f33018edf0ad45270887d4b01945b

https://github.com/brandmeonline/Brand-Me-Labs/blob/babb3604ae2f33018edf0ad45270887d4b01945b/brandme_core/domains/rewards/credits.py#L174

```text
174:         return  # the caller deletes the credit in this transaction
175:     txn.update("PurchaseCredits", columns=("member_id", "credit_id", "state", "applied_ref", "settled_at", "version"),
176:                values=[(member, cid, state, applied_ref, COMMIT_TIMESTAMP, c["version"] + 1)])
177: 
178: 
179: def apply_credit(txn, *, member_id: str, credit_id: Any, order_ref: Any, currency: str, now: Optional[datetime] = None) -> Dict[str, Any]:
180:     """For the in-app checkout (commerce lane), inside its order transaction:
181:     spend one available, unexpired credit of this member in its own currency.
182:     Not wired yet; the commerce lane calls it when it adopts credits."""
183:     credit_id = require_uuid(credit_id, name="credit_id")
184:     order_ref = require_text(order_ref, name="order_ref", max_len=120)
185:     c = _credit(txn, member_id, credit_id)
186:     at = now or server_now(txn)
187:     if c is None:
188:         raise NotFound("credit not found")
189:     guard_write(txn, member_id, "rewards.credits")
190:     if c["state"] != "available" or c["expires_at"] <= at:
191:         raise DetailedInvalidTransition("this credit is no longer available", code="credit_unavailable", extra={"state": c["state"]})
192:     if c["currency"] != currency:
193:         raise DetailedInvalidTransition("this credit is in another currency", code="credit_currency_mismatch", extra={"currency": c["currency"]})
194:     _settle(txn, c, "applied", order_ref, "service:commerce.checkout")
195:     return {"credit_id": credit_id, "amount": {"minor": c["amount_minor"], "currency": c["currency"]}}
196: 
197: 
198: def export_credits(snap, member_id: str) -> List[Dict[str, Any]]:
199:     return [_dto(dict(zip(COLS, r))) for r in query(snap, f"SELECT {', '.join(COLS)} FROM PurchaseCredits WHERE member_id=@m ORDER BY created_at",
200:                                                     {"m": member_id}, {"m": STR})]
201: 
202: 
```

## brandme-frontend/features/social/horizons.tsx @ 0ff12fbdbce2a8b4ea1391a02ef3ea821ae6a420

https://github.com/brandmeonline/Brand-Me-Labs/blob/0ff12fbdbce2a8b4ea1391a02ef3ea821ae6a420/brandme-frontend/features/social/horizons.tsx#L1

```text
1: import Link from 'next/link'
2: import type { ReactNode } from 'react'
3: import { PageHeading } from '../../components/shell/page-heading'
4: 
5: const horizons = [
6:   { id: 'now', label: 'Now' },
7:   { id: 'flow', label: 'Flow' },
8:   { id: 'editorial', label: 'Editorial' },
9: ] as const
10: export type Horizon = typeof horizons[number]['id']
11: 
12: export function SocialHorizon({ active, children }: { active: Horizon; children?: ReactNode }) {
13:   return <>
14:     <PageHeading eyebrow="Social" title="Good taste, shared."
15:       description="A moment to help a friend. A place for the houses and ideas you care about." />
16:     <nav className="bm-horizon-nav" aria-label="Social horizons">
17:       {horizons.map(horizon => <Link key={horizon.id} href={`/social/${horizon.id}`}
18:         aria-current={active === horizon.id ? 'page' : undefined}>{horizon.label}</Link>)}
19:     </nav>
20:     <div className="bm-social-stream-container"><div className="bm-social-streams">
21:       <section aria-labelledby={`horizon-${active}`} className="bm-flow-stack">
22:         <h2 id={`horizon-${active}`} className="bm-editorial-title">{horizons.find(horizon => horizon.id === active)!.label}</h2>
23:         {children ?? <div className="bm-horizon-unavailable">
24:           <p className="bm-eyebrow">Not available yet</p>
25:           <h3 className="bm-section-title">{active === 'flow' ? 'Your houses, in one place.' : 'A considered point of view.'}</h3>
26:           <p>{active === 'flow'
27:             ? 'Flow is not available in this preview. Updates from your houses and your circle are not connected yet.'
28:             : 'Editorial is not available in this preview. Curated stories and runway imagery are not connected yet.'}</p>
29:           <Link className="bm-text-link" href="/social/now">See decisions in Now</Link>
30:         </div>}
31:       </section>
32:       <aside className="bm-brand-stream" aria-labelledby="brand-stream-heading">
33:         <p className="bm-eyebrow">Alongside your circle</p>
34:         <h2 id="brand-stream-heading" className="bm-section-title">Brands &amp; designers</h2>
35:         <p>This separate stream is not available in the preview yet.</p>
36:         <Link className="bm-text-link" href="/discover">Explore Shops</Link>
37:       </aside>
38:     </div></div>
39:   </>
40: }
```

## docs/build/orchestration/pipeline-state.md @ ed19dc151d103b108cf972e6d37971c55d5dcf60

https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/docs/build/orchestration/pipeline-state.md#L8

```text
8: Refreshed 2026-10-30 ~11:15 EDT: main c902317 (#60 merged), #66 Stage 21
9: undrafted + green but held, #63 Codex contact.
10: 
11: ## Loop status
12: - Design: APPROVED by founder 2026-10-29. Check-in rule (option 3): lanes keep
13:   building on work independent of open questions; recommended defaults are NEVER
14:   treated as rulings. Open questions queue for the founder checkpoint.
15: - Main HEAD: c902317 (foundation PR #62 merged 2026-10-30 morning EDT,
16:   D-007 approved by the founder 2026-10-30; spatial PR #60 merged by the
17:   founder 2026-10-30 10:18 EDT).
18: - Main health: FULLY GREEN on c902317 (verified 2026-10-30 ~11:14 EDT:
19:   13 success + 1 skipped on the merge push run, nothing failing). The Test
20:   Frontend advisory failure cleared after the #62 merge; the re-run vs
21:   remediation decision is closed by events. Mechanism not established (do not
22:   attribute to #62's qs override). Flagged advisory for the record:
```

## docs/build/orchestration/pipeline-state.md @ ed19dc151d103b108cf972e6d37971c55d5dcf60

https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/docs/build/orchestration/pipeline-state.md#L61

```text
61:   privacy lane) approved by the founder 2026-10-30. Q11 trimmed; #61 flags folded
62:   in; Q8 round trip 54 contracts. Next: ultra-plan-02 foundation draft (following
63:   queue). wip/fb2 token fold deferred to round 5 remains open.
64:   Last ping: round-4 status (pre-merge). Last pong: #62 merge 2026-10-30.
65: - **Consumer-domains (Opus) — PR #66, head e40ea7cd, Stage 21, UNDRAFTED.**
66:   Session proved alive overnight and through the morning. Item 9 (lane outbox
67:   worker deletion) UNBLOCKED by the #62 merge (Q8 import now on main); trigger
68:   comment posted 2026-10-30 morning. Checks on e40ea7cd green at last check
69:   (21 success + 1 skipped), mergeable clean — but HELD, not merged, on two
70:   items: (1) Codex review still running on the head (triggered by
71:   draft-marked-ready); (2) foundation approval pending for two deviations
72:   recorded in the lane status file (c488c25 foundation-test-count edit;
73:   catalog pins consumer-domains 36 → 37 / total 54 → 55), both marked
74:   "Approval: Foundation, at review". Merge follows review completion +
75:   foundation approval (or founder decision).
76:   Last ping: Stage 21 status on #66; undrafted 2026-10-30. Last pong:
77:   hold notice 2026-10-30 (review + foundation approval pending).
78: - **Commerce-agents (Opus) — no open PR.** Round-03 oneshot plan is on main via
79:   #67; needs a fresh branch to start. Money-path proof still gated on the two
80:   founder keys (STRIPE_TEST_SECRET_KEY, BRANDME_DEV_ANTHROPIC_API_KEY — names-only
81:   check 2026-10-30 morning: only GCP_SA_KEY present).
82:   Last ping: none (no open PR). Last pong: round-03 plan on main via #67.
83: - **Midnight-rights (Opus) — no open PR.** Round-03 ultra plan is on main via #67;
84:   needs a fresh branch to start.
85:   Last ping: none (no open PR). Last pong: round-03 plan on main via #67.
86: - **Consumer-ui (Astra) — PR #63, draft, head 0ff12fb, visual-baseline gate.**
87:   Codex contact confirmed 2026-10-30: chatgpt-codex-connector bot re-synced the
88:   branch with main 97d54477 via merge commit 75f0ff0 and corrected the lane's
89:   claimed re-sync (docs-only). That reply counts as contact under ping-pong,
90:   not stage completion. Checks on 0ff12fb: 15 success + 1 skipped + shell
91:   failing; visual-baseline gate still open. Note: main has since advanced to
92:   c902317, so a further re-sync is needed before merge.
93:   Last ping: Codex re-sync reply 2026-10-30 (contact, not completion).
94:   Last pong: second kick-off trigger 2026-10-30 (comment 6524069655).
95: - **Spatial-ar (Astra) — MERGED.** PR #60 merged by the founder 2026-10-30
96:   10:18 EDT (merge commit c902317, head 3eddd28; 20 success + GKE skipped
97:   on the merged head, including Spatial browser and local pose passing, Codex
98:   zero findings, mergeable clean). Caveat: the merge lands code, not device
99:   proof — physical measurement session, native-device session, and
100:   live-provider run still NOT_RUN; pose evidence single-fixture.
101:   Last ping: merge (receipt obligation closed by the merge). Last pong:
102:   second kick-off trigger 2026-10-30 (comment 6524070094).
103: 
```

## .github/workflows/consumer-ui.yml @ ed19dc151d103b108cf972e6d37971c55d5dcf60

https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/consumer-ui.yml#L1

```text
1: name: Consumer UI
2: 
3: on:
4:   pull_request:
5:     paths: ['brandme-frontend/**', 'brandme-console/**', 'packages/**', 'pnpm-lock.yaml', '.github/workflows/consumer-ui.yml']
6:   push:
7:     branches: ['bench/astra-consumer-ui-20261005']
8:   workflow_dispatch:
```

## .github/workflows/spatial-validation.yml @ ed19dc151d103b108cf972e6d37971c55d5dcf60

https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/spatial-validation.yml#L1

```text
1: name: Spatial validation
2: 
3: on:
4:   push:
5:     branches: ['bench/astra-spatial-ar-20261005']
6:   pull_request:
7:     branches: [main]
8:     paths:
```

## pnpm-workspace.yaml @ ed19dc151d103b108cf972e6d37971c55d5dcf60

https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/pnpm-workspace.yaml#L1

```text
1: # Owned by the opus-foundation lane. Toolchain pins: docs/build/compatibility-lock.md
2: # Registration, lockfile and conflict rules: docs/build/workspace-governance.md
3: # (enforced by scripts/check-workspace.mjs; every tracked package.json must match a
4: # glob below or be a STANDALONE entry in that script).
5: packages:
6:   - 'brandme-gateway'
7:   - 'brandme-chain'
8:   - 'brandme-console'
9:   - 'brandme-frontend'
10:   - 'packages/*'
11:   - 'scripts/assets'
12: 
13: # pnpm 10 blocks dependency lifecycle scripts unless allowlisted.
```

## .github/workflows/module-regression.yml @ ed19dc151d103b108cf972e6d37971c55d5dcf60

https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/module-regression.yml#L30

```text
30: 
31:       - name: Setup Node
32:         uses: actions/setup-node@v4
33:         with:
34:           node-version-file: .nvmrc
35: 
36:       # No `version:` here — package.json's `packageManager` field is the
37:       # single source of truth. action-setup@v4 errors out if both are set.
38:       - name: Setup pnpm
39:         uses: pnpm/action-setup@v4
40: 
41:       # Before the install: an unregistered package fails here with
42:       # E_UNREGISTERED instead of a later "tsc: not found" from a package that
43:       # `pnpm install --frozen-lockfile` silently skipped (PR #55). Offline
44:       # checks only; the next step is pnpm's own frozen-lockfile check.
45:       # Error codes and fixes: docs/build/workspace-governance.md
46:       - name: Workspace guard
47:         run: node scripts/check-workspace.mjs
48: 
49:       - name: Install JS dependencies
```

## tests/contracts/property.test.ts @ ed19dc151d103b108cf972e6d37971c55d5dcf60

https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/tests/contracts/property.test.ts#L218

```text
218:  * Deterministic coverage preamble for the vacuity guard in the test below.
219:  *
220:  * The guard requires both a success and a rejection for each stateful
221:  * circuit, but the random command stream only *usually* produces them: a
222:  * 10-seed probe (150 sequences each) showed consumeReprintAllowance ok
223:  * counts as low as 4 and acceptTransfer as low as 3 per batch, and CI hit
224:  * the unlucky seed on 2026-10-10 where no random consumeReprintAllowance
225:  * ever succeeded ("consumeReprintAllowance never succeeded" on main
226:  * 99fc2fa2, Module Regression job 114233947986; GitHub issue #38).
227:  *
228:  * This drives exactly one success and one rejection per guarded circuit
229:  * through sim.attempt — the same path the random runs use — and folds them
230:  * into the shared tally via recordCalls, so the guard below is
231:  * deterministic. The property test itself is unchanged: it still explores
232:  * random interleavings and checks the ch.04 §4 invariants after every step.
233:  */
234: function seedCircuitCoverage() {
235:   const sim = new RightsSimulator();
236:   const issuer = new Actor('issuer');
237:   const holder = new Actor('holder');
238:   const recipient = new Actor('recipient');
239:   const mfr = new Actor('mfr');
240:   const iid = registerIssuer(sim, issuer);
241:   const mid = registerManufacturer(sim, issuer, iid, mfr);
242:   const issuanceId = random32();
243:   const eid = derive.entitlementId(iid, issuanceId);
244:   sim.call(issuer, 'issueEntitlement', iid, issuanceId, random32(), random32(), true, true,
245:     prepareHolder(sim, holder, eid, 1n));
246: 
247:   // grantReprintAllowance: success, then zero-quota rejection.
248:   const aid = sim.call<Uint8Array>(issuer, 'grantReprintAllowance', iid, random32(), eid,
249:     random32(), mid, 2n, FAR_FUTURE, random32());
250:   expect(sim.attempt(issuer, 'grantReprintAllowance', iid, random32(), eid, random32(), mid,
251:     0n, FAR_FUTURE, random32()).ok, 'preamble: zero-quota grant must be rejected').toBe(false);
252: 
253:   // proveControl: success, then challenge-replay rejection.
254:   const challenge = random32();
255:   const audience = random32();
256:   expect(sim.attempt(holder, 'proveControl', eid, challenge, audience).ok,
257:     'preamble: proveControl must succeed').toBe(true);
258:   expect(sim.attempt(holder, 'proveControl', eid, challenge, audience).ok,
259:     'preamble: challenge replay must be rejected').toBe(false);
260: 
261:   // consumeReprintAllowance: success, then duplicate-job rejection.
262:   const job = random32();
263:   expect(sim.attempt(holder, 'consumeReprintAllowance', aid, job, 1n, random32()).ok,
264:     'preamble: consumeReprintAllowance must succeed').toBe(true);
265:   expect(sim.attempt(holder, 'consumeReprintAllowance', aid, job, 1n, random32()).ok,
266:     'preamble: duplicate job consumption must be rejected').toBe(false);
267: 
268:   // offerTransfer: non-controller rejection, then success.
269:   expect(sim.attempt(recipient, 'offerTransfer', eid, random32(), random32(),
270:     BigInt(sim.now + 600), random32()).ok,
```

## Preview handoff correction @ 0ff12fbdbce2a8b4ea1391a02ef3ea821ae6a420  ```text
636: 
637: ### Design-preview synchronization with the approved parent and contract
638: 
639: The local PR #63 branch initially incorporated approved parent `cccfe7b4b4ce9f44fb9bebd9a7cb2c47b4fe97b8` and contract publication `4ba1fae8a846a2a34104564ce35010fb4be4ad2c`. The Stage 15 approval, Stage 16 contract receipt and all preview evidence are preserved. PR #56 has since merged; preview publication and retargeting remain deferred until the contract PR #65 has actually merged.
640: 
641: On combined snapshot `7f7d4e7`, `test:ui` passed **33/33 tests with zero failures or skips**: 27 preview cases, four console compatibility cases and two adapter parity cases. Validation used Node 24.21.0 / pnpm 10.34.6 in a new detached worktree with new junctions to the root's fresh frozen dependency installation; no existing junction was removed or replaced. The shared test compiler now resolves each application's `@/` aliases within that application, preserving the separate React runtimes. The existing React 18/Radix static-render layout-effect diagnostics remain distinct from browser hydration evidence.
642: 
643: Consumer application sources and reviewed baselines are unchanged from preview head `9d1e29f`; domain and revision-fixture changes match the approved parent exactly. The founder's approval covers that domain correction only. Human visual-baseline approval, device and screen-reader sessions remain outstanding; this preparation adds no production feature or approval.
644: 
645: Actual publication parent `06d8fc13f3133fea5108164266a6fee59b88db1f` (PR #65) is now incorporated locally, preserving its main-merge ancestry and final Stage 16 CI receipts. Compared with preview head `50b0b72`, this integration changes only status documentation; application and test sources are identical, so the 33-test suite is not repeated. No baseline or device approval is implied, and the preview remains unpublished pending the actual #65 merge.
646: 
647: ### Both prerequisites merged; preview review remains pending
648: 
649: PR #56 merged as `b9f483be139f1e0a3c324cdf5f30bbb3c5bdc22b`, followed by contract PR #65 as `77280249df4e91d93b4d814b140bd5e38bba4735`. Exact contract head `06d8fc13f3133fea5108164266a6fee59b88db1f` passed [full CI run 40155977531](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/40155977531): 1,742 Python tests, all 256 consumer-domain tests and all five container build/runtime checks. [Consumer UI run 40155977548](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/40155977548) passed 22 UI/compatibility/adapter cases, 13 gateway/security cases, all 74 unchanged reviewed pixel comparisons and the real live-domain journey.
650: 
651: The local preview incorporates actual main `77280249`. Application and test sources remain identical to `50b0b72`, whose combined 33 UI tests were already validated; this integration changes status documentation only, so no tests or captures are repeated. Domain sources and reviewed baselines are unchanged. The preview still requires human review of its 58 rejected comparisons (47 pixel and 11 dimension differences). Flow, Editorial, brand feeds, membership/public-profile and entitlement features still await their owning backend contracts. Device and screen-reader sessions remain `not_run`; neither prerequisite merge approves the new preview visuals or supplies those missing capabilities.
652: 
653: ## Stage 17 — Round-03 handoff published to the repository (2026-10-30)
654: 
655: **Status:** The restart report is recorded in the consumer lane's repository
656: status file, on `codex/consumer-design-preview` through [draft PR #63](https://github.com/brandmeonline/Brand-Me-Labs/pull/63).
657: The round-03 implementation and release gates remain incomplete. The founder's
658: max-plan / full-effort instruction remains the requested execution posture.
659: 
660: ### Verified remote state and publication correction
661: 
662: - The active plan is [Ultra plan 03](https://github.com/brandmeonline/Brand-Me-Labs/blob/main/docs/build/orchestration/ultra-plan-03-astra-consumer-ui.md),
663:   already on main. The pending pipeline-state seed is not a prerequisite for this lane.
664: - Main was verified at `97d54477f7667dade1a4fd7220c0b2694cffb604` (#62 merged).
665:   Before this status publication, PR #63's published head was
666:   `2f89dce5d171138085d994456722cfcb1868f637`, targeting main.
667: - The [previous Codex restart report](https://github.com/brandmeonline/Brand-Me-Labs/pull/63#issuecomment-6524186371)
668:   reported a conflict-free main merge `75f0ff0` and status commit `5709e00`.
669:   GitHub could not resolve either commit during this publication. The published status
670:   file ended before the reported Stage 17, so the report's old line links did not
671:   contain that update. The summary was posted, but the reported commits were not
672:   available in the repository.
673: - This append recovers the handoff as repository content. It does not reconstruct
674:   those unavailable commits or establish that main was merged into the published
675:   preview branch. That synchronization and verification remain outstanding.
676: - Only this lane status file changes. No application source, dependency, reviewed
677:   baseline, backend/domain source or spatial asset is changed by this publication.
678: 
679: ### Earlier execution report — carried forward, not rerun here
680: 
681: These results come from the previous execution report linked above and supplied by
682: the founder. They are not fresh checks of this documentation commit:
683: 
684: | Command | Earlier reported result |
685: | --- | --- |
686: | `pnpm --dir brandme-frontend test:ui` | 33 passed |
687: | `pnpm --dir brandme-frontend test:gateway` | 13 passed |
688: | `pnpm --dir brandme-frontend build` | Production build passed; 30 static pages generated |
689: | `pnpm --dir brandme-console build` | Production build passed |
690: | `git diff --check` | Passed |
691: | `pnpm --dir brandme-frontend test:browser` | Could not launch: Playwright Chromium 1208 was unavailable |
692: | `pnpm --dir brandme-frontend exec playwright install chromium` | CDN returned HTTP 403 on all five reported download attempts |
693: 
694: The earlier run therefore produced no fresh screenshot or pixel-comparison result.
695: No replacement baseline or human visual approval is inferred from the build and
696: component passes. The prior preview's 58 rejected comparisons remain subject to
697: human review; those historical failures are separate from the later browser-download
698: blocker.
699: 
700: ### Design reconciliation and remaining gates
701: 
702: The previous ChatGPT-design artifact remains an explicit input gap in the handoff;
703: no screen-by-screen ADOPT / ADAPT / DISCARD reconciliation is claimed. Continue from
704: the locked October 23 decisions, spec 02 screen contracts and merged UI, in that
705: precedence order, until the designs are supplied.
706: 
707: Next execution work is to synchronize the published preview with current main,
708: run the required checks on the resulting head, and resolve the visual-baseline gate
709: with human review. Rooms and Now/Flow must be verified against live dev gateway data;
710: Flow/Editorial, invite/waitlist, public persona and other server-owned integrations
711: must be assessed against current owner contracts rather than promoted from preview
712: markup. Real-device and screen-reader sessions remain unverified in this handoff.
713: The round-03 check-in trigger and external-release gates are not satisfied by this
714: documentation publication.
715: 
716: **Limits:** The earlier execution reported no rate-limit refresh time. No rate-limit
717: interruption was observed while publishing this handoff; no future refresh time is
718: asserted.
719: 
720: **Credential manifest:** No credentials were created or copied. Publication uses the
721: existing connected GitHub access.
```

## Consumer credit call-site search

Command: git grep -n apply_credit babb3604ae2f33018edf0ad45270887d4b01945b -- :!docs :!pnpm-lock.yaml

```text
babb3604ae2f33018edf0ad45270887d4b01945b:brandme_core/domains/rewards/credits.py:16:  (``apply_credit``, for the commerce lane to call inside its order
babb3604ae2f33018edf0ad45270887d4b01945b:brandme_core/domains/rewards/credits.py:179:def apply_credit(txn, *, member_id: str, credit_id: Any, order_ref: Any, currency: str, now: Optional[datetime] = None) -> Dict[str, Any]:
babb3604ae2f33018edf0ad45270887d4b01945b:tests/test_persona_lane_mydata.py:48:from brandme_core.domains.rewards.credits import CreditService, apply_credit  # noqa: E402
babb3604ae2f33018edf0ad45270887d4b01945b:tests/test_persona_lane_mydata.py:292:    frozen(lambda: run_txn(db, lambda t: apply_credit(t, member_id=m, credit_id=credit_id, order_ref="order-dev-1", currency="USD")))
babb3604ae2f33018edf0ad45270887d4b01945b:tests/test_rewards_surveys_credits.py:25:from brandme_core.domains.rewards.credits import CreditService, apply_credit
babb3604ae2f33018edf0ad45270887d4b01945b:tests/test_rewards_surveys_credits.py:155:        run_txn(db, lambda t: apply_credit(t, member_id=me.member_id, credit_id=c["credit_id"], order_ref="order-1", currency="EUR"))
babb3604ae2f33018edf0ad45270887d4b01945b:tests/test_rewards_surveys_credits.py:159:        run_txn(db, lambda t: apply_credit(t, member_id=stranger, credit_id=c["credit_id"], order_ref="order-1", currency="USD"))
babb3604ae2f33018edf0ad45270887d4b01945b:tests/test_rewards_surveys_credits.py:160:    used = run_txn(db, lambda t: apply_credit(t, member_id=me.member_id, credit_id=c["credit_id"], order_ref="order-1", currency="USD"))
babb3604ae2f33018edf0ad45270887d4b01945b:tests/test_rewards_surveys_credits.py:163:        run_txn(db, lambda t: apply_credit(t, member_id=me.member_id, credit_id=c["credit_id"], order_ref="order-2", currency="USD"))
babb3604ae2f33018edf0ad45270887d4b01945b:tests/test_rewards_surveys_credits.py:234:    assert run_txn(db, lambda t: apply_credit(t, member_id=me.member_id, credit_id=spend, order_ref="order-1", currency="USD"))["credit_id"] == spend
```

## Rights router mount and trust-path search

git grep -n createTransfersRouter a05f2e03e58e55cc2b392b8abc7b19f59659f820 -- brandme-gateway/src/routes/v1/index.ts: no matches, exit 1.

git grep -n rights_commands a05f2e03e58e55cc2b392b8abc7b19f59659f820 -- brandme_core/config.py: no matches, exit 1.

