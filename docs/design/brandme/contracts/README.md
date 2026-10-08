# Machine-readable implementation contracts

These files make the design reproducible. They describe required future behavior and fictional examples; they do not claim that the application, media assets, providers or blockchain operations already exist.

| File | Use |
|---|---|
| [design-tokens.json](design-tokens.json) | Generate CSS/TypeScript tokens, motion constants and scene budgets |
| [domain.schema.json](domain.schema.json) | JSON Schema 2020-12 definitions for core wire types and structural constraints |
| [contract-examples.json](contract-examples.json) | Valid fictional examples and deliberately invalid boundary cases |
| [demo-scenario.json](demo-scenario.json) | Deterministic members/products, room/garment asset requirements and integrated demo sequence |
| [reward-rules.json](reward-rules.json) | Versioned contribution rules, caps, settlement timing and reversal accounting |
| [acceptance-catalog.json](acceptance-catalog.json) | 150 MUST acceptance criteria, stage, procedure, pass condition and evidence method |
| [validate_spec.py](validate_spec.py) | Package-level schema, example, source/link and consistency validation |
| [requirements.txt](requirements.txt) | Dependency for the documentation validator only |

## Interpretation and code generation

Use snake_case for JSON wire fields. Generated application types may use another naming convention only through explicit tested serialization. IDs are opaque UUIDs. Revisions and nonnegative monetary minor units are decimal strings to avoid JavaScript precision loss; server arithmetic uses bounded integers. Negative reward ledger changes use a signed ledger field, not a negative checkout price. Refund amounts are positive money plus a refund transaction type.

The schema uses `$defs`; select the relevant definition by `$ref`. It is a core contract library, not the complete generated OpenAPI document. During implementation, generate a complete OpenAPI 3.1 surface matching chapter 03, all event-specific payload schemas, internal model types and their validators. Do not assume an arbitrary object is safe because `EventEnvelope.payload` is structurally an object: the event registry must resolve and enforce its exact payload schema.

Keep unknown axis values `null`. All 12 keys remain present so unknown, omitted and zero are distinguishable. A member's declared values, inference and effective ranking vector are separate. Context overrides and evidence metadata must be implemented in the full domain model even where the compact schema example omits them.

The `claim_level` on a wardrobe example is a display summary. Actual passport claims remain independent evidence records; tag verification cannot imply legal title, physical possession, valid copyright or calibrated fit. Do not order these labels into a universal “trust score.”

## Domain invariants beyond JSON structure

Structural schema validation is necessary and insufficient. Enforce these in deterministic domain code and tests:

1. Authenticated principal, delegation, environment and object policy decide authority; request fields never do.
2. A persona patch cannot contain duplicate axis keys, even if the two objects contain different values. Declared locks and suppressed evidence win over inference.
3. `If-Match` must match the current aggregate revision. Successful writes advance once. Idempotency keys bind the canonical request, identity and operation.
4. Placement quaternions are finite and normalized within an explicit tolerance; positions/scales are finite, asset-bounded and inside the selected semantic group. Reject NaN/Infinity before serialization. Slot ownership and layout/item ownership must match.
5. A decision's `closes_at` is computed on the server. Accept responses only when server transaction time is strictly before the deadline and the caller is in the valid audience. Limit to one response record per respondent/decision.
6. All quote components use one supported ISO currency. Check its real exponent. Sum exact line totals, discounts, tax and shipping with integer arithmetic; do not infer totals from formatted strings.
7. Expiry is after issue time and still valid at execution. A purchase approval is bound to the canonical material terms, not just the quote's string ID.
8. Verified provider capability requires appropriate current evidence; a non-null `evidence_ref` is not proof by itself. Unconfigured/unsupported checkout cannot execute.
9. A chain transaction reference must resolve against the intended network/contract and satisfy actual observation/finality policy. Merely passing the schema cannot establish settlement.
10. Reprint quota consumption, license validity, issuer/manufacturer authorization and uniqueness must be enforced by the real contract/workflow. A `remaining_quota` number from the browser grants nothing.
11. Shares filter allowed fields against entity-specific policy, current audience and block/revocation state. The arbitrary string array is a typed request, not permission to read arbitrary database columns.
12. All event payloads are minimal, classified, versioned and validated. Outbox/inbox uniqueness and monotonic projection rules handle duplicate/out-of-order delivery.

## Demo and asset requirements

Every person, merchant, product, quote and time sequence in the scenario is fictional. `.example.invalid` is used only to derive stable UUIDs. No fixture contains a live provider receipt, real blockchain proof, live merchant offer or manufacturing license.

Asset paths in the scenario are files the implementing agent **must create**, not assets supplied with this documentation commit. Create original or appropriately licensed room/garment geometry and media, include rights manifests and prove the files load. The final app must not display `requires-real-deployment` or fixture hash strings as verified data. The sample chain operation is deliberately only `prepared` with no transaction ID.

Interactive demos rebase relative events to a session clock. Deterministic tests freeze the stated clock. Otherwise a five-minute decision seeded with an old absolute timestamp would always be expired. Production uses authoritative server time, never the demo clock.

The quote example deliberately labels its hash as a fixture requiring recomputation. Production uses a real canonical encoder/hash plus verified approval and provider evidence. A sample total of USD 96.12 is illustrative demo arithmetic, not a Nordstrom price or tax promise.

## Acceptance evidence

Each catalog item starts `not_run`. The implementing agent records outcomes in a separate results artifact keyed by stable requirement ID; it must not rewrite the requirement to make its implementation pass. An external gate can be `blocked` with a specific missing prerequisite, while the corresponding local fixture test passes independently. `not_applicable` requires a documented justification and cannot silently remove a MUST product requirement.

Source links in the catalog point to the relevant chapter. Evidence methods include domain/integration/browser/security/asset/visual/accessibility/performance/provider/network/contract/device/operations/usability/inspection. A screenshot proves appearance, not a real transaction. A fixture proves deterministic app behavior, not live provider access.

## Validate this documentation package

From repository root, use a Python environment with the dependency below:

```bash
python3 -m pip install -r docs/design/brandme/contracts/requirements.txt
python3 docs/design/brandme/contracts/validate_spec.py
```

The validator checks local Markdown links and source references, unique requirement IDs, valid requirement metadata, JSON Schema definitions, positive/negative examples, shared axis/room/token consistency and fixture arithmetic. It does not run the application or verify external network capabilities. Application tests, benchmarks and real provider evidence are deliverables of the subsequent build.
