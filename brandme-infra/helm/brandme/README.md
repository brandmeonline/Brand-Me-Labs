# brandme Helm chart

Kubernetes manifests for the Brand.Me processes that can boot in a strict
mode (`BRANDME_MODE=sandbox` or `production`) today. **Validated offline only;
nothing has been deployed with this chart.** The cluster, the GCP resources and
the credentials it needs are founder actions, listed in order in
[`docs/build/deploy/gke-verification-packet.md`](../../../docs/build/deploy/gke-verification-packet.md).

> ADR-06 (`docs/design/brandme/07-repository-audit-sources.md:70`) makes Cloud
> Run the initial cloud target and keeps GKE as an option. This chart prepares
> the GKE option because the founder asked for it; the packet records the tension.

## Workloads

| Component | Image | Command | Port / probe | Google identity (sandbox) |
|---|---|---|---|---|
| gateway | `brandme-gateway` | `node dist/index.js` | 3001 `GET /healthz` | `bm-sbx-fnd-gateway` |
| chain | `brandme-chain` | `node dist/src/index.js` | 3001 `GET /health` | `bm-sbx-rts-chain` |
| console | `brandme-console` | `node brandme-console/server.js` | 3002 `GET /` | none |
| read-api | `brandme-core` (`runtime` stage) | `python -m brandme_core.read_api` | 8000 `GET /health` (readiness), TCP (liveness) | `bm-sbx-rts-read-api` |
| exports-api | `brandme-core` | `python -m brandme_core.privacy_exports` | 8000 `GET /health`, TCP | `bm-sbx-rts-export-api` |
| exports-worker | `brandme-core` | `python -m brandme_core.privacy_exports --worker` | none (exits non-zero on failed startup checks) | `bm-sbx-rts-export-wkr` |
| events-worker | `brandme-core` | `python -m brandme_core.events.worker` | none (same) | `bm-sbx-fnd-outbox` |
| events-retention (CronJob, hourly at :17 UTC) | `brandme-core` | `python -m brandme_core.events.retention --once` | none (exits non-zero on a failed pass) | `bm-sbx-fnd-outbox` (own KSA; needs its own Workload Identity binding) |
| migrations (hook Job) | `brandme-core` | `python brandme-data/spanner/migrations/runner.py up` | — | `bm-sbx-fnd-migrator` |

The legacy brain, policy, orchestrator, knowledge, compliance, identity and cube
services are deliberately absent: they refuse strict modes
(`python -m brandme_core.config preflight`, exit 3). The chart runs no
`preflight` init container: the shared inventory allows these processes in
sandbox (packet G13), but an init container would also need `ENVIRONMENT` and
each service's network variable. The read API, export API/worker and outbox
worker run the same guard in-process at start (`brandme_core/boot.py`), so a
production pod on a Midnight test network exits 3 regardless; the chart also
refuses to render that combination (`templates/validate.yaml`).

## Guarantees enforced at render time

- `mode` must be `sandbox` or `production`; `BRANDME_MODE` and `ENVIRONMENT`
  are both set from it on every process.
- Every environment-specific value is required. Any value containing
  `REPLACE_ME` fails the render, so `values-sandbox.yaml` cannot ship half-filled.
- Images need a `sha256:` digest (preferred) or an immutable tag; `latest` is refused.
- Midnight `mainnet`, export buckets outside `brandme-<mode>-exports-`, topics
  outside `brandme-<mode>-`, and non-https public origins are refused.
- Secrets reach pods only through `secretKeyRef` to Kubernetes Secrets named in
  `secretRefs`. The chart renders no Secret and contains no secret value. Those
  Secrets are synced from Secret Manager (GKE secret sync add-on or External
  Secrets Operator; packet step C-15).
- Every pod: own ServiceAccount (with a Workload Identity annotation, except
  the console's, which calls no Google API), non-root numeric UID,
  `RuntimeDefault` seccomp, no privilege escalation, all capabilities dropped,
  read-only root filesystem with an `emptyDir` `/tmp`, requests and limits.
  Every Deployment also gets a PodDisruptionBudget (`maxUnavailable: 1`); the
  migrations Job and the events-retention CronJob do not.
- `eventsRetention.schedule` must be hourly at a fixed minute (the outbox
  retention and erasure sweep assume a pass every hour; `concurrencyPolicy: Forbid`).
- Default-deny NetworkPolicy for the namespace plus explicit allows
  (load balancer → gateway/console only when ingress is on; gateway → chain,
  read-api, exports-api; DNS; GKE metadata server; HTTPS egress outside private ranges).
- Migrations run as a `pre-install,pre-upgrade` hook Job before any workload
  changes; a failed migration stops the release.
- The optional GKE Ingress (static IP, ManagedCertificate, BackendConfig health
  checks, HTTPS redirect) is disabled by default.

## Validate

```bash
bash scripts/validate-helm.sh          # add BRANDME_PYTHON=.venv/bin/python for the env contract stage
```

It downloads checksum-pinned helm 3.22.1 and kubeconform 0.8.0, lints, renders
`ci/test-values.yaml` (fake values, CI only) and the filled-in sandbox values
for Kubernetes 1.35 and 1.36 (GKE Regular channel), validates with
`kubeconform -strict` (pinned schemas, GKE CRDs included), checks hardening
invariants, and asserts that unsafe or incomplete values fail to render.
CI runs it in `.github/workflows/deploy-validate.yml`.

## Files

- `values.yaml` — safe defaults; everything real is empty and required.
- `values-sandbox.yaml` — first deploy target (`BRANDME_MODE=sandbox`), naming
  from the packet, `REPLACE_ME` for founder decisions.
- `ci/test-values.yaml` — fake values for CI rendering only. Never deploy it.
