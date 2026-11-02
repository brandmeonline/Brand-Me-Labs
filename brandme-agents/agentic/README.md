# brandme-agents/agentic (CLI)

**Copyright (c) Brand.Me, Inc. All rights reserved.**

A command-line tool, not a service: `cli/main.py` drives the agent orchestration in `orchestrator/` with the
tools in `tools/`. Status per `CLAUDE.md`: **CLI only**; nothing in `docker-compose.yml` or the Helm chart runs it.

- `graph_db.py` and `graph_rag.py`: the Neo4j/GraphRAG layer is disabled and builds no client
  (`docs/build/security/trivy-triage-2026-10-25.md`); there is no Neo4j in this repository.
- Dependencies: `requirements.txt` (trimmed in `docs/build/deviations.md` D-008); `setup.py` packages the CLI.
- The assistant planner that the product actually uses lives in `brandme_core/orchestrator` and
  `brandme_core/domains/commerce` (see that README's "Assistant planner" section), not here.

The former architecture write-up for this package is archived at
`docs/archive/2025-10-legacy-platform/AGENTIC_ARCHITECTURE.md` and describes a target that was not built.
