# LEGACY — do not deploy this chart

`brandme-umbrella` is non-functional and superseded by
[`../brandme`](../brandme/README.md). It is kept, not deleted, until the
founder decides on retiring the legacy deploy paths
(`docs/build/deploy/gke-verification-packet.md`, section F).

Evidence (helm v3.22.1, checksum-verified, run 2026-10-23):

- `helm template brandme ./brandme-umbrella` fails: `found in Chart.yaml, but
  missing in charts/ directory: brandme-gateway, brandme-core, brandme-agents,
  brandme-chain, brandme-console`. `Chart.yaml:10-34` points at
  `file://../charts/*`, and `brandme-infra/helm/charts/` does not exist.
- `--values values/values-prod.yaml`, which the old `Deploy to GKE` job used
  before 2026-10-24, fails: `open values/values-prod.yaml: no such file or
  directory`. The deploy job now uses `brandme-infra/helm/brandme` instead.
- `helm lint ./brandme-umbrella` still exits 0 with only a WARNING, so lint
  alone never caught this. The new chart is gated by `helm template | kubeconform`
  in `scripts/validate-helm.sh`.
- `values.yaml` names a registry and images CI never pushes
  (`gcr.io/brandme-prod` at `:9`, `brandme-core-brain`/`-policy`/`-orchestrator`
  and `brandme-agent-*` at `:101-159`), moves the gateway to port 3000
  (`:56`, `:73-74`) while its image exposes and health-checks 3001
  (`brandme-gateway/Dockerfile:20-21`), sets no `BRANDME_MODE` (the gateway
  config requires it), and injects `JWT_SECRET`/`OAUTH_*` (`:75-89`), which the
  gateway refuses in sandbox/production (`brandme-gateway/src/middleware/mode.ts:45`).
