# brandme-core (legacy Python services)

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Three FastAPI services from the original scan-and-provenance platform. They share the `brandme_core` library
(repository root) and Spanner; there is no PostgreSQL, Redis or Celery runtime in this repository.

| Service | Port | Status (`CLAUDE.md`) | What it does |
|---|---|---|---|
| `brain/` | 8000 | **REAL** | `POST /intent/resolve`: real Spanner asset lookup, then policy and orchestrator calls; `/health`, `/metrics` |
| `policy/` | 8001 | **REAL** | `/policy/check`, `/policy/canViewFace`, `/policy/canTransferOwnership`, provenance reads and `/verify`; consent graph in Spanner; region rules from `policies/region/{default,eu-west1,us-east1}.yaml` (`policy/region_rules.py`) |
| `orchestrator/` | 8002 | **STUB** | returns a fabricated `cardano_tx_*` hash (`orchestrator/main.py:92`); `celery_app.py`, `tasks.py` and `worker.py` are the never-wired Celery shape |

## Run

`docker-compose.yml` starts `brain` and `policy` in the default profile and `orchestrator` only with
`--profile legacy`; each runs `python -m brandme_core.config preflight --service <name>` first, and preflight
refuses the stub services in sandbox and production. Natively, `pnpm dev:demo` from the repository root starts
brain with the gateway and consumer app.

```bash
cd brandme-core/brain && uvicorn main:app --port 8000     # with SPANNER_EMULATOR_HOST set, see docs/build/local-setup.md
cd brandme-core/policy && uvicorn main:app --port 8001
```

Dependencies per service are in each `requirements.txt`; the hashed lock for the whole Python tree is
`scripts/python/requirements.lock`. Tests live in the repository's `tests/` suite (run by `pnpm check` and CI's
Test Core job with emulators); there is no `brandme-core/tests/`.

## What is not here

Cardano anchoring, Midnight proofs and ESG verification do not happen in these services; see `CLAUDE.md` for the
exact break boundaries and `brandme-chain/` for the real Midnight adapter.
