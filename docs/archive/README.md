# Archive — superseded documentation

Files here are kept unchanged for history. Each set is dated by the work it describes and names what replaced it.
Nothing in this directory describes the current tree; for that, read [`CLAUDE.md`](../../CLAUDE.md),
[`docs/build/implementation-status.md`](../build/implementation-status.md) and the
[design package](../design/brandme/README.md).

Convention: one dated subfolder per retired set (`YYYY-MM-<topic>/`), files moved with `git mv` so their history
follows them, and a row below for each file. Never name a subfolder `build/` (the root `.gitignore` ignores it).

## 2025-01-enterprise-session/ — the January 2025 "enterprise transformation" session

PostgreSQL/Celery platform, "v7 Stable Integrity Spine", 90% readiness claims. Replaced by `CLAUDE.md` and the
build record.

| File | What it was | Replaced by |
|---|---|---|
| `STATUS_UPDATE_2025_01_27.md`, `PROGRESS_REPORT_2025_01_27.md`, `SESSION_SUMMARY_2025_01_27.md`, `COMPLETE_SESSION_REPORT.md` | Session trackers and reports | `docs/build/status/*.md` |
| `COMPLETE_STATUS.md`, `ENTERPRISE_ASSESSMENT.md` | "Complete status report" (90%) and the pre-transformation assessment | `CLAUDE.md`; `docs/audits/2026-11-01/` |
| `DEPLOYMENT_READY_CHECKLIST.md` | Deployment checklist for the umbrella chart | `docs/build/deploy/gke-verification-packet.md` |
| `OBSERVABILITY_PHASE_4.md`, `PHASE_4_OBSERVABILITY_COMPLETE.md`, `OBSERVABILITY.md` | Phase-4 observability tracker, completion report and write-up | packet section G12 (workers have no health endpoint yet); `brandme_core/events/README.md` |
| `ROADMAP.md` | Execution roadmap, "90% enterprise-ready" | `docs/build/orchestration/next-plans-20261025.md`, `pipeline-state.md` |

## 2025-10-legacy-platform/ — documents of the previous platform (PostgreSQL, umbrella chart, ports 8100–8103)

| File | What it was | Replaced by |
|---|---|---|
| `PROJECT_STATUS.md` (2025-10-25), `CURRENT_STATUS.md` ("v8", 95%) | Platform status reports | `CLAUDE.md`; `docs/build/implementation-status.md` |
| `DEPLOYMENT.md`, `DEPLOYMENT_GUIDE.md`, `QUICK_START.md` | One-click deployment via `deploy-brandme.sh` (inoperable: it sources files that do not exist), Postgres/umbrella-chart guide, quick start | `docs/build/local-setup.md`; `docs/build/deploy/gke-verification-packet.md`; `brandme-infra/README.md` |
| `INFRASTRUCTURE.md` | Celery/Prometheus/Loki/Alembic infrastructure guide | `brandme-infra/helm/brandme/README.md`; the packet |
| `SYSTEM_ARCHITECTURE.md` (v8/v9, merged twice), `AGENTIC_ARCHITECTURE.md` (LangGraph/MCP target) | Architecture specifications | `docs/design/brandme/03-architecture-data-api.md`, `05-commerce-agents-connectors.md` |

`docs/architecture/OVERVIEW.md` was deleted on 2026-11-02: its two tables were verbatim copies of the root README's.

## 2025-10-cube-integration/ — the Product Cube integration session (26–27 Oct 2025)

Six session artifacts plus the executive summary; "READY FOR DEPLOYMENT" with "Runtime testing: 0%" in the same
file. The cube service remains a stub behind the `legacy` compose profile.

| File | What it was | Replaced by |
|---|---|---|
| `FINAL_SUMMARY.md` ("95% Enterprise-Ready") | Session summary | `CLAUDE.md` |
| `PRODUCT_CUBE_SUMMARY.md` | Executive summary; honest that startup was untested | `CLAUDE.md` cube row; `docs/build/evidence/w00/baseline-test-report.md` |
| `CUBE_ACTION_PLAN.md`, `CUBE_DEPLOYMENT_READINESS.md`, `CUBE_SERVICE_INTEGRATION.md`, `CUBE_STATUS_REPORT.md`, `PRODUCT_CUBE_QUICKSTART.md` | Plan, checklist, integration guide, status report, quick start | `brandme-cube/README.md` |

## 2026-04-plan/ — the April 2026 plans

| File | What it was | Replaced by |
|---|---|---|
| `PLAN.md` | End-to-end + ACP/AP2/A2A phase plan; self-marked "Historical plan — superseded" | `docs/design/brandme/README.md` (product scope); `docs/build/orchestration/` (sequencing) |
| `REGRESSION_EXECUTION_PLAN.md` | Regression loop plan | `scripts/regression/README.md`; `.github/workflows/module-regression.yml` |

## 2026-08-lux-foundation-audit/ — the August 2026 audit and lift-and-shift plan (PR #29)

See the folder's own README. The audit documents are history; the `brandme_foundation/` code they proposed was
never imported by any service and is preserved only at its commit.

## 2026-10-orchestration-history/ — completed orchestration records

| File | What it was | Replaced by |
|---|---|---|
| `merge-log-20261023.md` | Merge train of 2026-10-23 | `docs/build/orchestration/pipeline-state.md` |
| `next-consumer-domains-pr52.md` | Completed assignment (merge `main` into PR #52) | — (done) |
| `oneshot-plan-03-opus-foundation.md` | Lane assignment whose exit was reached by PR #62 | `docs/build/status/opus-foundation.md` |
