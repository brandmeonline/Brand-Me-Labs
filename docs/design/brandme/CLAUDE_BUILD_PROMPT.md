# Claude kickoff — build the complete Brand.Me experience

Use Claude Code with Opus 5.5 if it is available in your account. Select the model through the actual client configuration; the documented API model ID is `claude-opus-5-5`. Do not claim model access from the contents of this file.

Paste the instruction below while working in this repository. The instruction starts a sustained, checkpointed implementation. It does not require a single unreviewed code dump.

---

You are implementing Brand.Me in this existing repository. The founder has authorized a complete application build from `docs/design/brandme/README.md` and every linked chapter and machine contract. Read the entire package, root `CLAUDE.md`, and any applicable repository instructions before changing code. Reconcile the specification's baseline against the actual current branch.

The product is **Be More U**: a self-directed personality and fashion experience, a beautiful living wardrobe, trusted social decisions, loyalty for useful participation, and enduring garment provenance/ownership through Midnight. Preserve the full consumer vision. Do not reduce the assignment to a wallet, a digital-passport explorer, a retailer affiliate grid or a static design prototype.

Build in the canonical `brandme-frontend`, keep `brandme-console` for operators, reuse and repair the existing gateway/Python/Spanner/policy/cube services, and integrate real supported Midnight providers/contracts. Upgrade dependencies deliberately and pin compatible versions. The design package defines the default architecture; deviations need evidence and a written explanation.

Create `docs/build/implementation-status.md`, `compatibility-lock.md`, `deviations.md` and an evidence directory. Track each acceptance ID from `docs/design/brandme/contracts/acceptance-catalog.json` as passed, failed, blocked, not_run or not_applicable with actual evidence. Update the status file after every stage so work can resume across sessions. Do not mark implementation presence as a passing integration test.

Execute W00–W11 in chapter 06. Complete all independent authorized work without repeatedly asking the founder to choose routine implementation details. Preserve unrelated changes. Follow the repository branch/PR/approval rules and do not merge or deploy to production without the required authorization. Creating capability code is not permission to spend real money, send real messages, publish private information or transact on Mainnet.

The finished consumer experience must include:

1. A useful first reveal in roughly 90 seconds without wallet, camera or contact-import requirements; optional sign-up and idempotent guest migration.
2. Twelve inspectable and editable persona axes, declared/inferred/effective separation, locks, evidence suppression, snapshots, learning controls and recommendation explanations that reflect actual scoring.
3. Three beautiful selectable closet environments, real licensed/original 3D room and garment assets, the exact add-to-closet animation, persistent semantic placement, an accessible 2D equivalent, outfits, care and packing.
4. Friends, selected-audience sharing, five-minute server-timed purchase decisions, outfit proposals, notifications, blocks, revocable shares, an idempotent reward ledger, benefits and evidence-backed badges.
5. Honest visualization fidelity and progressive 3D/AR/live-overlay/photo-try-on capabilities with explicit camera/image consent and deletion. Never label generative imagery calibrated fit.
6. Authorized provider discovery/ingestion and an operator setup console. Nordstrom is initially an approved Impact publisher/deep-link path unless actual richer commerce access is verified. No guessed retailer APIs or unauthorized scraping.
7. Agent research and cart preparation, principal-bound tools, scoped delegation, exact quote approvals, bounded purchase authority, budget reservations, real provider order reconciliation and return/refund handling.
8. Real Midnight contract/provider integration, user-controlled private-state/recovery flows, actual observed operations, claim-level passports, rights-scoped transfer and licensed/quota-bound reprint. Distinguish physical possession, digital entitlement, authenticity and reproduction permission.
9. My Data inspection/edit/export/delete, consent revocation, derived-data suppression, private projection filtering, account isolation and operational recovery.
10. Complete empty/loading/offline/denied/expired/revoked/duplicate/failed/unknown-outcome states, responsive accessible UI and measured performance.

Eliminate misleading trust-path stubs. The current repository includes fake transaction/proof values, synthetic commerce success and invented ESG/reprint results. Production/sandbox must fail closed if a required real adapter is unavailable. Demo mode must remain beautiful and useful with persistent fictional fixtures and visible simulation labels. Do not substitute a mock for a live provider and report completion.

Resolve current external API/protocol details from official documentation. In particular, follow the current supported Midnight tuple, current Mainnet provider configuration, current AP2 Checkout/Payment mandate model, and current MCP authorization. The older `PLAN.md` is historical where these conflict. An internal shopping intent is not an AP2 credential.

Use the design tokens and screen/scene choreography as implementation requirements. Deliver actual garment/room files, materials, lights, thumbnails, manifests and rights records. A photograph on a plane may be a labeled fallback but cannot replace all specified 3D artifacts. Inspect the product at 390×844, 768×1024 and 1440×900, plus 320 px, large text, reduced motion and no-WebGL behavior. Fix visual issues visible in screenshots/video before calling the experience complete.

Implement the required setup/dev/check/journey/provider/contract/asset/evidence commands. Test high-risk invariants and integrated user journeys with actual persistence and multiple sessions. Do not invent test results, network receipts, partner agreements, proof artifacts or screenshots. If access or hardware prevents a test, record exactly what is missing and finish the rest of the application and setup flow.

When an external prerequisite is genuinely needed, prepare its concrete configuration screen, adapter and test first. State the specific remaining credential/agreement/device action and its effect. Keep the application useful and honestly capability-gated while awaiting it. Do not use a missing retailer credential as a reason to leave persona, closet, social, rewards or privacy unfinished.

Finish with a reviewable PR and a self-contained report: startup command, preview instructions, implemented journeys, visual evidence, executed tests, measured budgets, current provider matrix, Midnight evidence, deviations and remaining production gates. Separate **experience complete**, **integration verified** and **production approved**. The founder should be able to run and experience the complete product loop, not only read an architecture summary.

Begin by inspecting the current repository and writing the implementation-status checklist. Then build and verify until the authorized scope is complete or a specific external blocker remains after all independent work is finished.

---

## Resume instruction

If execution spans sessions: read `docs/build/implementation-status.md`, this design package and the latest commits; verify the recorded state; continue the first incomplete dependency-ready work package. Preserve completed evidence and do not restart from a fresh scaffold.
