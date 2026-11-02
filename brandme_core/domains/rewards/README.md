# brandme_core/domains/rewards

Points ledger, badges, benefits and operator-defined reward rules (ch.03 §4). Reserved by the opus-foundation lane;
implemented by the consumer-domains lane. Stage log: `docs/build/status/opus-consumer-domains.md`.

- **Migration:** `brandme-data/spanner/migrations/V005_rewards.sql`.
- **Modules:** `api.py` (router), `service.py`, `ledger.py` (append-only points ledger), `rules.py`, `badges.py`,
  `benefits.py`, `consumer.py` (event consumer that awards points), `operators.py`, `events.py`, `deletion.py`
  (My Data handler).
- **Tests:** `tests/test_rewards_*.py`.
- **Note:** loyalty standing, surveys and in-app credit are in PR #66, not yet on `main`.

Foundation contract every domain follows: commands through `run_command` / `run_idempotent_command` with rows and
events in one transaction; `authorize` deny-by-default; events registered with closed schemas; data categories
registered for export and idempotent delete; API shapes generated from `packages/contracts`.
