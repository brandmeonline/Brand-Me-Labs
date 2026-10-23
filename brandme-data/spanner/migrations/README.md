# Spanner migrations

GoogleSQL only, applied by `runner.py` with a checksum ledger (`SchemaMigrations`).

```bash
pnpm migrate                      # = python brandme-data/spanner/migrations/runner.py up --create-database --wait 60
python brandme-data/spanner/migrations/runner.py status   # applied / pending / drift
python brandme-data/spanner/migrations/runner.py verify   # exit 1 on drift or pending
```

| Rule | Behaviour |
|---|---|
| Naming | `V<NNN>_<name>.sql`; duplicates and other names are rejected |
| Reservations | V001 foundation (identity + platform) · V002 persona · V003 wardrobe · V004 social · V005 rewards · V006 providers · V007 commerce · V008 rights · V009 privacy |
| Checksums | SHA-256 of the file; editing an applied migration is refused (write a new one) |
| Partial failure | Spanner DDL is not transactional. A failed batch leaves an `applying` row; later runs stop until an operator inspects and runs `repair --version N` |
| Ordering | A pending version lower than an applied one is refused (`--allow-out-of-order` is local-only, refused in sandbox/production) |
| Startup | Services call `assert_schema_supported(database, minimum, maximum)` and refuse an unsupported schema range |
| `--create-database` | Emulator only |

The legacy `../schema.sql` is **not** applied by the runner. It contains PostgreSQL syntax that GoogleSQL rejects (see `docs/build/evidence/w00/baseline-test-report.md`). Lanes that need legacy tables port them into their reserved migration with valid GoogleSQL. V001 has been verified on an empty database and on top of the partially-applied legacy schema.

V010 adds an independent projection revision to `RightsEntitlements` for transactional outbox events. Apply it before deploying the integrated rights projection; V008 and V009 remain unchanged. Existing rows receive revision 1 on their next verified update.

V011 adds the authenticated owner/environment and observation timestamp to `ChainOperations`, replaces global idempotency with a member/network/contract/environment index, and adds transactional subject locks. Apply before configuring durable chain status/reconciliation. Old rows remain unowned and are excluded; do not assign them to a member or regenerate their digest without reviewing the original request and any broadcast evidence. Existing migrations are unchanged.

V012 adds reconciliation leases, attempt counters and projection-completion markers to `ChainOperations`. Apply before deploying the background worker and updated rights privacy handler. Existing owned operations are due immediately; legacy unowned operations stay excluded. This migration does not enable any network writes.

V013 adds the environment-scoped outbox dispatch index. Apply before starting the Pub/Sub worker. No event payload or delivery status is rewritten. Stop older dispatchers before rolling out the new unique-lease-token and claim-time attempt semantics. Pub/Sub topics, subscriptions, workload IAM and consumers must be provisioned separately; see `brandme_core/events/README.md`.

V014 adds the separate selected-category privacy export queue, member-scoped idempotency records and recurring object cleanup ledger. Apply before deploying `brandme_core.privacy_exports`. The legacy synchronous `ExportJobs` remains unchanged. Provision an isolated private export bucket and API/worker identities separately; see `brandme_core/privacy_exports/README.md`. This migration neither enables account deletion nor completes full-account export coverage.
