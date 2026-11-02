# brandme_core/domains/social

Relationships, blind yes/no decisions with a deadline, shares, notifications and reports (ch.01 §social, ch.03 §4).
Reserved by the opus-foundation lane; implemented by the consumer-domains lane. Stage log:
`docs/build/status/opus-consumer-domains.md`.

- **Migration:** `brandme-data/spanner/migrations/V004_social.sql`.
- **Modules:** `api.py` (router), `relationships.py`, `decisions.py` (the Now loop), `shares.py`,
  `notifications.py`, `reports.py`, `policy.py` (visibility and blocking policy), `clock.py` (deadline clock),
  `events.py`, `deletion.py` (My Data handler).
- **Tests:** `tests/test_social_*.py`.
- **Note:** rooms, in-window comment threads and the share projector are in PR #66, not yet on `main`.

Foundation contract every domain follows: commands through `run_command` / `run_idempotent_command` with rows and
events in one transaction; `authorize` deny-by-default; events registered with closed schemas; data categories
registered for export and idempotent delete; API shapes generated from `packages/contracts`.
