# brandme-infra

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Deployment assets for Brand.Me on Google Kubernetes Engine (GKE).

**Status (2026-10-23): nothing here has been deployed.** The target cluster
(`brandme-cluster`, `us-east1`, project `lux-realestate-app` per
`.github/workflows/ci-cd.yml:36-39`) is unconfirmed, no GCP credentials were
available to verify it, and the CI `Deploy to GKE` job has never run (no `v*`
tag exists). What works today is offline validation. The ordered founder
actions, verified facts and gaps are in
[`docs/build/deploy/gke-verification-packet.md`](../docs/build/deploy/gke-verification-packet.md).

ADR-06 (`docs/design/brandme/07-repository-audit-sources.md:70`) makes Cloud
Run the initial cloud target and keeps GKE as an option; this directory
prepares the GKE option at the founder's request.

## Layout

| Path | State |
|---|---|
| [`helm/brandme/`](helm/brandme/README.md) | **Current.** Chart for the processes that boot in strict mode: gateway, chain, console, read API, privacy exports API and worker, outbox worker, plus a pre-install/pre-upgrade migration Job. Workload Identity per workload, digest-pinned images, hardened pods, default-deny NetworkPolicy, optional GKE Ingress (off). |
| [`helm/brandme-umbrella/`](helm/brandme-umbrella/LEGACY.md) | **Legacy, non-functional.** Its subcharts and `values/values-prod.yaml` do not exist. Kept until the founder retires it. |
| `terraform/main.tf` | **Legacy, non-functional.** `terraform validate` fails (`var.db_password` is used at `main.tf:192` but never declared). It provisions Cloud SQL, which current code does not use, and none of Spanner, Pub/Sub, Secret Manager or per-workload identities. The packet's `gcloud` steps replace it for the first sandbox. |

## Validate the chart

```bash
bash scripts/validate-helm.sh
# optional env-contract stage (rendered env -> each core process's own validator):
BRANDME_PYTHON=.venv/bin/python bash scripts/validate-helm.sh
```

The script downloads helm 3.22.1 and kubeconform 0.8.0 into `.cache/tools`,
verifying SHA-256 checksums pinned from the official release checksum files,
then lints, renders, validates against Kubernetes 1.35 and 1.36 schemas
(GKE Regular channel) and runs negative rendering tests. CI:
`.github/workflows/deploy-validate.yml` ("Deploy manifests").

## Deploy (not yet possible)

Deployment is gated on the founder actions in the packet, section C. The
proposed CI deploy job (deploy by digest, Workload Identity Federation, GitHub
Environment `sandbox`, `BM_DEPLOY_ENABLED` guard, migrations before rollout) is
in section E; it is not applied to `ci-cd.yml` yet. A manual equivalent, once
every `REPLACE_ME` in `values-sandbox.yaml` is filled:

```bash
helm upgrade --install brandme brandme-infra/helm/brandme \
  --namespace brandme \
  --values brandme-infra/helm/brandme/values-sandbox.yaml \
  --set-string images.registry=gcr.io/<project> \
  --set-string images.core.digest=sha256:<...> \
  --set-string images.gateway.digest=sha256:<...> \
  --set-string images.chain.digest=sha256:<...> \
  --set-string images.console.digest=sha256:<...> \
  --wait --wait-for-jobs --timeout 15m
```

## Secrets

The chart never contains secret values. Each credential lives in Google
Secret Manager as `brandme-<mode>-<lane>-<purpose>` (for example
`brandme-sandbox-rts-chain-service-token`) and is synced into a Kubernetes
Secret of the same name (key `value`) by the GKE secret sync add-on or
External Secrets Operator. Pods read them only through `secretKeyRef`. The old
instructions here (`oauth-secrets`, `jwt-secret`, wallet key files) are
obsolete: the gateway refuses `JWT_SECRET` in strict modes, and no wallet key
belongs in the cluster.
