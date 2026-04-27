# Module Regression Scripts

This directory provides a **module-by-module pass/fail regression suite** for the monorepo.

## Goals

- Keep checks deterministic and non-interactive for local runs and CI.
- Enforce per-step time limits to prevent stuck runs.
- Surface real failures per module so fixes can be tracked over time.

## Run locally

```bash
REGRESSION_TIMEOUT=900 bash scripts/regression/run_all.sh
```

- `REGRESSION_TIMEOUT` applies to each individual step via `timeout`.
- A Markdown report is generated at `scripts/regression/.last-run-report.md`.
- The script exits non-zero if any module fails.

## Structure

- `lib.sh` — shared helpers (`require_cmd`, `run_step`).
- `run_all.sh` — orchestrates module scripts and writes a report.
- `modules/*.sh` — one script per major module.

## Module checks

- `root_shared` — repo-level sanity and shell syntax checks.
- `brandme_core` — Python compile checks for core services/shared package.
- `brandme_cube` — Python compile checks.
- `brandme_governance` — Python compile checks.
- `brandme_agents` — Python compile checks.
- `brandme_gateway` — TypeScript type-check and tests.
- `brandme_gateway` tests inject minimal auth env vars in-process so Vitest can load config non-interactively.
- `brandme_chain` — TypeScript type-check and tests.
- `brandme_frontend` — TypeScript compile check.
- `brandme_console` — TypeScript type-check.
- `brandme_data` — schema presence and SQL-file smoke checks.
- `brandme_infra` — infra manifest presence and shell syntax checks.

## CI

The workflow `.github/workflows/module-regression.yml` runs this suite on every push and pull request.

## Practical loop after each run

1. Run `run_all.sh`.
2. Read `.last-run-report.md` and failing module logs.
3. Fix one failing module at a time.
4. Re-run until no failures remain.


## Current baseline

After the latest fix loop (2026-04-27), `run_all.sh` completes with all modules passing locally.
