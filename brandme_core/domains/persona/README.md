# brandme_core/domains/persona

The member's editable identity (declared, inferred and evidence facets), onboarding and recommendations (ch.03 §4),
and the process that serves every consumer domain. Reserved by the opus-foundation lane; implemented by the
consumer-domains lane. Stage log: `docs/build/status/opus-consumer-domains.md`.

- **Migration:** `brandme-data/spanner/migrations/V002_persona.sql`.
- **Process:** `app.py` is the FastAPI application of the `consumer-domains` service (port 8010; compose service
  `consumer-domains`, `docker-compose.yml`). The gateway forwards the consumer routers to it with ES256 principal
  assertions, verified in `assertion.py`; `http.py` holds the HTTP plumbing.
- **Modules:** `api.py` (router), `service.py`, `model.py`, `kernel.py`, `onboarding.py`, `recommender.py`,
  `backfill.py`, `events.py`, `deletion.py` (My Data handler), `privacy_guard.py`.
- **Workers:** `ingress.py` (lane ingress consuming outbox events from Pub/Sub), `jobs.py` (scheduled jobs such as
  reward settlement), `lane.py`. Outbox delivery is foundation's `brandme_core.events.worker`, which loads this
  lane's catalog; the lane's own outbox worker is gone (Ultra plan 03, item 9). Composition evidence for the chain
  `events.worker → Pub/Sub → ingress → jobs`: `docs/audits/2026-11-01/claude-opus-02/evidence/runtime/emulator-run.md`.
- **Tests:** `tests/test_persona_*.py`.

Foundation contract every domain follows: commands through `run_command` / `run_idempotent_command` with rows and
events in one transaction; `authorize` deny-by-default; events registered with closed schemas; data categories
registered for export and idempotent delete; API shapes generated from `packages/contracts`.
