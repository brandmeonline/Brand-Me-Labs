# Regression Execution Plan (Module Loop)

Last updated: 2026-04-27

## Objective

Drive the repository toward a clean and connected baseline by using the module regression suite as the control loop.

## Loop

1. Run `REGRESSION_TIMEOUT=900 bash scripts/regression/run_all.sh`.
2. Capture failures from terminal output and `scripts/regression/.last-run-report.md`.
3. Fix the highest-leverage module first (shared/core before downstream).
4. Re-run full suite.
5. Repeat until all modules pass.

## Prioritized remediation order

1. `brandme_core` (shared Python layer used broadly)
2. `brandme_agents`
3. `brandme_cube`
4. `brandme_gateway`
5. `brandme_chain`
6. `brandme_frontend`
7. remaining modules

## Done criteria

- Every module script under `scripts/regression/modules/` returns success.
- `scripts/regression/.last-run-report.md` shows `Failed (0)`.
- CI workflow `Module Regression` passes on push.

## Current execution status (2026-04-27)

✅ Done criteria met locally.

### Fixes completed in this pass

- Restored valid Python implementations for corrupted files in:
  - `brandme-core/orchestrator/main.py`
  - `brandme_core/mcp/tools.py`
  - `brandme_core/zk/proof_of_ownership.py`
  - `brandme-cube/src/main.py`
  - `brandme-cube/src/service.py`
  - `brandme-agents/compliance/src/lifecycle/burn_proof.py`
  - `brandme-agents/compliance/src/lifecycle/esg_verifier.py`
- Fixed gateway type issues and stabilized strict limiter behavior.
- Added a gateway unit test so the gateway test phase is no longer empty.
- Added `brandme-chain/src/services/cardano-wallet.ts` shim to satisfy startup/type imports.
- Fixed frontend type mismatches in demo-model contracts and request-id helper implementation.

## Notes

The suite intentionally reports real failures rather than masking them. Keep this behavior to prevent silent regressions.
