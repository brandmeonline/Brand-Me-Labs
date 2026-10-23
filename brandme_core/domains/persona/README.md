# brandme_core/domains/persona (reserved)

Reserved by the opus-foundation lane. The framework provides **no logic** here.

- **Owning lane:** consumer-domains
- **Migration number:** V002 (`brandme-data/spanner/migrations/`)
- **Entities (ch.03 §4):** PersonaProfile, PersonaEvidence, PersonaSnapshot, BodyProfile; backfill of the two legacy Users persona columns

Contract for the owning lane:
- Commands go through `brandme_core.domains.run_command` / `run_idempotent_command`. Domain rows and events commit in one transaction. Callbacks have no external side effects.
- Every object read/write calls `brandme_core.domains.authorize`, which is deny-by-default; unauthorized private reads raise `NotFound`.
- Event types are registered with an exact closed payload schema (`brandme_core.domains.events.register`). Payloads carry references, not personal data.
- Personal data categories are registered with `register_data_category` (export + idempotent delete) when the domain is introduced.
- API shapes are added to `packages/contracts` (`scripts/endpoints.mjs`, schemas) and regenerated. Never hand-edit `generated/`.
