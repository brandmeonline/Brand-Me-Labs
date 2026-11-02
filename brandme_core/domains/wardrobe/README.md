# brandme_core/domains/wardrobe

Wardrobe items, outfits, rooms and closet placement (ch.01 §closet, ch.03 §4). Reserved by the opus-foundation lane;
implemented by the consumer-domains lane with the spatial-ar lane for rooms and placement. Stage logs:
`docs/build/status/opus-consumer-domains.md`, `docs/build/status/astra-spatial-ar.md`.

- **Migration:** `brandme-data/spanner/migrations/V003_wardrobe.sql` (also creates the media tables).
- **Modules:** `api.py` (router, mounted by the gateway's `wardrobeRouter`), `service.py`, `model.py`, `outfits.py`,
  `rooms.py`, `placement.py`, `guest_sections.py`, `events.py`, `deletion.py` (My Data handler).
- **Tests:** `tests/test_wardrobe_*.py` (the legacy `tests/test_wardrobe.py` is quarantined in `tests/conftest.py`).
- **Gap:** the browser's wardrobe is still guest-local; the member-aware server repository and guest migration are
  audit work package WP-04 (`docs/audits/2026-11-01/claude-opus-02/RECONCILIATION.md`).

Foundation contract every domain follows: commands through `run_command` / `run_idempotent_command` with rows and
events in one transaction; `authorize` deny-by-default; events registered with closed schemas; data categories
registered for export and idempotent delete; API shapes generated from `packages/contracts`.
