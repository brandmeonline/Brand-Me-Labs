# Reconciliation — first audit (codex-01) × second audit (claude-opus-02)

Baseline `ed19dc151d103b108cf972e6d37971c55d5dcf60` (both audits). Date 2026-11-01. This file states what the two audits agree on, what the second corrected, what remains disputed and the exact evidence that would settle each dispute, and the final priority order. Cross-references: [`INDEPENDENT_REVIEW.md`](INDEPENDENT_REVIEW.md), [`CORRECTIONS.md`](CORRECTIONS.md), [`evidence/challenges.json`](evidence/challenges.json), [`evidence/branches/branch-verdicts.json`](evidence/branches/branch-verdicts.json).

## 1. Agreements (both audits, independently derived)

1. **Product state.** Brand.Me at `ed19dc1` is a substantial but unconnected consumer platform: persona, wardrobe, outfits, social decisions, rewards, rights reads/exports and chain reconciliation are implemented and mounted; commerce, catalog, assistant, providers, delegations and all `/ops` routers exist but are unmounted; no MCP server exists; browser sign-in exists only as a labelled dev simulation; the spatial closet is IndexedDB-only; recommendations rank an empty candidate list; nothing in any deployable topology closes decisions or settles rewards.
2. **What a user can do today.** Without a backend: guest onboarding, local closet/outfits/style, discover shell, try-on shell, settings — all device-local (52 second-audit screenshots). With the dev stack and emulator: the composite CI harness demonstrates dev sign-in → persona → API-seeded wardrobe item → 5-minute decision → reward → notifications → block → sign-out, with an in-process rewards dispatcher. Nothing is deployed anywhere observable; no releases, tags, environments.
3. **Branches.** Every squash-merged branch is an exact squash; six branches carry unique content (#29, #63, #66, #70, #71, BR-013's design-audit commits); #66 and #70 collide on V016 (and conflict textually in two files); the `pipeline-state.md` re-sync claim is false; `bench/astra-*` are bound to workflow push triggers; BR-007 and BR-013 must be bundled with verified recovery before any retirement; nothing was deleted or created by either audit.
4. **Security.** No Critical/High vulnerability; no live credential in tree or sampled history; strict modes fail closed; MCP executor, assistant runtime, SSRF guard, session/CSRF design are sound; the stored GCP SA key for publishing, the always-200 health route, the in-process limiter/replay caches, the immediate SIGTERM exit, the unpinned MCP dev tool, the CRITICAL-only Trivy gate and the Terraform drift are real.
5. **Integrations.** Nothing works end-to-end against a real provider; keys alone cannot connect unmounted routers, create resources, run migrations or implement the missing browser login. Deployed SHA/digest unknown.
6. **Roadmap.** M0 = one synthetic journey on one revision through canonical composition (WP-01/04/05/06); M1 adds real identity, privacy scope, resources/IAM, operations; neither is production.

## 2. Corrected conclusions (second audit prevails; see `CORRECTIONS.md`)

| Topic | First | Second | Why |
|---|---|---|---|
| BR-026, BR-034 | UNKNOWN | DELETION CANDIDATE (medium) | pure ancestors; no consumer; commits stay reachable |
| F-SEC-003 severity | High | Medium | single admin collaborator; no second writer; protection wouldn't bind admin |
| F-SEC-006/007 severity | Medium | Low | documented limitations; preStop sleep |
| CMP-039 `brandme_gateway/` | no consumer | 2026-11-01: "script consumer in `run_all.sh:14`" — **withdrawn 2026-11-02**, the first audit is right (C-15); still remove (mock auth) | SC-20 |
| `agents/` retention rationale | consumed by `deploy-brandme.sh` | consumer is inoperable (`agents/lib/common.sh` missing) | SC-44 |
| CI reproducibility | green with open alerts | also red-on-new-advisories (`pnpm audit --prod`, no floor); main's green not reproducible today | SC-32, PR #71/#72 |
| Helm deployment view | declares workloads | `consumerDomains.enabled: false` default; `BRAIN_SERVICE_URL` unset; probes on always-200 route | SC-40/45 |
| Compose dev topology | needs key pair, no media | also cannot start events worker/exports (undeclared emulator hosts) | SC-46 |
| BR-036 / PR #71 | docs-only | now Stripe Connect code (stale, not wrong) | delta |
| Inventory counts | 35 heads / 5 PRs | 36 / 6 | delta |
| M0 order | 01→04→05→06 | 01→05→04→06, with #72 first | SC-31/46 |

## 3. Remaining disputes and the exact evidence that resolves them

| # | Dispute | First audit | Second audit (incl. its branch sub-agent) | Evidence needed |
|---|---|---|---|---|
| D-1 | Six zero-content lane/bench refs (`bench/opus-*` ×4, `claude/opus-commerce-agents-setup-szpmf7`, `claude/opus-foundation-w00-2hgiw5`) | KEEP (orchestration docs name them) | UNKNOWN / owner decision (sub-agent: DELETION_CANDIDATE) | Owner statement whether the round-03 lane process is still active and whether any external tooling (dashboards, session templates) resolves these names. No git evidence can settle it. |
| D-2 | Draft PR #29 (`brandme_foundation/`) | PRESERVE THEN RETIRE | PRESERVE THEN RETIRE (sub-agent: INTEGRATE low) | Owner disposition of #29; a demonstrated capability gap in `brandme_core` that `brandme_foundation` fills. Absent that, no integration. |
| D-3 | Whether branch protection matters now (F-SEC-003 rating) | High | Medium | Whether non-owner identities (AI sessions, GitHub App installations) can push to `main`; the App's permission set. A ruleset including admins makes the dispute moot. |
| D-4 | "Isolated local demo" readiness | promising, not revalidated | builds; full Foundation gate `pnpm check` 12/12 (pytest 2146/20/17 strict); gateway 169/169; rules 6/6; composed smoke 7/7; canonical gateway→`persona.app`→Spanner API journey 16/16; **hand-composed worker chain 18/18 — a friend-decision reward settled exactly once through `events.worker` → Pub/Sub → `persona.ingress`** (2026-11-02). Still unexecuted here: the browser UI on top of that chain; deadline-expiry closure via `jobs` | One same-revision run of `consumer-ui.yml` live-domains (repin `BRANDME_DOMAIN_REFERENCE`) for the browser layer. The dispute has narrowed to that single layer; the worker side is a deployment-configuration task (WP-05), demonstrated to be code-complete. |
| D-5 | Intended GCP project for image publishing | "reconcile hardcoded project" | `lux-realestate-app` named; mismatch with product | Owner confirms project; then WIF migration (WP-02). |
| D-6 | Dependabot / 78 code-scanning alerts reachability | 19 High/Critical triaged statically | not re-triaged by the second audit | Dependabot access or a current `trivy fs`/SBOM run against the exact image digests. |

No dispute concerns a deletion: every ref either audit would delete is agreed by both (20 candidates = first audit's 18 + BR-026 + BR-034; the pack's tally line said 19 and 7 KEEP and was corrected to 20 and 5 on 2026-11-02, C-16); every ref either audit would keep for process reasons is withheld from deletion.

## 4. Final priority order (combined)

Severity and product importance are kept separate from sequence; this is the sequence.

**Immediate containment / evidence (days)**
1. Merge or supersede **PR #72** (or set a `pnpm audit` floor + allowlist) so CI is reproducible; record gate semantics (S2-OBS-002). *Update 2026-11-02:* #72's full CI run (41319340979) is green; #71's red at its new tip (41318692121) is the same gate, not its code — confirming the fix and the diagnosis.
2. **WP-01** reduced: repin `consumer-ui.yml:82` to the job's own checkout; align the emulator pin (1.5.28 → 1.5.45); keep the historical composite run labelled as such.
3. **WP-02**: WIF for image publishing (F-SEC-004/S2-SEC-001) after the owner confirms the publish project (D-5); ruleset on `main` including admins (F-SEC-003, Medium); pin/replace the MCP dev tool (F-SEC-001).
4. **S2-SEC-003** fix (brain must not report success on orchestrator failure) if the legacy scan path is demonstrated to anyone; otherwise schedule with WP-14.
5. **WP-03** dependency disposition (D-6).

**M0 — one synthetic journey on one revision (weeks)**
6. **WP-05**: compose `persona.jobs` + `persona.ingress`; enable `consumerDomains`; add the Pub/Sub/GCS emulator services the worker requires; dependency-aware readiness that matches the deployed topology (not brain). *2026-11-02:* demonstrated to be configuration-only — the processes composed by hand with env vars settled a reward exactly once (SC-61); the exact env names and topic/subscription shapes used are in `evidence/runtime/emulator-run.md`.
7. **WP-04**: browser Add → server wardrobe (member-aware repository; explicit guest migration).
8. **WP-06**: `/me` reflects session; cleanup covers all 9 guest stores.
9. **WP-07** (optional): inject candidate/wardrobe sources.

**Branch recovery (parallel, owner-gated)**
10. Allocate V016/V017 (F-BR-001); integrate **#66**, then **#63** against the accepted API, then **#70** with mount + trust-path registration (F-BR-002).
11. Bundle + verified recovery of BR-007/BR-013; owner decision on D-1/D-2; then individually authorized ref retirements of the 20 candidates with fresh tip checks.

**M1 — staging pilot**
12. **WP-08** browser OIDC (F-UX-003) — launch-blocking.
13. **WP-09** minimal topology; **WP-10** privacy scope; WP-13 commerce slice only after identity and data safety; #71's Stripe Connect code reviewed then.

**Later**
14. **WP-14** legacy consolidation: `agents/` + `deploy-brandme.sh` + Makefile deploy targets + `scripts/deploy.sh` (inoperable chain), `brandme_gateway/`, `brandme_core/health.py`, eight unbuildable Dockerfiles, console `lib/api.ts` bypass client, CLAUDE.md citation fixes, Terraform.

## 5. Is the combined audit reliable enough to guide cleanup and implementation?

**Yes, for everything that does not require owner knowledge or cloud access.** The two audits were produced by different tooling and reviewers, the second ran the code — including, on 2026-11-02, the full Foundation gate, the repository's composed smoke, the canonical gateway→consumer-domain→Spanner path and a hand-composed run of the worker processes, all green — and every consequential conclusion either converges or is corrected with cited evidence. Specifically reliable: the 19-ref deletion list (with the stated preconditions), the three-lane integration order, the V016 remedy, the break boundaries of every journey, the "keys alone do not help" conclusion, the M0 package set, and the security backlog.

**Not yet reliable, and why:** (a) anything about deployed state — nothing is observable; (b) the six lane/bench refs (D-1) and draft #29 (D-2) — owner decisions; (c) the exact-image dependency posture (D-6); (d) real-user identity, device/AR/accessibility behaviour, provider sandboxes — untested by both audits.

**Remaining blockers before implementation starts:** owner answers to D-1, D-2, D-5; a decision on PR #72 (or the audit floor); authorization to commit the audit packs to the repository.

**Next concrete action:** merge PR #72 (or apply its two-file override in a reviewed change), then run `consumer-ui.yml` with `BRANDME_DOMAIN_REFERENCE` repinned to the job's own checkout and the emulator pin aligned — one green same-revision live-domains run converts the composite evidence into the first same-SHA M0 acceptance artifact and is the smallest possible first step of WP-01.

*Readiness note:* the second audit's emulator-backed Python run reproduced CI's counts exactly (`2146 passed, 20 skipped, 17 xfailed`, strict skip rule, exit 0; [`evidence/runtime/emulator-run.md`](evidence/runtime/emulator-run.md)). Together with the no-emulator run, the Node suites and the builds, the **isolated local demo** tier now has direct execution evidence; D-4 narrows to the composed journey only. Staging and production verdicts are unchanged: not established.
