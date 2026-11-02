# brandme-agents (legacy Python services and the agentic CLI)

**Copyright (c) Brand.Me, Inc. All rights reserved.**

| Directory | Port | Status (`CLAUDE.md`) | Notes |
|---|---|---|---|
| `identity/` | 8005 | **PARTIAL** | FastAPI (`src/main.py`); initialisation is real and a `ZKProofManager` from `brandme_core.zk` is wired, but proofs use stubs or the `allow_stub_fallback` path |
| `knowledge/` | 8003 | **STUB** | FastAPI (`src/main.py`); Spanner pool initialisation only |
| `compliance/` | 8004 | **STUB** | FastAPI (`src/main.py`); hash-chained audit-log writes are real, ESG scores fall back to a hash stub (`src/lifecycle/esg_verifier.py`) |
| `branding/` | — | not wired | not in any compose file |
| `agentic/` | — | CLI only | see [`agentic/README.md`](./agentic/README.md) |

The three services run only under `docker-compose.yml --profile legacy`, each after
`python -m brandme_core.config preflight --service <name>`, which refuses sandbox and production. Ports are the
compose ports above (the 8100–8103 numbering found in archived documents belonged to the previous platform).

Dependencies: `requirements.txt` here and per service; the hashed lock for the Python tree is
`scripts/python/requirements.lock`. Tests live in the repository's `tests/` suite.
