#!/usr/bin/env bash
# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Per-lane sandbox service identities for Brand.Me on GCP.
# Design and role rationale: docs/build/security/lane-service-accounts.md
# Naming: docs/build/security/secrets-conventions.md
#
# DRY RUN BY DEFAULT: prints every gcloud command and changes nothing. With
# --apply it runs them. It never creates a service-account key, never writes a
# secret value (secret containers are created empty; values are added by an
# operator with `gcloud secrets versions add`, see
# docs/build/runbooks/credential-rotation.md) and never creates the data plane
# or the cluster. With --apply it first checks that the Spanner database, the
# three outbox topics, the buckets and the registry exist, and stops before any
# change if one does not (the GKE cluster itself is not checked).
#
#   scripts/provision/gcp-dev-identities.sh                     # dry run with placeholders
#   scripts/provision/gcp-dev-identities.sh --project my-sandbox-project
#   scripts/provision/gcp-dev-identities.sh --project my-sandbox-project --apply
#
# Options
#   --project ID               GCP project (required with --apply)
#   --project-number N         project number (looked up with --apply when omitted)
#   --mode sandbox             only sandbox is provisioned. production is refused
#                              (separate reviewed change); development is refused
#                              because it runs on emulators only.
#   --spanner-instance ID      default brandme-<mode> (values-sandbox.yaml, packet C-8)
#   --spanner-database ID      default brandme-<mode>
#   --export-bucket NAME       default brandme-sandbox-exports-SUFFIX (placeholder)
#   --ar-repo NAME             Artifact Registry repository, default gcr.io
#   --ar-location LOC          default us (the gcr.io-domain repository CI pushes to)
#   --ar-project ID            project that hosts that repository, default --project.
#                              CI pushes to gcr.io/lux-realestate-app today; pass it
#                              here if the sandbox project is a different one
#   --namespace NS             Kubernetes namespace, default brandme
#   --release NAME             helm release; KSA = <release>-<component>, default brandme
#   --github-repo OWNER/NAME   default brandmeonline/Brand-Me-Labs
#   --github-repo-id N         numeric repository id (required with --apply): the
#                              name alone is mutable (rename/transfer), the id is not
#   --allow-ref REF            ref the deploy job's tokens may come from; repeatable;
#                              a trailing * means prefix. Default refs/tags/v*
#   --require-environment ENV  GitHub Environment the deploy job runs in, default sandbox
#   --wif-pool ID              deploy pool, default github-deploy
#   --wif-provider ID          deploy provider, default brandme-deploy
#   --push-wif-pool ID         image-push pool, default github-push (separate pool, so
#                              a push token can never act as the deployer or vice versa)
#   --with-projector           also create the Firestore projector identity
#   --projector-subscription S Pub/Sub subscription the projector reads
#   --firestore-database ID    default (default)
#   --dom-media-bucket NAME    grant the consumer-domains API its media bucket
#   --include-planned          also create the planned commerce signing-key
#                              container and grant the gateway access to it
#   --enforce-no-sa-keys       enforce org policy iam.disableServiceAccountKeyCreation
#   --i-understand-shared-project
#                              allow --apply on a project id containing "prod" or
#                              "lux-realestate"
#   --apply                    run the commands (default: print only)
#   --yes                      skip the confirmation prompt with --apply
#   -h, --help
set -euo pipefail

die() { printf 'gcp-dev-identities: %s\n' "$*" >&2; exit 2; }
usage() { sed -n '2,/^set -euo pipefail$/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'; }

# ---- options -----------------------------------------------------------------
project=""
project_number=""
mode="sandbox"
spanner_instance=""
spanner_database=""
export_bucket=""
ar_repo="gcr.io"
ar_location="us"
ar_project=""
namespace="brandme"
release="brandme"
github_repo="brandmeonline/Brand-Me-Labs"
github_repo_id=""
allow_refs=()
require_environment=""
wif_pool="github-deploy"
wif_provider="brandme-deploy"
push_wif_pool="github-push"
push_wif_provider="brandme-push"
with_projector=0
projector_subscription=""
firestore_database="(default)"
dom_media_bucket=""
include_planned=0
enforce_no_sa_keys=0
shared_ok=0
apply=0
assume_yes=0

need() {
  if [ "$#" -lt 2 ] || [ -z "$2" ]; then die "$1 needs a value"; fi
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project) need "$@"; project="$2"; shift 2 ;;
    --project-number) need "$@"; project_number="$2"; shift 2 ;;
    --mode) need "$@"; mode="$2"; shift 2 ;;
    --spanner-instance) need "$@"; spanner_instance="$2"; shift 2 ;;
    --spanner-database) need "$@"; spanner_database="$2"; shift 2 ;;
    --export-bucket) need "$@"; export_bucket="$2"; shift 2 ;;
    --ar-repo) need "$@"; ar_repo="$2"; shift 2 ;;
    --ar-location) need "$@"; ar_location="$2"; shift 2 ;;
    --ar-project) need "$@"; ar_project="$2"; shift 2 ;;
    --namespace) need "$@"; namespace="$2"; shift 2 ;;
    --release) need "$@"; release="$2"; shift 2 ;;
    --github-repo) need "$@"; github_repo="$2"; shift 2 ;;
    --github-repo-id) need "$@"; github_repo_id="$2"; shift 2 ;;
    --allow-ref) need "$@"; allow_refs+=("$2"); shift 2 ;;
    --require-environment) need "$@"; require_environment="$2"; shift 2 ;;
    --wif-pool) need "$@"; wif_pool="$2"; shift 2 ;;
    --wif-provider) need "$@"; wif_provider="$2"; shift 2 ;;
    --push-wif-pool) need "$@"; push_wif_pool="$2"; shift 2 ;;
    --with-projector) with_projector=1; shift ;;
    --projector-subscription) need "$@"; projector_subscription="$2"; shift 2 ;;
    --firestore-database) need "$@"; firestore_database="$2"; shift 2 ;;
    --dom-media-bucket) need "$@"; dom_media_bucket="$2"; shift 2 ;;
    --include-planned) include_planned=1; shift ;;
    --enforce-no-sa-keys) enforce_no_sa_keys=1; shift ;;
    --i-understand-shared-project) shared_ok=1; shift ;;
    --apply) apply=1; shift ;;
    --yes) assume_yes=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done
# The deploy job runs on v* tags under environment: sandbox (ci-cd.yml deploy).
[ "${#allow_refs[@]}" -gt 0 ] || allow_refs=("refs/tags/v*")
[ -n "$require_environment" ] || require_environment="sandbox"

# ---- refusals ----------------------------------------------------------------
case "$mode" in
  sandbox) env3="sbx" ;;
  production) die "refusing --mode production: production identities need their own reviewed change and project; this script only provisions sandbox" ;;
  development) die "refusing --mode development: development runs on emulators only (read API, export API and outbox worker refuse real Spanner outside sandbox/production), so it needs no cloud identities" ;;
  *) die "unknown --mode '$mode' (sandbox is the only supported value)" ;;
esac

if [ "$apply" -eq 1 ]; then
  [ -n "$project" ] || die "--apply requires --project explicitly"
  lower_project="$(printf '%s' "$project" | tr '[:upper:]' '[:lower:]')"
  case "$lower_project" in
    *prod*|*lux-realestate*)
      [ "$shared_ok" -eq 1 ] || die "refusing --apply on project '$project': the id contains 'prod' or 'lux-realestate'. Use a dedicated sandbox project, or pass --i-understand-shared-project after reading docs/build/security/lane-service-accounts.md" ;;
  esac
  [ "$with_projector" -eq 0 ] || [ -n "$projector_subscription" ] || die "--with-projector needs --projector-subscription"
  [ -n "$export_bucket" ] || die "--apply needs --export-bucket brandme-sandbox-exports-<suffix>"
  [ -n "$github_repo_id" ] || die "--apply needs --github-repo-id (gh api repos/OWNER/NAME --jq .id): trust is pinned to the immutable id"
fi
[ -n "$spanner_instance" ] || spanner_instance="brandme-${mode}"
[ -n "$spanner_database" ] || spanner_database="brandme-${mode}"

if [ -n "$project" ]; then
  [[ "$project" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || die "invalid project id '$project'"
  case "$project" in
    *prod*|*lux-realestate*) printf '# WARNING: project %s looks shared or production; --apply will refuse it without --i-understand-shared-project\n' "$project" ;;
  esac
fi
[ -n "$project" ] || project="PROJECT_ID"
[ -n "$ar_project" ] || ar_project="$project"
[ -n "$export_bucket" ] || export_bucket="brandme-${mode}-exports-SUFFIX"
[[ "$export_bucket" == "brandme-${mode}-exports-"* ]] || die "export bucket must start with brandme-${mode}-exports- (brandme_core/privacy_exports/config.py:39)"
if [ "$apply" -eq 1 ]; then
  [[ "$export_bucket" =~ ^[a-z][a-z0-9-]{1,61}[a-z0-9]$ ]] || die "invalid export bucket name '$export_bucket'"
  # Never block on an interactive gcloud prompt.
  export CLOUDSDK_CORE_DISABLE_PROMPTS=1
fi
[ -z "$github_repo_id" ] || [[ "$github_repo_id" =~ ^[0-9]+$ ]] || die "--github-repo-id must be numeric"
[ -n "$github_repo_id" ] || github_repo_id="REPO_ID"
[[ "$github_repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die "--github-repo must be owner/name"

# ---- command runner ----------------------------------------------------------
quote_arg() {
  if [[ "$1" =~ ^[A-Za-z0-9_./:=@,+%-]+$ ]]; then
    printf '%s' "$1"
  else
    printf "'%s'" "${1//\'/\'\\\'\'}"
  fi
}
show() {
  local out="+" a
  for a in "$@"; do out+=" $(quote_arg "$a")"; done
  printf '%s\n' "$out"
}
guard() {
  # Defence in depth: this script must never mint or upload a key.
  local joined=" $* "
  case "$joined" in
    *" keys create "*|*" keys upload "*|*" hmac create "*) die "refusing to run a key-creating command: $*" ;;
  esac
}
run() {
  guard "$@"
  show "$@"
  if [ "$apply" -eq 1 ]; then "$@"; fi
}
# ensure DESCRIBE... -- CREATE...: create only when DESCRIBE fails.
ensure() {
  local describe=() create=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do describe+=("$1"); shift; done
  [ "$#" -gt 0 ] || die "ensure: missing --"
  shift
  create=("$@")
  guard "${create[@]}"
  printf '# if absent (checked with: %s)\n' "$(show "${describe[@]}" | cut -c3-)"
  show "${create[@]}"
  if [ "$apply" -eq 1 ]; then
    if "${describe[@]}" >/dev/null 2>&1; then
      printf '  exists; left unchanged\n'
    else
      "${create[@]}"
    fi
  fi
}
# require DESCRIBE... : a prerequisite this script never creates.
require() {
  printf '# prerequisite (must already exist): %s\n' "$(show "$@" | cut -c3-)"
  if [ "$apply" -eq 1 ] && ! "$@" >/dev/null 2>&1; then
    die "prerequisite missing: $* — create it first (docs/build/security/lane-service-accounts.md, Prerequisites)"
  fi
}
section() { printf '\n## %s\n' "$*"; }

gsa_email() { printf '%s@%s.iam.gserviceaccount.com' "$1" "$project"; }
ksa_member() { printf 'serviceAccount:%s.svc.id.goog[%s/%s-%s]' "$project" "$namespace" "$release" "$1"; }

# ---- plan --------------------------------------------------------------------
printf '# Brand.Me %s identities for project %s (%s)\n' "$mode" "$project" "$([ "$apply" -eq 1 ] && echo APPLY || echo 'DRY RUN: nothing is executed')"
printf '# No service-account keys are created. No secret values are written.\n'

if [ "$apply" -eq 1 ]; then
  command -v gcloud >/dev/null 2>&1 || die "gcloud not found"
  active_account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1)"
  [ -n "$active_account" ] || die "no active gcloud account (gcloud auth login)"
  gcloud projects describe "$project" --format='value(projectId)' >/dev/null || die "cannot read project $project"
  if [ -z "$project_number" ]; then
    project_number="$(gcloud projects describe "$project" --format='value(projectNumber)')"
  fi
  printf '# active account: %s, project number: %s\n' "$active_account" "$project_number"
  if [ "$assume_yes" -ne 1 ]; then
    [ -t 0 ] || die "--apply without --yes needs an interactive terminal"
    printf 'Type the project id (%s) to apply: ' "$project"
    read -r typed
    [ "$typed" = "$project" ] || die "confirmation did not match; nothing applied"
  fi
fi
[ -n "$project_number" ] || project_number="PROJECT_NUMBER"
[[ "$project_number" =~ ^([0-9]+|PROJECT_NUMBER)$ ]] || die "invalid project number '$project_number'"

prefix="bm-${env3}"
database_path="projects/${project}/instances/${spanner_instance}/databases/${spanner_database}"
topics=("brandme-${mode}-public" "brandme-${mode}-member-private" "brandme-${mode}-restricted")
role_spanner_rw="projects/${project}/roles/brandmeSpannerDataReadWrite"
role_outbox="projects/${project}/roles/brandmeOutboxPublisher"
role_export_read="projects/${project}/roles/brandmeExportObjectReader"
role_export_write="projects/${project}/roles/brandmeExportObjectWriter"

section "Prerequisites (created elsewhere, never by this script; checked before any change)"
require gcloud spanner databases describe "$spanner_database" --instance "$spanner_instance" --project "$project"
for t in "${topics[@]}"; do require gcloud pubsub topics describe "$t" --project "$project"; done
require gcloud storage buckets describe "gs://${export_bucket}" --project "$project"
require gcloud artifacts repositories describe "$ar_repo" --location "$ar_location" --project "$ar_project"
[ "$with_projector" -eq 0 ] || require gcloud pubsub subscriptions describe "${projector_subscription:-SUBSCRIPTION}" --project "$project"
[ -z "$dom_media_bucket" ] || require gcloud storage buckets describe "gs://${dom_media_bucket}" --project "$project"

section "APIs"
run gcloud services enable iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  secretmanager.googleapis.com spanner.googleapis.com pubsub.googleapis.com storage.googleapis.com \
  artifactregistry.googleapis.com container.googleapis.com cloudresourcemanager.googleapis.com \
  --project "$project"

if [ "$enforce_no_sa_keys" -eq 1 ]; then
  section "Org policy: no service-account keys in this project"
  run gcloud resource-manager org-policies enable-enforce iam.disableServiceAccountKeyCreation --project "$project"
fi

section "Custom roles (least privilege)"
# databaseUser minus updateDdl, adapt, changequorum and operation control
# (permission list: docs.cloud.google.com/iam/docs/roles-permissions/spanner).
spanner_rw_perms="spanner.databases.beginOrRollbackReadWriteTransaction,spanner.databases.beginPartitionedDmlTransaction,spanner.databases.beginReadOnlyTransaction,spanner.databases.get,spanner.databases.getDdl,spanner.databases.partitionQuery,spanner.databases.partitionRead,spanner.databases.read,spanner.databases.select,spanner.databases.write,spanner.sessions.create,spanner.sessions.delete,spanner.sessions.get,spanner.sessions.list"
custom_role() {
  local id="$1" title="$2" perms="$3"
  ensure gcloud iam roles describe "$id" --project "$project" -- \
    gcloud iam roles create "$id" --project "$project" --title "$title" --permissions "$perms" --stage GA
  run gcloud iam roles update "$id" --project "$project" --permissions "$perms"
}
custom_role brandmeSpannerDataReadWrite "Brand.Me Spanner data read/write (no DDL)" "$spanner_rw_perms"
custom_role brandmeOutboxPublisher "Brand.Me outbox publisher (publish + get)" "pubsub.topics.publish,pubsub.topics.get"
custom_role brandmeExportObjectReader "Brand.Me export bucket reader" "storage.buckets.get,storage.objects.get"
custom_role brandmeExportObjectWriter "Brand.Me export bucket writer" "storage.buckets.get,storage.objects.get,storage.objects.create,storage.objects.delete"

section "Service accounts (no keys)"
# key|purpose|ksa component ("-" = none)
identities=(
  "fnd-deployer|CI deployer (helm, tag + sandbox Environment only) via GitHub WIF|-"
  "fnd-pusher|CI image push (main and v* tags) via GitHub WIF|-"
  "fnd-migrator|Spanner schema migrations (helm pre-upgrade Job)|migrations"
  "fnd-outbox|Outbox to Pub/Sub dispatcher|events-worker"
  "fnd-retention|Outbox retention and erasure (CronJob)|events-retention"
  "fnd-gateway|API gateway|gateway"
  "rts-chain|Midnight chain service|chain"
  "rts-read-api|Rights and privacy read API (read-only)|read-api"
  "rts-export-api|Privacy export API|exports-api"
  "rts-export-wkr|Privacy export worker|exports-worker"
  "com-domain|Commerce domain service|commerce-domain"
  "dom-api|Consumer domains API|consumer-domains-api"
)
[ "$with_projector" -eq 0 ] || identities+=("fnd-projector|Firestore projection writer|projector")

for spec in "${identities[@]}"; do
  IFS='|' read -r key purpose component <<<"$spec"
  id="${prefix}-${key}"
  [ "${#id}" -le 30 ] || die "service account id too long: $id"
  [[ "$id" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || die "invalid service account id: $id"
  ensure gcloud iam service-accounts describe "$(gsa_email "$id")" --project "$project" -- \
    gcloud iam service-accounts create "$id" --project "$project" \
      --display-name "Brand.Me ${mode} ${key}" --description "$purpose. Keyless: Workload Identity only."
  if [ "$component" != "-" ]; then
    run gcloud iam service-accounts add-iam-policy-binding "$(gsa_email "$id")" --project "$project" \
      --role roles/iam.workloadIdentityUser --member "$(ksa_member "$component")"
  fi
done

section "Spanner (database ${spanner_database} only)"
spanner_bind() {
  run gcloud spanner databases add-iam-policy-binding "$spanner_database" --instance "$spanner_instance" \
    --project "$project" --member "serviceAccount:$(gsa_email "${prefix}-$1")" --role "$2"
}
spanner_bind fnd-migrator roles/spanner.databaseUser   # DDL + migration ledger; no drop/IAM
spanner_bind rts-read-api roles/spanner.databaseReader
# fnd-retention: this role only (its partitioned-DML purge needs beginPartitionedDmlTransaction); no Pub/Sub.
for key in fnd-outbox fnd-retention fnd-gateway rts-chain rts-export-api rts-export-wkr com-domain dom-api; do
  spanner_bind "$key" "$role_spanner_rw"
done

section "Pub/Sub (the three outbox topics only)"
for t in "${topics[@]}"; do
  run gcloud pubsub topics add-iam-policy-binding "$t" --project "$project" \
    --member "serviceAccount:$(gsa_email "${prefix}-fnd-outbox")" --role "$role_outbox"
done

section "Export bucket gs://${export_bucket} (API reads, worker writes; no bucket admin)"
run gcloud storage buckets add-iam-policy-binding "gs://${export_bucket}" \
  --member "serviceAccount:$(gsa_email "${prefix}-rts-export-api")" --role "$role_export_read"
run gcloud storage buckets add-iam-policy-binding "gs://${export_bucket}" \
  --member "serviceAccount:$(gsa_email "${prefix}-rts-export-wkr")" --role "$role_export_write"

section "Secret Manager containers (empty) and per-secret access"
# purpose-kebab|lane|owner|rotation-days|accessor keys (comma-separated)
secret_specs=(
  "rights-service-token|rts|midnight-rights|90|fnd-gateway,rts-read-api"
  "privacy-service-token|rts|midnight-rights|90|fnd-gateway,rts-read-api"
  "privacy-export-service-token|rts|midnight-rights|90|fnd-gateway,rts-export-api,rts-export-wkr"
  "chain-service-token|rts|midnight-rights|90|fnd-gateway,rts-chain"
  "midnight-blockfrost-project-id|rts|midnight-rights|event-driven|rts-chain"
  # Gateway-only signing key for consumer-domain principal assertions; the domain
  # service gets the public JWKS from Helm values, never this secret.
  "domain-assertion-key|dom|consumer-domains|180|fnd-gateway"
)
[ "$include_planned" -eq 0 ] || secret_specs+=("domain-assertion-key|com|commerce-agents|180|fnd-gateway")
for spec in "${secret_specs[@]}"; do
  IFS='|' read -r purpose lane owner days accessors <<<"$spec"
  sm_id="brandme-${mode}-${lane}-${purpose}"
  consumers_label="${accessors//,/_}"
  ensure gcloud secrets describe "$sm_id" --project "$project" -- \
    gcloud secrets create "$sm_id" --project "$project" --replication-policy automatic \
      --labels "lane=${lane},owner=${owner},rotation-days=${days},consumers=${consumers_label}"
  IFS=',' read -r -a accessor_keys <<<"$accessors"
  for key in "${accessor_keys[@]}"; do
    run gcloud secrets add-iam-policy-binding "$sm_id" --project "$project" \
      --member "serviceAccount:$(gsa_email "${prefix}-${key}")" --role roles/secretmanager.secretAccessor
  done
done
# Commerce provider credentials are created out of band by operators under
# brandme-<mode>-com-provider-*; the domain may read only that prefix. The
# narrower prefix keeps the gateway's assertion signing key out of its reach.
run gcloud projects add-iam-policy-binding "$project" \
  --member "serviceAccount:$(gsa_email "${prefix}-com-domain")" --role roles/secretmanager.secretAccessor \
  --condition "expression=resource.name.startsWith(\"projects/${project_number}/secrets/brandme-${mode}-com-provider-\"),title=brandme-${mode}-com-provider-secrets"

section "CI identities: image push and deploy are separate service accounts"
# The pusher only writes images; the deployer only reads cluster credentials and
# deploys into one namespace. Neither can do the other's job.
run gcloud artifacts repositories add-iam-policy-binding "$ar_repo" --location "$ar_location" --project "$ar_project" \
  --member "serviceAccount:$(gsa_email "${prefix}-fnd-pusher")" --role roles/artifactregistry.writer
run gcloud projects add-iam-policy-binding "$project" \
  --member "serviceAccount:$(gsa_email "${prefix}-fnd-deployer")" --role roles/container.clusterViewer --condition None
printf '# then, with cluster-admin credentials (namespace-scoped deploy rights; not run by this script):\n'
show kubectl create rolebinding brandme-deployer --clusterrole admin --namespace "$namespace" \
  --user "$(gsa_email "${prefix}-fnd-deployer")"
if [ "$ar_project" != "$project" ]; then
  printf '# images live in %s: grant the cluster node service account read access there (not run by this script):\n' "$ar_project"
  show gcloud artifacts repositories add-iam-policy-binding "$ar_repo" --location "$ar_location" --project "$ar_project" \
    --member "serviceAccount:NODE_SA_EMAIL" --role roles/artifactregistry.reader
fi

section "GitHub Workload Identity Federation (keyless CI; two pools)"
[[ "$require_environment" =~ ^(sandbox|production)$ ]] || die "--require-environment must be sandbox or production"
ref_clauses=()
for ref in "${allow_refs[@]}"; do
  [[ "$ref" =~ ^refs/(heads|tags)/[A-Za-z0-9._/-]+\*?$ ]] || die "invalid --allow-ref '$ref'"
  if [[ "$ref" == *"*" ]]; then
    ref_clauses+=("assertion.ref.startsWith(\"${ref%\*}\")")
  else
    ref_clauses+=("assertion.ref == \"${ref}\"")
  fi
done
ref_condition="${ref_clauses[0]}"
for clause in "${ref_clauses[@]:1}"; do ref_condition+=" || ${clause}"; done
# Pinned to the immutable repository id (a renamed or transferred repository keeps
# its name claim available to others) and, for deploys, to the GitHub Environment,
# whose required reviewers and branch rules gate the token.
repo_clause="assertion.repository_id == \"${github_repo_id}\" && assertion.repository == \"${github_repo}\""
mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref"
deploy_condition="${repo_clause} && (${ref_condition}) && assertion.environment == \"${require_environment}\""
deploy_mapping="${mapping},attribute.environment=assertion.environment"
push_condition="${repo_clause} && (assertion.ref == \"refs/heads/main\" || assertion.ref.startsWith(\"refs/tags/v\"))"
wif_setup() {
  local pool="$1" provider="$2" map="$3" cond="$4" purpose="$5"
  ensure gcloud iam workload-identity-pools describe "$pool" --location global --project "$project" -- \
    gcloud iam workload-identity-pools create "$pool" --location global --project "$project" \
      --display-name "GitHub Actions ${purpose}" --description "Keyless CI ${purpose} for ${github_repo}"
  ensure gcloud iam workload-identity-pools providers describe "$provider" --workload-identity-pool "$pool" \
      --location global --project "$project" -- \
    gcloud iam workload-identity-pools providers create-oidc "$provider" --workload-identity-pool "$pool" \
      --location global --project "$project" --display-name "${github_repo} ${purpose}" \
      --issuer-uri "https://token.actions.githubusercontent.com" \
      --attribute-mapping "$map" --attribute-condition "$cond"
  run gcloud iam workload-identity-pools providers update-oidc "$provider" --workload-identity-pool "$pool" \
    --location global --project "$project" --attribute-mapping "$map" --attribute-condition "$cond"
}
wif_bind() {
  run gcloud iam service-accounts add-iam-policy-binding "$(gsa_email "${prefix}-$1")" --project "$project" \
    --role roles/iam.workloadIdentityUser \
    --member "principalSet://iam.googleapis.com/projects/${project_number}/locations/global/workloadIdentityPools/$2/attribute.repository_id/${github_repo_id}"
}
wif_setup "$wif_pool" "$wif_provider" "$deploy_mapping" "$deploy_condition" "deploy"
wif_bind fnd-deployer "$wif_pool"
wif_setup "$push_wif_pool" "$push_wif_provider" "$mapping" "$push_condition" "image push"
wif_bind fnd-pusher "$push_wif_pool"

if [ "$with_projector" -eq 1 ]; then
  section "Projector (Firestore database ${firestore_database} + its subscription)"
  run gcloud projects add-iam-policy-binding "$project" \
    --member "serviceAccount:$(gsa_email "${prefix}-fnd-projector")" --role roles/datastore.user \
    --condition "expression=resource.name == \"projects/${project}/databases/${firestore_database}\",title=brandme-${mode}-firestore"
  run gcloud pubsub subscriptions add-iam-policy-binding "$projector_subscription" --project "$project" \
    --member "serviceAccount:$(gsa_email "${prefix}-fnd-projector")" --role roles/pubsub.subscriber
fi

if [ -n "$dom_media_bucket" ]; then
  section "Consumer-domains media (gs://${dom_media_bucket}; keyless V4 signing)"
  run gcloud storage buckets add-iam-policy-binding "gs://${dom_media_bucket}" \
    --member "serviceAccount:$(gsa_email "${prefix}-dom-api")" --role roles/storage.objectUser
  run gcloud iam service-accounts add-iam-policy-binding "$(gsa_email "${prefix}-dom-api")" --project "$project" \
    --member "serviceAccount:$(gsa_email "${prefix}-dom-api")" --role roles/iam.serviceAccountTokenCreator
fi

section "GitHub repository variables to set afterwards (not secrets)"
printf 'BM_GCP_PROJECT_ID=%s\n' "$project"
printf 'BM_GCP_WIF_PROVIDER=projects/%s/locations/global/workloadIdentityPools/%s/providers/%s\n' "$project_number" "$wif_pool" "$wif_provider"
printf 'BM_GCP_DEPLOYER_SA=%s\n' "$(gsa_email "${prefix}-fnd-deployer")"
printf '# for build-images once it moves off GCP_SA_KEY (packet G24):\n'
printf 'BM_GCP_PUSH_WIF_PROVIDER=projects/%s/locations/global/workloadIdentityPools/%s/providers/%s\n' "$project_number" "$push_wif_pool" "$push_wif_provider"
printf 'BM_GCP_PUSHER_SA=%s\n' "$(gsa_email "${prefix}-fnd-pusher")"
printf '\n# consumer-ui and spatial-ar get no Google identity. Database: %s\n' "$database_path"
if [ "$apply" -eq 1 ]; then
  printf '# applied.\n'
else
  printf '# dry run complete: nothing was executed.\n'
fi
