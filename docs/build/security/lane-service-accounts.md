# Per-lane service identities (sandbox)

Status (2026-10-23, base `744d593`): **design plus a dry-run script.**

- [`scripts/provision/gcp-dev-identities.sh`](../../../scripts/provision/gcp-dev-identities.sh)
  has **never been executed against a real GCP project.** No project, service
  account, role, pool or secret was created.
- What did run:
  - its default dry run;
  - its refusal cases;
  - an `--apply` pass against a recording `gcloud` stub (no network), confirming
    that it executes exactly the commands it prints and never a key-creating
    command;
  - `bash -n` and shellcheck 0.10.0.

Naming follows [secrets-conventions.md](secrets-conventions.md). Credentials are
listed in [credential-manifest.yaml](credential-manifest.yaml).

## Why sandbox, not development

"Dev identities" here means **sandbox in a non-production project**. A cloud
identity is useless in `development`, because development requires emulators:

- the read API (`brandme_core/read_api/config.py:28-30`);
- the export API (`brandme_core/privacy_exports/config.py:26-31`);
- the outbox worker (`brandme_core/events/worker.py:40-43`).

The script refuses `--mode development` and `--mode production`. Production
identities need their own reviewed change, in a dedicated project.

## Which lanes need GCP at all

| Lane | Needs a Google identity | Why |
|---|---|---|
| foundation (`fnd`) | yes | gateway, migrations, outbox worker, CI deployer; optional projector |
| midnight-rights (`rts`) | yes | chain service, read API, export API and worker |
| commerce-agents (`com`) | yes | commerce domain service; provider credentials by reference |
| consumer-domains (`dom`) | yes | domain API; media bucket once GCS replaces MemoryMediaStore |
| consumer-ui (`ui`) | **no** | reads only non-secret config; if deployed, use a zero-role identity, never the default compute account |
| spatial-ar (`ar`) | **no** | same as consumer-ui |
| CI test jobs | **no** | emulators only |

## Identities

Each identity has a Kubernetes ServiceAccount (KSA) `<release>-<component>` in
namespace `brandme` (defaults `--release brandme --namespace brandme`). The KSA
is bound with `roles/iam.workloadIdentityUser` for
`serviceAccount:<project>.svc.id.goog[brandme/<ksa>]`. **No identity has a key.**

All roles are granted on the resource, not the project, except two:

- `roles/container.clusterViewer` for the deployer;
- the conditional prefix grant for commerce provider secrets.

| GSA (sandbox) | KSA | Purpose | Roles (resource-scoped) | Secret access |
|---|---|---|---|---|
| `bm-sbx-fnd-deployer` | none (GitHub WIF) | CI image push and helm deploy | `roles/artifactregistry.writer` on the image repository; `roles/container.clusterViewer` (project); in-cluster RBAC `admin` on namespace `brandme` only | none |
| `bm-sbx-fnd-migrator` | `brandme-migrations` | `runner.py up` (helm pre-upgrade Job) | `roles/spanner.databaseUser` on the database (DDL plus ledger writes; no create, drop or IAM) | none |
| `bm-sbx-fnd-outbox` | `brandme-events-worker` | outbox to Pub/Sub dispatcher | `brandmeSpannerDataReadWrite` on the database; `brandmeOutboxPublisher` on the three outbox topics only | none |
| `bm-sbx-fnd-gateway` | `brandme-gateway` | API gateway (identity/session store) | `brandmeSpannerDataReadWrite` on the database | the four service tokens; the planned commerce assertion key (`--include-planned`) |
| `bm-sbx-fnd-projector` (only with `--with-projector`) | `brandme-projector` | Firestore projection writer (no process exists yet) | `roles/datastore.user` conditioned on the one Firestore database; `roles/pubsub.subscriber` on its subscription | none |
| `bm-sbx-rts-chain` | `brandme-chain` | Midnight chain service (operation store) | `brandmeSpannerDataReadWrite` on the database | `CHAIN_SERVICE_TOKEN`, `MIDNIGHT_BLOCKFROST_PROJECT_ID` |
| `bm-sbx-rts-read-api` | `brandme-read-api` | rights/privacy read API | `roles/spanner.databaseReader` on the database (`brandme_core/read_api/README.md:47-48`) | `RIGHTS_SERVICE_TOKEN`, `PRIVACY_SERVICE_TOKEN` |
| `bm-sbx-rts-export-api` | `brandme-exports-api` | privacy export API | `brandmeSpannerDataReadWrite` on the database; `brandmeExportObjectReader` on the export bucket | `PRIVACY_EXPORT_SERVICE_TOKEN` |
| `bm-sbx-rts-export-wkr` | `brandme-exports-worker` | privacy export worker | `brandmeSpannerDataReadWrite` on the database; `brandmeExportObjectWriter` on the export bucket | `PRIVACY_EXPORT_SERVICE_TOKEN` (the worker parses the same `ExportConfig`, `brandme_core/privacy_exports/__main__.py:32`) |
| `bm-sbx-com-domain` | `brandme-commerce-domain` | commerce domain service | `brandmeSpannerDataReadWrite` on the database | `roles/secretmanager.secretAccessor` conditioned on `projects/<number>/secrets/brandme-sandbox-com-provider-*` |
| `bm-sbx-dom-api` | `brandme-consumer-domains-api` | consumer domains API | `brandmeSpannerDataReadWrite` on the database; with `--dom-media-bucket`, `roles/storage.objectUser` on the media bucket and `roles/iam.serviceAccountTokenCreator` on itself (keyless V4 signed URLs) | none |

The two privacy export identities are separate, as
`brandme_core/privacy_exports/README.md:75-79` requires. Only the worker can
create or delete objects. Neither can administer the bucket or its policy.

The Midnight contract maintenance key is under governance custody and is held by
no service account (`brandme-chain/src/midnight/adapter.ts:439-444`).

`MN_PREPROD_SEEDS` belongs to the reviewer-gated GitHub Environment `sandbox` and
to no GCP identity.

## Custom roles

The script creates these roles at project level and grants them only on the
named resource.

| Role id | Permissions | Why not a predefined role |
|---|---|---|
| `brandmeSpannerDataReadWrite` | `spanner.databases.{beginOrRollbackReadWriteTransaction, beginPartitionedDmlTransaction, beginReadOnlyTransaction, get, getDdl, partitionQuery, partitionRead, read, select, write}`, `spanner.sessions.{create, delete, get, list}` | `roles/spanner.databaseUser` also includes `spanner.databases.updateDdl`. Its permission list was checked against `docs.cloud.google.com/iam/docs/roles-permissions/spanner` on 2026-10-23. Runtime services never run DDL. Partitioned DML stays because `brandme_core/spanner/idempotent.py:210` uses it. |
| `brandmeOutboxPublisher` | `pubsub.topics.publish`, `pubsub.topics.get` | Exactly what `brandme_core/events/README.md:27-30` asks for: publish, and `get` for the retention check at startup. `roles/pubsub.publisher` lacks `get`; `roles/pubsub.viewer` is broader. |
| `brandmeExportObjectReader` | `storage.buckets.get`, `storage.objects.get` | The API reads bucket metadata (preflight) and objects (download). |
| `brandmeExportObjectWriter` | the reader permissions plus `storage.objects.create`, `storage.objects.delete` | The worker also uploads and cleans up. Nothing grants `setIamPolicy` or `buckets.update`. |

Not verified live: that every permission above is accepted in a custom role
granted on a Spanner database, and how gcloud reacts to permissions that do not
apply at that level. Run the script against a throwaway sandbox project first.

## GitHub Workload Identity Federation

The script creates pool `github` and OIDC provider `brandme-labs`, with issuer
`https://token.actions.githubusercontent.com`, this attribute mapping:

```
google.subject=assertion.sub,attribute.repository=assertion.repository,
attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref
```

and this default attribute condition, which pins the repository **and** the ref:

```
assertion.repository == "brandmeonline/Brand-Me-Labs" && (assertion.ref == "refs/heads/main")
```

- `--allow-ref 'refs/tags/v*'` adds `|| assertion.ref.startsWith("refs/tags/v")`.
- `--github-repo-id N` also pins the numeric repository id, which survives a
  repository rename. Recommended; the id was not looked up here.
- `--require-environment sandbox` also requires the Environment claim, which suits
  the deploy job once it runs under `environment: sandbox`. Image publishing on
  push to main does not run under an Environment today.
- Pull-request refs (`refs/pull/N/merge`) never match.

The deployer service account then grants `roles/iam.workloadIdentityUser` to
`principalSet://iam.googleapis.com/projects/<number>/locations/global/workloadIdentityPools/github/attribute.repository/brandmeonline/Brand-Me-Labs`.

The script prints the repository variables to set afterwards:
`BM_GCP_PROJECT_ID`, `BM_GCP_WIF_PROVIDER` and `BM_GCP_DEPLOYER_SA`.

## Prerequisites (never created by the script; checked before any change)

1. **Pick the project.** CI currently pushes to `lux-realestate-app`
   (`.github/workflows/ci-cd.yml:37`), which looks shared. With `--apply` the script
   refuses any project id containing `prod` or `lux-realestate` unless you pass
   `--i-understand-shared-project`. A dedicated sandbox project is the recommended
   default.
2. **Create the data plane:**
   - Spanner `brandme-instance`/`brandme-db`;
   - the topics `brandme-sandbox-public`, `brandme-sandbox-member-private` and
     `brandme-sandbox-restricted`, with at least 24 h retention;
   - the export bucket `brandme-sandbox-exports-<suffix>`, with the policy
     `brandme_core/privacy_exports/storage.py:100-113` enforces;
   - the Artifact Registry repository (default `gcr.io` in `us`, the path CI pushes
     to today);
   - a GKE cluster with Workload Identity and namespace `brandme`.

   The GKE deploy-verification packet covers these.
3. **Get an operator** with permission to create service accounts, roles, IAM
   bindings, WIF pools and secrets.
4. **After `--apply`, as a cluster admin:** run
   `kubectl create rolebinding brandme-deployer --clusterrole admin --namespace brandme --user <deployer email>`
   (the script prints it but does not run it). Then make sure the node pool can
   pull from the registry.
5. **Add secret values** with the rotation runbook: `gcloud secrets versions add`
   from stdin, never on the command line. The script creates **empty** secret
   containers only.

## Options worth knowing

- `--enforce-no-sa-keys` enforces the org policy
  `iam.disableServiceAccountKeyCreation` on the project. This needs an org-policy
  admin; verify the command against current gcloud documentation first.
- `--ar-repo` and `--ar-location` override the registry; `--spanner-*` and
  `--export-bucket` override the data plane; `--release` and `--namespace`
  override the KSA names.
- `--yes` skips the typed-confirmation prompt. Without it, `--apply` needs an
  interactive terminal.

## Open decisions (founder)

- Which project hosts sandbox (`lux-realestate-app` or a new dedicated project)?
  Is the deploy target GKE or Cloud Run (ADR-06 makes Cloud Run the initial
  target)?
- Should the deployer get `roles/container.developer` (simpler, cluster-wide)
  instead of `clusterViewer` plus namespace RBAC?
- Will a projector process exist, and will agents use Vertex AI (IAM, no key) or
  a provider key?
- Who custodies the Preprod test wallets?
