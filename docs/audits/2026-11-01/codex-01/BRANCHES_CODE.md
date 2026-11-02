# Branches, preserved value, and cleanup proposal

[Audit home](README.md) · [Architecture](PRODUCT_ARCHITECTURE.md) · [Roadmap](ROADMAP.md) · [Machine-readable branches](evidence/branches.json)

The remote product is substantially newer than the user's clean local checkout. Remote `main` is **`ed19dc151d103b108cf972e6d37971c55d5dcf60`**; original local `main` remains **`0f5f58a9eecaca46b367c9bd96f89654343fa5fb`**, 370 commits behind, with 1,128 changed paths in the endpoint tree comparison. They must not share a single capability verdict. The audit clone is detached at the remote baseline; the original checkout and existing refs remain unchanged. A final scope refresh fetched only the newly advertised BR-036 remote-tracking ref into the isolated clone.

Three current branches contain valuable unmerged product work: **PR #66 consumer domains, PR #63 consumer UI preview, and PR #70 rights commands/privacy**. Their combined trees are not a working product: #66 and #70 independently claim migration **V016**, #63 has not incorporated recent main, and specific backend/UI connections remain absent. Recover these lanes in a controlled integration order instead of rewriting their implementations.

## Coverage and evidence limits

- Inventoried the initial **34 remote branch heads**, then the final recheck's one new head: **35 remote heads total**, plus preserved local main as **BR-035**. The new head is **BR-036**; existing IDs were retained. `origin/HEAD` is an alias, not another branch. The initial source snapshot had three remote heads; all remain. No initial remote tip moved or disappeared in the [final ref delta](evidence/history-final-ref-delta.json); main is unchanged. No tag refs were returned locally.
- Enumerated an initial 69 PRs and final new #71: **70 PRs total: 62 merged, 3 closed unmerged (#2, #37, #55), and 5 open (#29, #63, #66, #70, #71)**. Listings were paginated; initial evidence remains preserved separately. PR numbers need not be contiguous. All open PRs target main; there is no open PR whose base is another open lane, but there are semantic integration dependencies.
- Reviewed ancestry, merge bases, ahead/behind, per-commit patch equivalence, original merge trees, aggregate squash patches, added-file retention, changed-file inventories, current workflow/branch references, source/audit worktrees, GitHub protection/ruleset/environment/deployment/release metadata, and branch-tip CI/review metadata. Compared current replacement entry points and sampled consequential branch source. **This is not an exhaustive line-by-line review or runtime verification of every branch-specific implementation or test.**
- Executed only read-only Git/GitHub/static inspection and audit-authored inventory scripts. No repository application, test, install, hook, migration, or live provider action was executed by this branch workstream. Prior repository reports and CI metadata are evidence with their own revision/scope, not tests rerun by this audit.
- The repository/includes-parent ruleset listing returned empty; all 35 branches report `protected:false`. The initial 34 per-branch protection calls explicitly returned `Branch not protected` (404); BR-036's final branch metadata separately reports `protected:false`. Security impact is addressed as **F-SEC-003** in [security and reliability](SECURITY_RELIABILITY.md). GitHub releases, environments, and deployments returned empty successful listings. These observations do not prove absence of externally managed deployments, monitoring, or branch consumers.
- Source and audit worktree lists show only source local main and the detached audit checkout. Independent clones, unregistered worktrees, external automations, and hosted branch bindings were not exhaustively observable. Every retirement proposal therefore requires fresh external-consumer confirmation and tip revalidation.

Primary evidence: [pre-fetch baseline](evidence/local-baseline-before-fetch.txt), [raw initial Git comparisons](evidence/history-git-branches-raw.json), [final advertised heads](evidence/history-final-remote-heads.txt), [semantic/squash comparisons](evidence/history-semantic-comparisons.json), [all PRs including final delta](evidence/history-github-prs-final.json), [selected PR review/merge metadata](evidence/history-github-pr-details.json), [CI checks including new branch](evidence/history-github-branch-ci-final.json), [protections](evidence/history-github-protection.json), [API outcomes](evidence/history-github-api-log.json), [branch consumers](evidence/history-branch-consumers.txt), and [numbered immutable source excerpts](evidence/history-source-excerpts.md).

## Every available branch

Decisions: **KEEP** preserves active/canonical routing; **INTEGRATE** moves valuable unique work to named main after acceptance; **PRESERVE THEN RETIRE** requires selecting/archiving identified value before a later retirement decision; **DELETION CANDIDATE** means no remaining unique implementation or observed active branch binding was found within this audit's visibility; **UNKNOWN** means evidence does not justify retirement. None authorizes deletion. Exact purpose, activity timestamp, comparison target/merge base, PR/review/CI state, changed areas, unique commits, consumers, dependencies, preservation requirements, and confidence are in [branches.json](evidence/branches.json).

| ID | Exact remote branch | Tip SHA | Ahead / behind main | Decision |
|---|---|---|---:|---|
| BR-001 | `bench/astra-consumer-ui-20261005` | `cccfe7b4b4ce9f44fb9bebd9a7cb2c47b4fe97b8` | 0 / 90 | KEEP |
| BR-002 | `bench/astra-spatial-ar-20261005` | `1413178b7f74ecaf20589d67c4ba4dcdedbb69c2` | 0 / 5 | KEEP |
| BR-003 | `bench/opus-commerce-agents-20261005` | `7c61afd7c98a66836ba91d715bc4c6c913807003` | 0 / 344 | KEEP |
| BR-004 | `bench/opus-consumer-domains-20261005` | `d839267fc1f74b5e778e83f2930953e1a5400712` | 0 / 365 | KEEP |
| BR-005 | `bench/opus-foundation-20261005` | `67327e45ed816bd76bc20ed1e2eb694009923530` | 0 / 357 | KEEP |
| BR-006 | `bench/opus-midnight-rights-20261005` | `44aaceab55bdcf595ce56ff2ded562d79bf1d190` | 0 / 356 | KEEP |
| BR-007 | `claude/brand-me-lux-foundations-audit-8zywr3` | `eed6737062da451a38114f8002159c1bed0e5cb5` | 5 / 370 | PRESERVE THEN RETIRE |
| BR-008 | `claude/ci-repair-workflows` | `512021c35a6b9d381c94fe02495ba903f411b916` | 0 / 369 | DELETION CANDIDATE |
| BR-009 | `claude/midnight-rights-lifecycle-yhfyyu` | `a05f2e03e58e55cc2b392b8abc7b19f59659f820` | 5 / 0 | INTEGRATE |
| BR-010 | `claude/opus-commerce-agents-setup-szpmf7` | `161f6eb6498c6085c8a070d2a389e3562b1b1ba9` | 0 / 69 | KEEP |
| BR-011 | `claude/opus-consumer-domains-1csp2g` | `babb3604ae2f33018edf0ad45270887d4b01945b` | 18 / 17 | INTEGRATE |
| BR-012 | `claude/opus-foundation-w00-2hgiw5` | `f5c906ab163084f791a7b601f3bbb71a828bb934` | 0 / 18 | KEEP |
| BR-013 | `claude/setup-design-system-cli-6iovG` | `8b9bd4a718ef0d2ec0826b94537d438df68b2b32` | 8 / 373 | PRESERVE THEN RETIRE |
| BR-014 | `codex/chain-projection-worker-20261022` | `e96356eaffaffb0c64e2a4ed1b2e1753a8cd992d` | 1 / 293 | DELETION CANDIDATE |
| BR-015 | `codex/console-contract-publication` | `06d8fc13f3133fea5108164266a6fee59b88db1f` | 0 / 88 | DELETION CANDIDATE |
| BR-016 | `codex/consumer-design-preview` | `0ff12fbdbce2a8b4ea1391a02ef3ea821ae6a420` | 20 / 87 | INTEGRATE |
| BR-017 | `codex/critical-dependency-repairs-20261022` | `542b52cc12ca668e64c13a072acf7374bd0a5752` | 2 / 292 | DELETION CANDIDATE |
| BR-018 | `codex/docker-pipeline-20261022` | `a5373d5c0eef5466a20e6ef4d4682a06275e20d4` | 7 / 296 | DELETION CANDIDATE |
| BR-019 | `codex/durable-chain-reconciliation-20261022` | `e2dcbdd3a916c23ac409ee564b6ada3fa56f0cf6` | 2 / 294 | DELETION CANDIDATE |
| BR-020 | `codex/durable-outbox-pubsub-20261022` | `65367789130870c8c2a0e786f2d6152357d88093` | 2 / 291 | DELETION CANDIDATE |
| BR-021 | `codex/explain-execution-details-and-next-steps` | `15ae7bf3ce02773ec431977cd23c6f5b19d811fd` | 1 / 371 | DELETION CANDIDATE |
| BR-022 | `codex/midnight-integration-20261022` | `32e63d4d87f515f5398ab01d1eb18eba94019b5c` | 3 / 295 | DELETION CANDIDATE |
| BR-023 | `codex/privacy-recovery-safety-20261023` | `e6274ef5a19e5db77d27c19c3b7349b08fa96c84` | 2 / 290 | DELETION CANDIDATE |
| BR-024 | `codex/rights-export-worker` | `02297b2cea98dfd54818de5a3104a1ce341acfcd` | 2 / 288 | DELETION CANDIDATE |
| BR-025 | `codex/rights-privacy-read-api` | `10a468395cde98eaf7b7f0159855c7bac3a5827a` | 1 / 289 | DELETION CANDIDATE |
| BR-026 | `docs/brandme-full-experience-2026-10-05` | `b31373170953705f180246e254a8c2e9a41b4931` | 0 / 357 | UNKNOWN |
| BR-027 | `fix/property-test-vacuity-guard-flake` | `a699331df56c12570067223dbaad9c0a86d1567a` | 1 / 300 | DELETION CANDIDATE |
| BR-028 | `main` | `ed19dc151d103b108cf972e6d37971c55d5dcf60` | 0 / 0 | KEEP |
| BR-029 | `mia/next-plans-20261025` | `057320d4bf01e86c381d6750202e6e5bb7bb741f` | 0 / 78 | DELETION CANDIDATE |
| BR-030 | `mia/orchestration-20261023` | `27f3215a9cb3512ee6d92a5a6fb13519bd82385d` | 0 / 276 | DELETION CANDIDATE |
| BR-031 | `mia/pipeline-seed-20261030` | `5e9eceb67599f2465ca2d7a47b71234965f0b2f1` | 0 / 14 | DELETION CANDIDATE |
| BR-032 | `triage/pnpm-version-conflict-20261023` | `114470007e9c631010ee22930a8ddfb75d0ea700` | 1 / 363 | DELETION CANDIDATE |
| BR-033 | `triage/pnpm-workspace-frontend-20261008` | `64d5fd6ca17d3cfebd600c0d9fa2a7584f0f4f17` | 1 / 368 | DELETION CANDIDATE |
| BR-034 | `w11/integration-20261008` | `bec80b1f25fcd4a310529888351c45c71d33dc4a` | 0 / 319 | UNKNOWN |
| BR-036 | `claude/amazing-goodall-ntrljq` | `45e157f5555647f0e9add424b9634f27d606211d` | 1 / 0 | KEEP |

**BR-035 — original local `refs/heads/main` at `0f5f58a9eecaca46b367c9bd96f89654343fa5fb`: KEEP.** It is the user's preserved working baseline, not a cleanup target. The audit clone's local main also retains this initial commit while its worktree is detached at remote main.

Final classification of the 35 remote heads: **10 KEEP, 3 INTEGRATE, 2 PRESERVE THEN RETIRE, 2 UNKNOWN, 18 DELETION CANDIDATE**. Adding preserved local BR-035 yields 36 inventory records and 11 KEEP records.

The primary comparison target is current canonical main. Historical PR base branches are retained separately in the JSON: #32–#35 first merged into bench lanes; #36 first targeted the spec branch; #55 targeted the spatial lane. W11's early integration history merged four Opus lanes. The six bench names remain in lane assignment documents, and both Astra branches have literal push-trigger bindings in [consumer-ui.yml:7](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/consumer-ui.yml#L7) and [spatial-validation.yml:5](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/spatial-validation.yml#L5). Their code having landed is insufficient grounds for deleting those live routing names.

### Final snapshot addition: BR-036 / draft PR #71

At the final 2026-11-01 recheck, **`claude/amazing-goodall-ntrljq` at `45e157f5555647f0e9add424b9634f27d606211d`** appeared as one documentation-only commit on unchanged main. The entire 230-line [Stripe Connect plan](https://github.com/brandmeonline/Brand-Me-Labs/blob/45e157f5555647f0e9add424b9634f27d606211d/docs/build/stripe-connect-plan.md#L1) was read. [Draft PR #71](https://github.com/brandmeonline/Brand-Me-Labs/pull/71) proposes separate brand/atelier and member-resale payment flows and explicitly says none of the Connect proposal is implemented. It identifies open payout-authentication, payee/merchant-of-record invariant, KYC, country and dashboard decisions. Those provider/API and financial/legal assertions were not independently verified in this incremental review and receive no implementation-readiness credit. **KEEP** while the active proposal is reviewed; do not infer new authorization to provision accounts or implement money movement.

The [captured new-head CI metadata](evidence/history-new-branch-checks.json) shows six successful checks, one failed Test Frontend check and two checks still in progress. This is a time-specific observation, not a final green verdict or proof that the documentation change caused the failure. [Delta evidence](evidence/history-final-ref-delta.json) records the one-ref, no-prune fetch, unchanged main, and clean audit worktree; stable branch conclusions were not redone.

## What apparent branch uniqueness really means

The October 22–23 Codex slices are a clear squash-merge trap. `git cherry` marks several original commits `+`, but comparing each branch's aggregate diff to its PR squash yields the same stable patch ID, and its entire tree equals the original merge tree. No new implementation remains to integrate from those tips. Later main changes are retained; the audit does not propose replaying old dependency versions, network tuples, or earlier privacy guards.

| Branch ID | Merged PR | Exact replacement commit containing the same original tree | Current retained implementation sampled |
|---|---:|---|---|
| BR-014 | [#45](https://github.com/brandmeonline/Brand-Me-Labs/pull/45) | `74e137534b1b6f04e536a433977763a1775dc950` | Chain reconciliation worker/queue, rights projection, V012 |
| BR-017 | [#46](https://github.com/brandmeonline/Brand-Me-Labs/pull/46) | `fbadf012155663be8e174c4845e6c9c0e3b4dca6` | Package/lockfile security updates and image audit gates |
| BR-018 | [#42](https://github.com/brandmeonline/Brand-Me-Labs/pull/42) | `1ac8f97da6b326cfe6f425e26abd0daac6044917` | Docker/runtime smoke, credential exclusions, strict legacy guards |
| BR-019 | [#44](https://github.com/brandmeonline/Brand-Me-Labs/pull/44) | `238f65a357c64169662738b17adbb526c999a52b` | Durable chain journal, authenticated reconciliation, V011 |
| BR-020 | [#47](https://github.com/brandmeonline/Brand-Me-Labs/pull/47) | `1a4cfd1d142bb562b5c2e12c211111345a6fc23d` | Fenced Pub/Sub outbox, transport failure handling, V013 |
| BR-021 | [#28](https://github.com/brandmeonline/Brand-Me-Labs/pull/28) | `0f5f58a9eecaca46b367c9bd96f89654343fa5fb` | MCP commerce handler and regression groundwork |
| BR-022 | [#43](https://github.com/brandmeonline/Brand-Me-Labs/pull/43) | `a2e625a104c4e69e88731ff81e6cdf7b4c2940a4` | Rights auth/event/service boundaries |
| BR-023 | [#48](https://github.com/brandmeonline/Brand-Me-Labs/pull/48) | `f4a4015f1820f35a11312ea020421a9d091dbd28` | Privacy write freezes, restore barriers and regression tests |
| BR-024 | [#50](https://github.com/brandmeonline/Brand-Me-Labs/pull/50) | `5174ec27a482e9364173be82137c7d7dbc17f375` | Authenticated export process/private download path, V014 |
| BR-025 | [#49](https://github.com/brandmeonline/Brand-Me-Labs/pull/49) | `20bf3e95af466df7e3a8eb6cb14c9823921a12b7` | Authenticated read API and gateway adapter |
| BR-027 | [#39](https://github.com/brandmeonline/Brand-Me-Labs/pull/39) | `49623e4e3746eb2913b839545428d21b5d03e12d` | Deterministic property-test preamble, followed by random-path repair |

These commits are retained in current main's history, not merely mentioned in this report. Added-path comparisons found no missing newly introduced paths for the Codex implementation slices above. Current examples include [outbox worker](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/events/worker.py#L90), [privacy guard](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/privacy/deletion.py#L191), [read API](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/read_api/app.py#L99), [export API](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/privacy_exports/app.py#L53), and [deterministic test preamble](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/tests/contracts/property.test.ts#L218). These static links establish retained code, not business-transaction success.

The historical-revert search was not used as proof that no regressions exist. It found two messages mentioning reversion/review context, no explicit `Revert ...` subjects in the recorded result. The inspection also considered merge commits and subsequent current-tree changes. See [complete commit graph metadata](evidence/history-all-commits.txt) and [search result](evidence/history-revert-commits.txt). The unexecuted regression risk remains explicit.

## Preserve and connect the three active product lanes

### BR-011 / PR #66 — consumer domains, first integration candidate

Head **`babb3604ae2f33018edf0ad45270887d4b01945b`**, merge base **`97d54477f7667dade1a4fd7220c0b2694cffb604`**, 18 ahead/17 behind main. It extends actual service routers with Flow, houses/standing, surveys, points-to-credit conversion, persona cards, closet visibility, rooms, experiments and share projection. The composition is visible in [persona/app.py:45](https://github.com/brandmeonline/Brand-Me-Labs/blob/babb3604ae2f33018edf0ad45270887d4b01945b/brandme_core/domains/persona/app.py#L45) and gateway route mounts. This is valuable backend work, with privacy and idempotency fixes accumulated during review.

Preserve the complete branch sequence, especially implementation commits **`d502a0c2d6443e3a70f029739bc5c85894d0c18a`**, **`fa0a1a21b0fca25457565a21bf8eb40ba162c0a6`**, authorization/privacy fix **`068001dcc83ecdee465eabc76bf984339bf278fe`**, and subsequent review fixes through the exact head. The full ordered commit/file list is in BR-011's JSON record. Do not salvage only the first feature commits while discarding later audience/privacy/credit corrections.

Proposed integration: merge fresh main into this existing lane, resolve foundation test/catalog ownership, settle the shared migration reservation, and review the full resulting diff. Then integrate to main as a reviewed unit. Accept only after the migration registry and empty/V015 upgrade tests pass, Now/Flow/card/room/survey boundaries are exercised against synthetic authenticated users, cross-user/deletion restrictions hold, and current shell failures are explained and corrected. At audit time GitHub reports mergeable but unstable, with **`shell` failed** at [job 124211331023](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41098774318/job/124211331023). All 19 review threads are marked resolved in the [paginated review-thread snapshot](evidence/history-github-review-threads.json), but review submissions were comments, not an approval; thread resolution does not establish foundation's required ownership decision. The other three open PRs have zero review threads in that snapshot.

**F-BR-004:** conversion is connected to this branch's service, but [credits.py:179](https://github.com/brandmeonline/Brand-Me-Labs/blob/babb3604ae2f33018edf0ad45270887d4b01945b/brandme_core/domains/rewards/credits.py#L179) exports `apply_credit` for commerce. The repository-wide branch search finds its definition and tests only, no application checkout call. Integration therefore still needs a commerce transaction that applies credit atomically with the order, plus insufficient/expired/wrong-user/wrong-currency/retry checks. A unit/emulator call to that function is not a user purchasing with credits.

### BR-009 / PR #70 — rights commands and privacy handoff

Head **`a05f2e03e58e55cc2b392b8abc7b19f59659f820`**, five commits directly on pinned main. Preserve all five: **`c55c010dbcc6f18a9bf12146dcea0045652dc7a9`** (plan receipt), **`cd6224d3dfb849c0746b78306cd342578db7d688`** (privacy extension), **`d58e3c8e8426e69225b8c3ea009e4a6cb58c6bf2`** (command backend), **`6a4a11a6b424256443acd39de52b544efef5f68c`** (reprint attestation/My Data composition), and head **`a05f2e03...`** (evidence packet).

The branch adds `brandme_core/rights_commands/{app,config,__main__}.py`, `domains/rights/commands.py`, `domains/privacy/composition.py`, gateway `transfers.ts`, V016 transfer invite schema, and tests including `tests/test_rights_commands.py`, `tests/test_my_data_composition.py`, `commands-backend.test.ts`, privacy and Spanner reconciliation cases. It guards member entitlement/epoch, private invite digest, recent auth, idempotency and restore/privacy barriers; it does not sign or broadcast a member wallet transaction.

**F-BR-002:** [transfers.ts:4](https://github.com/brandmeonline/Brand-Me-Labs/blob/a05f2e03e58e55cc2b392b8abc7b19f59659f820/brandme-gateway/src/routes/v1/transfers.ts#L4) is deliberately unmounted. The branch's public mount file contains no `createTransfersRouter` import/call. The executable [__main__.py:30](https://github.com/brandmeonline/Brand-Me-Labs/blob/a05f2e03e58e55cc2b392b8abc7b19f59659f820/brandme_core/rights_commands/__main__.py#L30) calls `guard("rights_commands")` while shared trust-path configuration lacks that service, so strict modes remain refused. Its [deployment instructions](https://github.com/brandmeonline/Brand-Me-Labs/blob/a05f2e03e58e55cc2b392b8abc7b19f59659f820/brandme_core/rights_commands/README.md#L48) also require migrations, distinct internal service credentials, private network routing and a configured test network/contract. Keys alone cannot complete this flow.

Proposed integration: after allocating a nonconflicting migration number, integrate the coherent branch rather than isolated route files; have foundation review the mount, audited trust paths, packaged runtime/deployment binding and privacy handler contract. Keep strict refusal until those checks are satisfied. Acceptance requires authenticated transfer creation → recipient binding → sender status, authorization/CSRF/recent-auth/idempotency/expiry tests, My Data deletion/export integration, then the separately authorized wallet/journal/finality path. CI shows 19 successful check runs and deployment skipped on this SHA; that is not a deployed rights-transfer receipt. PR #70 remains draft.

### BR-016 / PR #63 — consumer preview, after backend contract reconciliation

Head **`0ff12fbdbce2a8b4ea1391a02ef3ea821ae6a420`**, merge base **`77280249df4e91d93b4d814b140bd5e38bba4735`**, 20 ahead/87 behind main. Preserve the feature sequence beginning **`15f637918fbb737c4b5c9e6cd9fcf61038c43cf9`**, **`77b0a4a530ddd23837c932e917fdc3fd933a3d52`**, **`bd7c731f063a28b729c46ff75fcee9d62a7d7d62`**, navigation fix **`990e4a940e50a0fc9a5e8b91762300a814f09765`**, all browser/haptic tests and later contract/history handoffs. Full sequence and 23 changed paths are inventoried.

Useful code includes the social Now/Flow/Editorial entry pages, private persona-card presentation, optional friend-response heartbeat and its browser checks. [horizons.tsx:27](https://github.com/brandmeonline/Brand-Me-Labs/blob/0ff12fbdbce2a8b4ea1391a02ef3ea821ae6a420/brandme-frontend/features/social/horizons.tsx#L27) explicitly says Flow/Editorial feeds are not connected. Do not count these pages as completed integrations with PR #66.

Proposed integration: merge actual current main into the lane, resolve the updated frontend/spatial/foundation contracts, connect agreed #66 endpoints, and then obtain human review of intentional visual changes. [Current shell job](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41065699801/job/124096382670) fails at this head; successful component/build/live-domain checks do not approve new visual baselines. The branch's Stage 17 handoff distinguishes earlier reported tests from fresh execution and expressly leaves device/screen-reader and design-artifact reconciliation unverified. It should remain a draft until those declared gates are resolved.

## Cross-lane defects to resolve before merging

**F-BR-001 — duplicate V016 reservation.** #66 adds [V016_consumer_design.sql](https://github.com/brandmeonline/Brand-Me-Labs/blob/babb3604ae2f33018edf0ad45270887d4b01945b/brandme-data/spanner/migrations/V016_consumer_design.sql#L1); #70 adds [V016_rights_transfer_invites.sql](https://github.com/brandmeonline/Brand-Me-Labs/blob/a05f2e03e58e55cc2b392b8abc7b19f59659f820/brandme-data/spanner/migrations/V016_rights_transfer_invites.sql#L1). The current [runner rejects duplicate integer versions at line 99](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-data/spanner/migrations/runner.py#L99), and the [registry test](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/tests/foundation/test_migrations.py#L44) requires one contiguous reservation per number. This is a confirmed static integration conflict; neither branch alone demonstrates the combined migration sequence. Allocate V016/V017 in the chosen merge order and update registry, schema minimum/version checks, fixtures and docs consistently. First inspect any environment ledger: never rename a migration already applied to a shared database merely to make the files fit.

**F-BR-003 — canonical pipeline state contradicts published ancestry.** Main's [pipeline-state.md:88](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/docs/build/orchestration/pipeline-state.md#L88) claims PR #63 re-synced to foundation `97d54477` using `75f0ff0`. Actual ancestry excludes `97d54477`, and #63's own Stage 17 correction says the reported commits were unavailable and synchronization remains outstanding. The same dated pipeline snapshot describes an older #66 head as green and Midnight as having no PR; current metadata shows #66's failed shell and open draft #70. Treat the pipeline file as a dated, partly erroneous status record until updated from exact published SHAs. Never let its standing merge language override this audit's no-merge authorization.

Detailed severity, confidence, affected revisions, preconditions, reproduction, fix, effort assumptions and acceptance criteria: [findings-branches.json](evidence/findings-branches.json). These are delivery/integration findings, not claims of exploitable security vulnerabilities.

## Older value worth preserving without a blanket merge

**BR-007 / draft #29:** `brandme_foundation/` contains independent tenancy models, runtime health/config/HTTP support, event broker and observability, with four dedicated test modules and historical audit/porting documents. Twenty-two added paths are absent on modern main. Their implementation is real code, but integration with modern `brandme_core` was not established; the new foundation already has its own modes, tenant/member authorization, durable outbox, identity and privacy contracts. The transplant's Pub/Sub broker and runtime flag model are materially different from current durable event boundaries. Preserve exact **`eed6737062da451a38114f8002159c1bed0e5cb5`** and the five unique commits; compare any desired cost/tenant/health capability with the current equivalent and port a small test-backed behavior only if a gap is demonstrated. The branch's historical claims about another repository were not independently audited here. Do not merge that older parallel foundation wholesale. Close/archive the draft only after an owner disposition and verified retention; no such action was taken.

**BR-013:** preserve **`8b9bd4a718ef0d2ec0826b94537d438df68b2b32`**, particularly design-audit commits **`12f5ee727613472d0f6ec819e220b6cdffa72178`**, **`425918ccb933a3d5f4213dfd9a2861ca3b9fecde`**, **`6de84d4bc239d7b75ea947aeafbc3114bd31ca6b`**, and head. The unique `.claude/skills/design-audit/` skill, June audit and concept rationales are historical design material. They are markdown concept descriptions, not a completed interface or observed runtime screenshots. Original design-system tooling was already merged via #26; current branch endpoint diff under `.claude` consists of these additional audit paths. Review tooling provenance and hooks independently before adopting them. Do not revert modern application/chain code to this stale branch snapshot.

**Closed unmerged PR #2:** examined its two-file patch: legacy PostgreSQL worker, fabricated transaction hashes, and policy stub. Current policy/orchestrator implementations occupy those paths with newer Spanner-era behavior, and their remaining limitations belong in the main-code audit. No valuable missing production integration was found in that abandoned stub. Preserve its PR/history as historical context; do not revive it. [Captured patch](evidence/history-pr-002-files.json).

**Closed unmerged PRs #37/#55:** the first attempted frontend workspace membership with an obsolete pnpm/lockfile generation; the second removed a conflicting pnpm version pin but did not repair membership by itself. Current [workspace line 9](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/pnpm-workspace.yaml#L9), lockfile importer and [workflow line 36](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/module-regression.yml#L36) supply the semantic replacement. Do not merge the old lockfile to recover a one-line membership change already present.

## Code disposition and proposed merge order

| Code group | Disposition | Reason and next acceptance evidence |
|---|---|---|
| Main foundation identity/modes/contracts/migrations, durable events, privacy and rights read/export services | Retain and repair verified gaps | Reuse canonical contracts. Retained paths and squashed history are evidenced above; operational/runtime limits remain in the main reports. |
| PR #66 domain/services/tests | Integrate, then connect commerce redemption | Preserve later audience/privacy/credit fixes; migrate once; run authenticated multi-user/journey tests. |
| PR #70 command backend/privacy composition | Integrate and connect | Resolve V016, mount transfer routes, review strict boot inventory and deploy wiring before enabling strict modes. |
| PR #63 preview | Retain, reconcile and connect | Preserve interaction work; sync main; connect backend contracts; deliberate visual review; do not erase baseline failures by accepting images automatically. |
| PR #29 parallel foundation | Preserve; selectively consolidate only a proven gap | Avoid parallel tenancy/event/runtime contracts without demonstrated product value. |
| BR-013 historical design output | Archive proposed | Preserve source provenance and useful rationale, label historical; exclude from runtime readiness evidence. |
| Squashed Codex/triage branch refs | Conditional ref retirement only | Replacement source/history already on main; no removal of code/tests/migrations/assets proposed. |
| Legacy imports, dynamic registrations, media/assets and operations scripts on main | Follow component-specific decisions in architecture report | Branch age/import count is insufficient to call source unused. This branch proposal does not independently declare those modules removable. |

Proposed dependency order: **(1)** reconcile authoritative branch/checkpoint facts and reserve migration numbers; **(2)** synchronize and finish #66's review/CI gates; **(3)** connect agreed #66 APIs in the synchronized #63 preview and verify a complete synthetic journey; **(4)** integrate #70 with foundation mount/mode/runtime handoff, then verify its separate wallet/chain dependencies as authorized; **(5)** review historical salvage and make individually approved retirement decisions. #70 development can proceed independently of consumer UI once migration/schema coordination is resolved. This is an integration proposal, not authorization to merge or remediate during the audit.

## Reviewed cleanup proposal — commands are examples, not executed

The 18 candidate rows identify exact remote refs and expected tips. Confidence is high for ref/PR/tree-equivalence facts and medium for final retirement because external consumers and every current behavior were not exhaustively verified. No branch head, code, tag, archive, or preservation ref was created or deleted. The final refresh added only BR-036's remote-tracking ref in the isolated clone. No push/commit/merge occurred.

Before any separately authorized retirement:

1. Refresh the exact remote tip without pruning and compare it with the table; stop on any difference. Recheck open/stacked PRs, protections/rulesets, active worktrees, workflow bindings, deployment branch restrictions, documented automation and externally managed consumers.
2. Preserve the approved exact tip in a durable retained ref or bundle. Keep original commit metadata where squash merged. Place the archive in an owner-approved durable location, record its checksum and manifest, and actually recover it in a separate empty repository. A SHA in this report is not a backup.
3. Resolve open PRs and active routing first. Do not retire KEEP, INTEGRATE or UNKNOWN rows under this proposal. BR-007/BR-013 need their named salvage/archive disposition before even becoming candidates.
4. Delete only an individually approved ref with an expected-tip lease. Recheck the canonical replacement and keep source-code cleanup in a separate review.

One concrete example for **BR-014**; these commands have **not** run:

```powershell
# Revalidate exact remote ref; expect e96356eaffaffb0c64e2a4ed1b2e1753a8cd992d.
git ls-remote --heads origin refs/heads/codex/chain-projection-worker-20261022

# After separate approval, from a clone containing the verified ref:
git bundle create branch-BR-014.bundle refs/remotes/origin/codex/chain-projection-worker-20261022
git bundle verify branch-BR-014.bundle
Get-FileHash -Algorithm SHA256 -LiteralPath .\branch-BR-014.bundle

# Independent recovery proof in a new directory, before deletion:
git init branch-BR-014-recovery
git -C branch-BR-014-recovery fetch ..\branch-BR-014.bundle refs/remotes/origin/codex/chain-projection-worker-20261022:refs/heads/recovered
git -C branch-BR-014-recovery rev-parse refs/heads/recovered
git -C branch-BR-014-recovery fsck --full

# Only after the approved retention/consumer checks and fresh tip comparison:
git push --force-with-lease=refs/heads/codex/chain-projection-worker-20261022:e96356eaffaffb0c64e2a4ed1b2e1753a8cd992d origin :refs/heads/codex/chain-projection-worker-20261022

# Recovery, if separately authorized and the remote ref is still absent:
git -C branch-BR-014-recovery push https://github.com/brandmeonline/Brand-Me-Labs.git refs/heads/recovered:refs/heads/codex/chain-projection-worker-20261022
```

No mass-deletion script is supplied. Restore verification must include the exact expected SHA and retained contents; a successful archive command alone is insufficient.

## Remaining branch work

Branch/ref/PR inventories and structural comparisons are complete for the captured repository-visible scope. The broader branch audit is **incomplete**: branch-specific runtime behavior, every consequential changed line/test, hosted branch consumers outside GitHub metadata, the substantive validity of every historical review/comment resolution, external automation ownership, and recovery of proposed archives have not all been verified. The exact continuation is to review the named active-lane trust paths and remaining owner/review decisions at refreshed SHAs, perform isolated acceptance checks after safe execution prerequisites are satisfied, and have the owner identify external bindings for the proposed retirement refs. Preserve this distinction when reporting the overall audit's completion status.

