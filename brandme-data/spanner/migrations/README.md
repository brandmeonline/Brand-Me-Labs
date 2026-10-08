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
