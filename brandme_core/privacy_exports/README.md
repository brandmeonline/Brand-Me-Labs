# Selected rights exports

This separately deployed API and worker implement exports of explicitly selected
rights categories. They do **not** implement a full account export, account
deletion, wallet ownership backups, or funded Midnight transactions. Every job
and package says `full_account: false` and `selected_categories_only: true`.

The gateway accepts `POST /api/v1/me/exports` with a verified `privacy:manage`
principal, authentication within ten minutes, a 16–128 character
`Idempotency-Key` (`A–Z`, `a–z`, digits, `_`, `-`), and an explicit nonempty
`categories` array. Select from `rights.control_links`, `rights.operations`,
`rights.transfers`, `rights.reprint_jobs`, and `rights.chain_commitments`.
Requests return 202 with an opaque job ID. Repeating the same member-scoped key
and selection returns that job; a different selection returns 409.

`GET /api/v1/me/exports/{jobId}` returns that member's status and safe package
metadata. `GET /api/v1/me/exports/{jobId}/download` requires recent authentication
again and returns a private JSON attachment with `X-Export-SHA256`, calculated
over the exact bytes. Both backend and gateway verify the digest. There are no
signed URLs. Caller-supplied subjects or reauthentication headers are ignored by
the gateway. Status/download cannot expose another member's job.

`GET /api/v1/me/exports/capability` checks the configured database restore barrier
and bucket policy. The My Data inventory advertises `export: selected_categories`
only after that check succeeds for its environment and registered categories.
Capability means requests can be accepted, not that a worker is currently running
or that a queued job has completed. Deletion remains unavailable.

## Deployment

Apply and verify migrations through **V014** with the existing migration runner
before starting either process. V014 creates new queue/request/object-ledger
tables; it does not reinterpret the older synchronous `ExportJobs` table or wire
the legacy `MyDataService.export()` method to HTTP.

Use the existing core image, overriding its entrypoint with Python:

```text
python -m brandme_core.privacy_exports --check
python -m brandme_core.privacy_exports
python -m brandme_core.privacy_exports --worker
python -m brandme_core.privacy_exports --worker --once
```

The API listens on `PORT` (default 8000). Deploy the polling worker as an
independently supervised process with continuous CPU, or schedule `--worker
--once` as a job. An HTTP service with request-only CPU is insufficient for the
polling worker. Each iteration sweeps up to five due cleanup records and builds
at most one export. Monitor queue age, failures and cleanup backlog, and size
workers/scheduling accordingly. Multiple workers use serializable claims and
unique attempt leases; database transactions never contain external uploads.
Worker logs contain only fixed outcomes and cleanup failure counts; a one-shot
run exits nonzero on dependency or cleanup failures. Provider text is excluded.

Required environment:

| Variable | Meaning |
|---|---|
| `BRANDME_MODE`, `ENVIRONMENT` | Matching explicit demo/development/sandbox/production mode |
| `SPANNER_PROJECT_ID`, `SPANNER_INSTANCE_ID`, `SPANNER_DATABASE_ID` | Isolated database for this environment |
| `EXPORT_NETWORK` | `undeployed`, `preview`, or `preprod`; Mainnet refused |
| `EXPORT_CONTRACT_ADDRESS` | 64 lowercase hex characters |
| `EXPORT_BUCKET` | Dedicated `brandme-<environment>-exports-…` bucket |
| `PRIVACY_EXPORT_SERVICE_TOKEN` | 32–256 character private service credential, distinct from other supplied service tokens |
| `SPANNER_EMULATOR_HOST`, `EXPORT_STORAGE_EMULATOR_HOST` | Both required in demo/development, both forbidden in sandbox/production |

The storage emulator must be loopback or the private `storage-emulator` container
hostname. Strict modes use ADC and the fixed Google Storage JSON API endpoint.
Redirects, ambient proxies and `.netrc` credentials are disabled. Do not expose
the API directly to the internet. Configure private ingress and workload
authentication at deployment, with the application bearer credential supplied
from secret management. Gateway settings are `PRIVACY_EXPORT_SERVICE_URL` (the
API root, without `/exports`) and `PRIVACY_EXPORT_SERVICE_TOKEN`.

Use separate workload identities: the API needs the queue/request database
operations, privacy/restore reads, bucket metadata and object reads; the worker
also needs selected rights projection reads, queue/object-ledger writes and
object create/delete. Neither needs bucket policy administration or wallet
credentials. Enforce and verify target IAM independently; the ADC OAuth scope
does not grant IAM permissions. Existing ingress/platform IAM choices must be
verified with the gateway before enabling the feature.

The bucket preflight requires uniform bucket-level access, enforced public access
prevention, versioning disabled, soft-delete retention explicitly zero, no
retention policy/default hold/object-retention enablement, and a lifecycle rule
exactly equivalent to `Delete` with the sole condition `age: 1`. Provision this
dedicated bucket separately. The process never modifies a bucket or its policy.
Preflight runs at startup and again before upload, download and cleanup. Changes
by bucket administrators are outside the application's transaction boundary.

## Correctness and limits

- The job and idempotency record commit atomically. Keys are hashed and scoped to
  environment and member. The chain scope and sorted selection are part of the
  request digest. Security abuse bounds allow two unexpired active/ready exports
  and ten requests per member per 24 hours; AI/commercial budgets are unrelated.
- A 120-second lease fences finalization. A new opaque object name is allocated
  for every attempt, with its cleanup record committed **before** upload. GCS
  creation uses `ifGenerationMatch=0`; downloads use the stored generation and
  cleanup uses generation-preconditioned deletes. Three failed attempts end the
  job. Lost upload/finalization acknowledgements do not delete a winning export.
- Selected categories are read in one strong Spanner snapshot, with restore and
  privacy checks. Control links, public references and operations are scoped to
  the configured contract/network (operations also to environment). Transfers
  and reprints have no contract column: their sections explicitly carry
  `contract_address: null` and contain member-owned records on that network.
  Legacy tables require separate databases per environment. These are app
  projections, not a full chain-history reconstruction or current control proof.
- Each category is capped at 1,000 rows and the complete JSON package at 2 MiB.
  Oversized jobs fail explicitly; nothing is silently truncated. Only allowlisted
  columns are read, never operation arguments, witnesses, payment credentials,
  raw quotes or provider errors. Int64 values are decimal strings.
- Existing freezes, pending/account deletions and newer tombstones are checked
  at acceptance, build, finalization, status and download. Downloads recheck after
  object I/O. Public commitment references also honor control-link restrictions.
  Authorization is evaluated at the final snapshot; bytes already released to a
  member cannot subsequently be revoked.
- Download access ends 24 hours after the request, regardless of worker health.
  The worker invalidates restricted/expired jobs before deleting objects. Ready
  objects are periodically checked for restrictions; deletion failures and late
  uploads remain subject to recurring cleanup. Cleanup ledgers are retained even
  after a successful delete. Bucket lifecycle is an asynchronous extra backstop;
  neither an expired status nor a cleanup attempt asserts physical deletion at
  an exact deadline. No deletion receipt is fabricated.
- Before physical restore, quiesce all API/worker processes and retain the
  authoritative tombstone ledger outside the backup. Reapply it and complete the
  restore barrier before serving. Local restored rows alone cannot establish
  that no later deletion occurred.

## Verification and remaining work

Tests exercise real Spanner migrations/transactions, an actual Python API and
worker process, signed OIDC through the mounted gateway, and a local HTTP fixture
for the GCS JSON API contract. They cover owner isolation, idempotency/concurrency,
stale workers, lost acknowledgements, expiry/repeated cleanup, restriction and
deletion races, digest tampering and unsafe bucket configurations. This is **not**
evidence of live GCS IAM, bucket lifecycle execution or a cloud deployment.

Target provisioning, migration rollout, actual cloud storage/IAM/ingress checks,
worker scheduling/monitoring, UI integration and full account category coverage
remain. New export operational metadata/request/cleanup retention must join the
future privacy-domain deletion policy; this milestone does not claim complete
account deletion or operational metadata erasure. Other domain handlers, durable
fenced deletion execution and all writer guards are still required. Wallet/private
state custody, rights commands, external history replay, event consumers and
funded Midnight Preprod finality evidence remain separate tasks. Mainnet writes
remain disabled.
