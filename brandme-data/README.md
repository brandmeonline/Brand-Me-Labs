# brandme-data

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Database definitions. The only live part is the Spanner migration set.

## Spanner migrations (`spanner/migrations/`)

GoogleSQL migrations `V001_identity.sql` … `V015_commerce_quote_terms.sql`, applied by `runner.py` with a
checksum ledger. Rules, reservations per lane and the behaviour on partial failure are in
[`spanner/migrations/README.md`](./spanner/migrations/README.md); `tests/foundation/test_migrations.py` enforces
contiguity and the reservation table.

```bash
pnpm migrate                                                   # = runner.py up --create-database --wait 60 (emulator)
python brandme-data/spanner/migrations/runner.py status        # applied / pending / drift
python brandme-data/spanner/migrations/runner.py verify        # exit 1 on drift or pending
```

In containers the `spanner-migrate` service of `docker-compose.yml` runs the same `up`.

## Legacy files (not applied by anything)

- `spanner/schema.sql`: PostgreSQL-syntax schema that GoogleSQL rejects; the runner ignores it
  (`docs/build/evidence/w00/baseline-test-report.md`).
- `schemas/001_users.sql` … `007_audit_log.sql`, `schemas/cube_service.sql` and `seeds/*.sql`: PostgreSQL-era
  definitions kept for reference. Nothing applies them; the regression harness only checks that `schemas/` exists,
  and the legacy cube database module names them in a comment.

Seeding for development happens through the domain commands and `pnpm smoke`, not through these SQL files.
