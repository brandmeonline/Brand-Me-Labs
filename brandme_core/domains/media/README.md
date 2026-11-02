# brandme_core/domains/media

Media assets, upload quarantine, derivatives and try-on job records (ch.03 §4). Reserved by the opus-foundation lane;
implemented by the consumer-domains and spatial-ar lanes. Stage logs: `docs/build/status/opus-consumer-domains.md`,
`docs/build/status/astra-spatial-ar.md`.

- **Migration:** no file of its own; `MediaObjects`, `TryOnJobs` and `TryOnConsents` are created by V003 (wardrobe).
- **Modules:** `api.py` (router), `service.py`, `store.py`, `gcs_store.py` (object storage; the local GCS emulator in
  development), `providers.py`, `events.py` (registered event schemas), `deletion.py` (My Data handler).
- **Tests:** `tests/test_media_*.py`.

Foundation contract every domain follows:
- Commands go through `brandme_core.domains.run_command` / `run_idempotent_command`; domain rows and events commit in
  one transaction; callbacks have no external side effects.
- Every object read/write calls `brandme_core.domains.authorize`, deny-by-default; unauthorized private reads raise
  `NotFound`.
- Event types are registered with an exact closed payload schema (`brandme_core.domains.events.register`); payloads
  carry references, not personal data.
- Personal data categories are registered with `register_data_category` (export + idempotent delete).
- API shapes are added to `packages/contracts` and regenerated; `generated/` is never hand-edited.
