# brandme_core/domains/rights

Rights entitlements, passports and licensed reprint as projected from the Midnight rights contract (ch.04).
Reserved by the opus-foundation lane; implemented by the midnight-rights lane. Stage log:
`docs/build/status/opus-midnight-rights.md`; chain side in `brandme-chain/`.

- **Migrations:** `brandme-data/spanner/migrations/V008_rights.sql`, `V010_rights_projection_version.sql`.
- **Modules:** `projection.py` (finalized-only entitlement projection with its own revision), `passport.py`
  (claim-level passport read model), `reprint.py` (reprint workflow and manufacturer callbacks), `privacy_handler.py`
  (My Data handler).
- **Reads:** served by `brandme_core/read_api/` behind the gateway; see its README.
- **Tests:** `tests/test_rights*.py` and the chain suites in `brandme-chain/tests/`.
- **Note:** the authenticated rights command backend (`brandme_core.rights_commands`) is in PR #70, not yet on `main`.

Foundation contract every domain follows: commands through `run_command` / `run_idempotent_command` with rows and
events in one transaction; `authorize` deny-by-default; events registered with closed schemas; data categories
registered for export and idempotent delete; API shapes generated from `packages/contracts`.
