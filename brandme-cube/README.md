# brandme-cube (legacy Product Cube service)

**Copyright (c) Brand.Me, Inc. All rights reserved.**

FastAPI service for the seven-facet Product Cube (port **8007**, entry `src/main.py`, `uvicorn src.main:app`).
Status per `CLAUDE.md`: **STUB / UNVERIFIED**. The routes import and the policy gates are real, but startup has
never been verified, `tests/test_api.py` holds only a placeholder and `tests/test_service.py` one mocked unit test,
and there is no authentication on the endpoints.

It runs only under `docker-compose.yml --profile legacy`, after `python -m brandme_core.config preflight --service
cube`, which refuses sandbox and production. `src/database/` is a thin CRUD layer whose `schema.py` is a placeholder
("can be used for SQLAlchemy models if needed later"); the PostgreSQL-era instructions in the archived cube
documents (`docs/archive/2025-10-cube-integration/`) no longer apply and no PostgreSQL exists in this repository.

Design of record for the cube's facets and visibility: `docs/design/brandme/04-midnight-ownership-lifecycle.md`
and `brandme_core/domains/rights/` (passport read model); the legacy facet filter is `src/passport_filter.py`.
