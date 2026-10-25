#!/usr/bin/env bash
# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Offline validation of brandme-infra/helm/brandme. Needs no cluster and no
# cloud credentials; proves nothing about a live deployment.
#
#   bash scripts/validate-helm.sh
#
# 1. Downloads pinned helm and kubeconform release archives into .cache/tools
#    and verifies each against a SHA-256 copied from the project's official
#    release checksum file (re-verified on every run, cache or not).
# 2. helm lint --strict with ci/test-values.yaml (fake values, CI only).
# 3. helm template | kubeconform -strict for each Kubernetes version below,
#    plus structural assertions (digest-pinned images, hardened containers,
#    no inline secret values).
# 4. Renders values-sandbox.yaml the way the deploy job does (placeholders
#    filled with fakes, digests via --set-string) and validates it.
# 5. Negative tests: rendering MUST fail on missing required values, on the
#    committed values-sandbox.yaml (REPLACE_ME), and on unsafe values.
# 6. If BRANDME_PYTHON points at a Python with scripts/python/requirements.lock
#    installed: feeds the rendered env of every core-image process to that
#    process's own strict-mode config validator.
# Exits non-zero on the first failure.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CHART="$ROOT/brandme-infra/helm/brandme"
TOOLS="${BRANDME_TOOLS_DIR:-$ROOT/.cache/tools}"

HELM_VERSION=3.22.1
KUBECONFORM_VERSION=0.8.0
# GKE Regular channel (docs.cloud.google.com/kubernetes-engine/docs/release-schedule,
# read 2026-10-23, page updated 2026-10-22): 1.35 is the current auto-upgrade
# target (since 2026-04-28); 1.36 is available and auto-upgrades from 2026-11.
# Validate against both so the next automatic upgrade cannot surprise us.
KUBE_VERSIONS=(1.35.0 1.36.0)
# Schemas pinned to commits (git refs/heads at 2026-10-23), not a moving branch.
K8S_SCHEMAS="https://raw.githubusercontent.com/yannh/kubernetes-json-schema/f7d855e49c34b039c9ef2196444910275e31e09e/{{.NormalizedKubernetesVersion}}-standalone{{.StrictSuffix}}/{{.ResourceKind}}{{.KindSuffix}}.json"
# GKE CRDs rendered when ingress.enabled: BackendConfig, ManagedCertificate, FrontendConfig.
CRD_SCHEMAS="https://raw.githubusercontent.com/datreeio/CRDs-catalog/501527ab9c40c827144c8f45945b25a023e344ce/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"

log() { printf '==> %s\n' "$*"; }
die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
  Linux) os=linux ;;
  Darwin) os=darwin ;;
  *) die "unsupported OS $(uname -s)" ;;
esac
case "$(uname -m)" in
  x86_64 | amd64) arch=amd64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) die "unsupported architecture $(uname -m)" ;;
esac
platform="$os-$arch"

# From https://get.helm.sh/helm-v3.22.1-<platform>.tar.gz.sha256sum
helm_sha256() {
  case "$1" in
    linux-amd64) echo 896cf63684a42a723d61c980369d6e588330927deb13676ca0d85006dd6da0ea ;;
    linux-arm64) echo 4c29e286b279d170fa048ddfc3e4e83dcd069ca9c52102766ba672d7149e694d ;;
    darwin-amd64) echo cf850a81b908f8eef0331e6b18776da2767bcac639ca84472311dad20008495c ;;
    darwin-arm64) echo e73da8a0b0d5193774fdff17ce6319c7436bb22ee229b45fd64f3c40368c753a ;;
  esac
}
# From https://github.com/yannh/kubeconform/releases/download/v0.8.0/CHECKSUMS
kubeconform_sha256() {
  case "$1" in
    linux-amd64) echo 9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883 ;;
    linux-arm64) echo 1f53fc8e81258197a35e8603054162a5af1de8c5af13746c71ab680d9534ed87 ;;
    darwin-amd64) echo 71dbc87ac9f24099a62b93570e65aa06312ba6ac8aea63b7f86e9d999edf5a92 ;;
    darwin-arm64) echo f84f4dfbebf4a6b0b230385fa065a39ea35e02608c2b50d025dcf64775a69d67 ;;
  esac
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}

# fetch <url> <file name> <expected sha256>: cached archive, verified every run.
fetch() {
  local url=$1 file="$TOOLS/downloads/$2" want=$3 got
  [ -n "$want" ] || die "no pinned checksum for $2 on $platform"
  mkdir -p "$TOOLS/downloads"
  if [ ! -f "$file" ]; then
    curl -fsSL --retry 3 --proto '=https' --tlsv1.2 -o "$file.part" "$url"
    mv "$file.part" "$file"
  fi
  got=$(sha256_of "$file")
  if [ "$got" != "$want" ]; then
    rm -f "$file"
    die "checksum mismatch for $2: expected $want, got $got"
  fi
}

install_tools() {
  local bin="$TOOLS/bin" tmp
  mkdir -p "$bin"
  tmp=$(mktemp -d)
  fetch "https://get.helm.sh/helm-v$HELM_VERSION-$platform.tar.gz" \
    "helm-v$HELM_VERSION-$platform.tar.gz" "$(helm_sha256 "$platform")"
  tar -xzf "$TOOLS/downloads/helm-v$HELM_VERSION-$platform.tar.gz" -C "$tmp" "$platform/helm"
  install -m 0755 "$tmp/$platform/helm" "$bin/helm"
  fetch "https://github.com/yannh/kubeconform/releases/download/v$KUBECONFORM_VERSION/kubeconform-$platform.tar.gz" \
    "kubeconform-v$KUBECONFORM_VERSION-$platform.tar.gz" "$(kubeconform_sha256 "$platform")"
  tar -xzf "$TOOLS/downloads/kubeconform-v$KUBECONFORM_VERSION-$platform.tar.gz" -C "$tmp" kubeconform
  install -m 0755 "$tmp/kubeconform" "$bin/kubeconform"
  rm -rf "$tmp"
  HELM="$bin/helm"
  KUBECONFORM="$bin/kubeconform"
  "$HELM" version --template '{{.Version}}' | grep -qx "v$HELM_VERSION" || die "unexpected helm version"
  "$KUBECONFORM" -v | grep -qx "v$KUBECONFORM_VERSION" || die "unexpected kubeconform version"
  log "tools verified: helm v$HELM_VERSION, kubeconform v$KUBECONFORM_VERSION ($platform)"
}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

render() { # render <kube version> <output file> [helm args...]
  local kv=$1 out=$2
  shift 2
  "$HELM" template brandme "$CHART" --namespace brandme --kube-version "$kv" "$@" >"$out"
}

conform() { # conform <kube version> <rendered file>
  mkdir -p "$TOOLS/kubeconform-cache"
  "$KUBECONFORM" -strict -summary -kubernetes-version "$1" \
    -schema-location "$K8S_SCHEMAS" -schema-location "$CRD_SCHEMAS" \
    -cache "$TOOLS/kubeconform-cache" "$2"
}

count() { grep -cE "$1" "$2" || true; }

# Structural assertions kubeconform cannot express.
assert_hardened() { # assert_hardened <rendered file> <expected Deployments...>
  local f=$1 name
  shift
  for name in "$@"; do
    grep -qx "  name: $name" "$f" || die "$f: expected resource $name was not rendered"
  done
  local pods images
  pods=$(count '^kind: (Deployment|Job|CronJob)$' "$f")
  images=$(count '^ +image: ' "$f")
  [ "$pods" -gt 0 ] || die "$f: no workloads rendered"
  [ "$images" -eq "$pods" ] || die "$f: expected one container per pod ($images images, $pods pods)"
  [ "$(count '^ +image: "[^"]+@sha256:[a-f0-9]{64}"$' "$f")" -eq "$images" ] || die "$f: an image is not pinned by digest"
  [ "$(count '^ +readOnlyRootFilesystem: true$' "$f")" -eq "$images" ] || die "$f: a container has a writable root filesystem"
  [ "$(count '^ +allowPrivilegeEscalation: false$' "$f")" -eq "$images" ] || die "$f: privilege escalation not disabled everywhere"
  [ "$(count '^ +drop: \["ALL"\]$' "$f")" -eq "$images" ] || die "$f: capabilities not dropped everywhere"
  [ "$(count '^ +runAsNonRoot: true$' "$f")" -eq "$pods" ] || die "$f: a pod may run as root"
  [ "$(count '^ +type: RuntimeDefault$' "$f")" -eq "$pods" ] || die "$f: a pod lacks the RuntimeDefault seccomp profile"
  [ "$(count '^kind: Secret$' "$f")" -eq 0 ] || die "$f: the chart must never render a Secret"
  if grep -A1 -E '^ +- name: [A-Z_]*(TOKEN|SECRET|BLOCKFROST_PROJECT_ID)$' "$f" | grep -qE '^ +value:'; then
    die "$f: a credential env var has an inline value (must use secretKeyRef)"
  fi
  [ "$(count '^kind: PodDisruptionBudget$' "$f")" -eq "$(count '^kind: Deployment$' "$f")" ] || die "$f: every Deployment needs a PDB"
  grep -q 'name: brandme-default-deny' "$f" || die "$f: default-deny NetworkPolicy missing"
}

# expect_failure <description> <expected error substring> [helm args...]
expect_failure() {
  local what=$1 want=$2 err="$WORK/neg.err"
  shift 2
  if "$HELM" template brandme "$CHART" --namespace brandme --kube-version "${KUBE_VERSIONS[0]}" "$@" >/dev/null 2>"$err"; then
    die "negative test passed unexpectedly: $what"
  fi
  grep -qF -- "$want" "$err" || { cat "$err" >&2; die "negative test failed for the wrong reason: $what (wanted: $want)"; }
  log "refused as expected: $what"
}

install_tools

CI_VALUES="$CHART/ci/test-values.yaml"
ALL_DEPLOYMENTS=(brandme-gateway brandme-chain brandme-console brandme-read-api brandme-exports-api brandme-exports-worker brandme-events-worker brandme-events-retention brandme-migrations)

log "helm lint --strict (ci/test-values.yaml)"
"$HELM" lint --strict "$CHART" --namespace brandme --kube-version "${KUBE_VERSIONS[0]}" -f "$CI_VALUES"

for kv in "${KUBE_VERSIONS[@]}"; do
  log "render ci/test-values.yaml for Kubernetes $kv"
  render "$kv" "$WORK/ci-$kv.yaml" -f "$CI_VALUES"
  conform "$kv" "$WORK/ci-$kv.yaml"
  assert_hardened "$WORK/ci-$kv.yaml" "${ALL_DEPLOYMENTS[@]}"
done

# values-sandbox.yaml exactly as the deploy job uses it: registry and digests
# via --set-string, every REPLACE_ME supplied by an overlay (fake values here).
cat >"$WORK/sandbox-filled.yaml" <<'YAML'
gcp: {projectId: ci-fake-project}
midnight: {contractAddress: "0000000000000000000000000000000000000000000000000000000000000000"}
gateway:
  oidc: {issuer: "https://issuer.example.invalid", audience: ci-fake-audience}
  publicOrigins: ["https://app.example.invalid"]
privacyExports: {bucket: brandme-sandbox-exports-ci-fake}
YAML
DIGESTS=(--set-string images.registry=registry.invalid/ci-fake-project)
for image in core gateway chain console; do
  DIGESTS+=(--set-string "images.$image.digest=sha256:$(printf '%064d' 0)")
done
for kv in "${KUBE_VERSIONS[@]}"; do
  log "render values-sandbox.yaml (placeholders filled) for Kubernetes $kv"
  render "$kv" "$WORK/sandbox-$kv.yaml" -f "$CHART/values-sandbox.yaml" -f "$WORK/sandbox-filled.yaml" "${DIGESTS[@]}"
  conform "$kv" "$WORK/sandbox-$kv.yaml"
  assert_hardened "$WORK/sandbox-$kv.yaml" brandme-gateway brandme-chain brandme-read-api brandme-exports-api \
    brandme-exports-worker brandme-events-worker brandme-events-retention brandme-migrations
  modes=$(count '^ +- name: (BRANDME_MODE|ENVIRONMENT)$' "$WORK/sandbox-$kv.yaml")
  sandbox=$(grep -A1 -E '^ +- name: (BRANDME_MODE|ENVIRONMENT)$' "$WORK/sandbox-$kv.yaml" | grep -cE '^ +value: "sandbox"$' || true)
  [ "$modes" -gt 0 ] && [ "$modes" -eq "$sandbox" ] || die "values-sandbox.yaml must render BRANDME_MODE=ENVIRONMENT=sandbox everywhere"
done

log "negative tests (rendering must fail)"
expect_failure "chart defaults without values" "mode is required"
expect_failure "any REPLACE_ME placeholder" "values still contain REPLACE_ME placeholders" \
  -f "$CI_VALUES" --set gateway.oidc.audience=REPLACE_ME_TEST
if grep -vE '^[[:space:]]*#' "$CHART/values-sandbox.yaml" | grep -q REPLACE_ME; then
  expect_failure "committed values-sandbox.yaml (unfilled REPLACE_ME)" "values still contain REPLACE_ME placeholders" \
    -f "$CHART/values-sandbox.yaml" "${DIGESTS[@]}"
else
  # Every placeholder has been filled in-repo: the committed file must render.
  log "values-sandbox.yaml has no REPLACE_ME left: rendering it as committed"
  render "${KUBE_VERSIONS[0]}" "$WORK/sandbox-committed.yaml" -f "$CHART/values-sandbox.yaml" "${DIGESTS[@]}"
  conform "${KUBE_VERSIONS[0]}" "$WORK/sandbox-committed.yaml"
fi
expect_failure "values-sandbox.yaml without image digests" "images.registry is required" \
  -f "$CHART/values-sandbox.yaml" -f "$WORK/sandbox-filled.yaml"
expect_failure "development mode" "mode must be sandbox or production" -f "$CI_VALUES" --set mode=development
expect_failure "image tag latest" "is refused" -f "$CI_VALUES" --set images.core.digest= --set images.core.tag=latest
expect_failure "malformed digest" "digest must be sha256" -f "$CI_VALUES" --set images.gateway.digest=sha256:abc
expect_failure "Midnight mainnet" "mainnet is not authorized" -f "$CI_VALUES" --set midnight.network=mainnet
expect_failure "export bucket outside brandme-<mode>-exports-" "must start with brandme-sandbox-exports-" \
  -f "$CI_VALUES" --set privacyExports.bucket=brandme-exports
expect_failure "plain-http public origin" "must be https" -f "$CI_VALUES" --set 'gateway.publicOrigins={http://localhost:3000}'
expect_failure "plaintext JWKS URI" "jwksUri must be https" -f "$CI_VALUES" --set gateway.oidc.jwksUri=http://idp.example.invalid/jwks
expect_failure "plain-http CORS origin" "corsOrigins entry" -f "$CI_VALUES" --set 'gateway.corsOrigins={http://evil.example.invalid}'
expect_failure "ingress without gateway.trustProxy" "ingress.enabled requires gateway.trustProxy" -f "$CI_VALUES" --set-string gateway.trustProxy=
expect_failure "missing Secret name" "secretRefs.chainServiceToken.name is required" \
  -f "$CI_VALUES" --set secretRefs.chainServiceToken.name=
expect_failure "missing Workload Identity GSA" "readApi.gcpServiceAccount is required" -f "$CI_VALUES" --set readApi.gcpServiceAccount=
expect_failure "topic outside brandme-<mode>-" "must start with brandme-sandbox-" -f "$CI_VALUES" --set eventsWorker.topics.public=outbox-public
expect_failure "events-retention without a Workload Identity GSA" "eventsRetention.gcpServiceAccount is required" \
  -f "$CI_VALUES" --set eventsRetention.gcpServiceAccount=
expect_failure "events-retention daily" "must be hourly at a fixed minute" -f "$CI_VALUES" --set-string 'eventsRetention.schedule=17 3 * * *'
expect_failure "events-retention without a schedule" "eventsRetention.schedule is required" -f "$CI_VALUES" --set-string 'eventsRetention.schedule='
expect_failure "events-retention every minute" "must be hourly at a fixed minute" -f "$CI_VALUES" --set-string 'eventsRetention.schedule=* * * * *'
expect_failure "production with Midnight test-network workloads" "mode=production with chain/read-api/exports enabled is refused" -f "$CI_VALUES" --set mode=production
expect_failure "production values with sandbox resources" "must start with brandme-production-" -f "$CI_VALUES" --set mode=production --set chain.enabled=false --set readApi.enabled=false --set exportsApi.enabled=false --set exportsWorker.enabled=false

if [ -n "${BRANDME_PYTHON:-}" ]; then
  log "env contract: rendered env -> each core process's own strict-mode validator ($BRANDME_PYTHON)"
  (cd "$ROOT" && PYTHONPATH="$ROOT" "$BRANDME_PYTHON" - "$WORK/ci-${KUBE_VERSIONS[0]}.yaml" <<'PY'
import sys

import google.auth
import yaml

from brandme_core.config import enforce_boot_guard
from brandme_core.events import pubsub
from brandme_core.events.retention import RetentionConfig
from brandme_core.events.worker import WorkerConfig
from brandme_core.privacy_exports.config import ExportConfig
from brandme_core.read_api.config import ReadConfig


class AdcReached(Exception):
    """Raised instead of looking up credentials: validation already passed."""


def no_adc(*_args, **_kwargs):
    raise AdcReached()


google.auth.default = no_adc

docs = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d]
pods = {d["metadata"]["name"]: d["spec"]["template"]["spec"] for d in docs if d["kind"] in ("Deployment", "Job")}
pods.update({d["metadata"]["name"]: d["spec"]["jobTemplate"]["spec"]["template"]["spec"] for d in docs if d["kind"] == "CronJob"})
secret_values = {}


def env_of(name):
    env = {}
    for item in pods[name]["containers"][0]["env"]:
        if "value" in item:
            env[item["name"]] = item["value"]
        else:
            ref = item["valueFrom"]["secretKeyRef"]
            # Distinct fake credential per Secret, valid for the token regex.
            env[item["name"]] = secret_values.setdefault(ref["name"], f"fake-{len(secret_values):02d}-" + "x" * 32)
    return env


checked = []
for name, validate in (
    ("brandme-read-api", ReadConfig.from_env),
    ("brandme-exports-api", ExportConfig.from_env),
    ("brandme-exports-worker", ExportConfig.from_env),
):
    cfg = validate(env_of(name))
    assert cfg.environment == "sandbox", name
    checked.append(name)

worker = WorkerConfig.from_env(env_of("brandme-events-worker"))
try:
    pubsub.PubSubPublisher(worker.topics, worker.environment)
except AdcReached:
    checked.append("brandme-events-worker")
else:
    raise SystemExit("PubSubPublisher did not reach credential lookup")

retention_pod = pods["brandme-events-retention"]
assert retention_pod["containers"][0]["command"] == ["python", "-m", "brandme_core.events.retention", "--once"]
assert retention_pod["restartPolicy"] == "Never" and retention_pod["serviceAccountName"] == "brandme-events-retention"
retention_env = env_of("brandme-events-retention")
assert RetentionConfig.from_env(retention_env).environment == "sandbox"
assert enforce_boot_guard("events_retention", env=retention_env).value == "sandbox"
checked.append("brandme-events-retention")

mig = env_of("brandme-migrations")
assert mig["BRANDME_MODE"] == mig["ENVIRONMENT"] == "sandbox" and all(
    mig.get(k) for k in ("SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID")), mig
checked.append("brandme-migrations")
print("env contract OK:", ", ".join(checked))
PY
  )
else
  log "skipped env contract check (set BRANDME_PYTHON to a Python with scripts/python/requirements.lock)"
fi

log "all chart validations passed"
