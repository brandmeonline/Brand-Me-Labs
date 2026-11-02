# brandme_core/domains/providers

Catalog, payment and fulfillment providers behind the commerce domain (ch.05). Reserved by the opus-foundation lane;
implemented by the commerce-agents lane. Stage log: `docs/build/status/opus-commerce-agents.md`.

- **Migration:** `brandme-data/spanner/migrations/V006_providers.sql`.
- **Modules:** `registry.py` and `setup.py` (provider registration and composition), `contracts.py`, `tiers.py`
  (partner tiers), `catalog.py`, `ingestion.py`, `merchant.py`, `local_atelier.py` and `nordstrom.py` (catalog
  sources), `payments/simulated.py`, `payments/stripe_test.py` and `payments/stripe_wire.py` (Stripe test mode over
  a loopback-recorded wire; no live run), `fulfillment/simulated.py`, `url_guard.py`, `redaction.py` (card-number
  and processor-text redaction used by logs and events).
- **Tests:** `tests/test_providers_*.py`.
- **Status:** simulated and Stripe test-mode rails are exercised by the suite; no provider has been run against a
  live account. Stripe Connect (brands flow) is parked in PR #71.

Foundation contract every domain follows: commands through `run_command` / `run_idempotent_command` with rows and
events in one transaction; `authorize` deny-by-default; events registered with closed schemas; data categories
registered for export and idempotent delete; API shapes generated from `packages/contracts`.
