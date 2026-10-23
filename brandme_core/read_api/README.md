# Rights and My Data read service

This is a separate, authenticated HTTP process packaged in the core image. It
reads existing Spanner records through the gateway. It does not submit chain
transactions, construct commands, export objects, or execute deletion jobs.

| Public gateway path | Backend path | Gateway scope |
| --- | --- | --- |
| `GET /api/v1/rights/entitlements` | `/rights/entitlements` | `rights:read` |
| `GET /api/v1/rights/reprint-jobs/{jobId}` | `/rights/reprint-jobs/{jobId}` | `rights:reprint` |
| `GET /api/v1/assets/{assetId}/passport` | `/rights/assets/{assetId}/passport` | Public claims; optional verified member |
| `GET /api/v1/me/data` | `/privacy/inventory` | `privacy:manage` |
| `GET /api/v1/me/deletion/{jobId}` | `/privacy/deletion/{jobId}` | `privacy:manage` |

Public response contracts are generated from
`packages/contracts/src/read-schemas.json`. Entitlements and passport claims
accept `limit` (1–100, default 24) and `cursor` (`next_cursor` from the preceding
page). Entitlement cursors are hex IDs; claim cursors are UUIDs. Every page
rechecks access and uses a new strong snapshot; pages are not a frozen export.
Unknown and repeated pagination keys are rejected. Int64 fields such as epoch,
block height, quantity and deletion counts are decimal strings.

## Deploy explicitly

Apply and verify the repository migrations through V013 before startup. Versions
V003–V005 are reserved and have no files. The service verifies applied migration
coverage and required columns; it never applies migrations. Run the migration
runner's `verify` command separately for checksum verification.

Use a separate database per environment. Several legacy tables have no
environment column. Configure these through the deployment and secret manager;
do not commit credentials:

```text
BRANDME_MODE=sandbox
ENVIRONMENT=sandbox
SPANNER_PROJECT_ID=<project>
SPANNER_INSTANCE_ID=<instance>
SPANNER_DATABASE_ID=<database reserved for this environment>
READ_API_NETWORK=preprod
READ_API_CONTRACT_ADDRESS=<64 lowercase hex characters>
RIGHTS_SERVICE_TOKEN=<independent random service credential, 32–256 characters>
PRIVACY_SERVICE_TOKEN=<different random service credential, 32–256 characters>
PORT=8000
```

Tokens use letters, digits or `._~+/-`. Give this process read-only database
permissions with the session permissions required by the Spanner client. Keep
the listener private behind authenticated network ingress and TLS; only the
gateway may reach it. A service bearer credential authorizes the gateway to
supply a verified internal member UUID in `X-Subject-Ref`. These credentials
must never reach browsers. Rights and privacy credentials cannot be equal or
used interchangeably. Even public passport reads require the rights credential
on the private backend. No caller-selected `viewer` or supplier role is accepted.

Override the existing core image's legacy default command:

```sh
python -m brandme_core.read_api --check
python -m brandme_core.read_api
```

For Docker, set the entrypoint to `python` and args to
`-m brandme_core.read_api`. Configure readiness at `GET /health`. The health
response contains only environment, readiness and the read-only capability;
database/provider errors are redacted. Access logging is disabled to avoid
logging private paths. Sandbox/production refuse the Spanner emulator;
demo/development require it. There is no Mainnet mode for this service.

Configure the gateway with `RIGHTS_SERVICE_URL=https://<private-service>/rights`,
`PRIVACY_SERVICE_URL=https://<private-service>/privacy` and the two matching,
distinct service credentials. `PRIVACY_SERVICE_TOKEN` is now mandatory for
privacy requests; there is no fallback to `RIGHTS_SERVICE_TOKEN`. Entitlements
are returned only when their network agrees with the chain capability response.
An unavailable capability on the same network remains explicitly unavailable;
it does not prevent inspecting persisted read data or enable writes.

## Read boundaries

- Entitlements filter member, network and contract in SQL. Reprint/deletion
  status filter job and member in the same query; reprints also filter network.
  Reprint records do not carry a contract address and are presented as workflow
  status, never as proof for the configured contract. Missing and other-member
  jobs return the same 404. Raw quotes, internal operation arguments and member
  references are excluded from responses.
- Passport environment and network are filtered in SQL. Owner claims require
  exactly one active entitlement for the asset on that network, with the
  configured contract and verified member. Multiple active links, revoked
  control, restrictions, pending deletion and newer tombstones grant no owner
  access. This check and the claims read share one strong snapshot. Owner claims
  without a network binding are excluded. Supplier-only claims remain hidden:
  `PassportClaims` lacks the supplier and contract bindings needed for broader
  access. Public statements remain public. Claims retain individual evidence,
  expiry/revocation state and test-network labels; they are not a current
  on-chain control proof or a physical ownership assertion.
- All reads, including health and public claims, refuse incomplete/failed
  restores. Before a physical restore, traffic and writers must still be
  stopped and the authoritative tombstone ledger preserved outside that backup.
  A database-local check cannot establish that an old backup's ledger is current.
- Queries have explicit RPC deadlines and no query retries; pages have row caps,
  JSON values/receipts are bounded to 64 KiB in SQL, and HTTP JSON is capped at
  512 KiB. The gateway additionally bounds upstream time and response bytes.
  Responses are never cacheable. Historical deletion receipt summaries include
  only category status and counts, excluding arbitrary handler error text.

## Remaining integration

My Data inventory covers the five categories registered by
`RightsPrivacyHandler`. `coverage.full_account` is **false**. Export and deletion
capabilities are **unavailable**, and command requests return 503 without
creating jobs. A readable historical deletion job is not evidence that a new
account deletion can be accepted. Other domains still need real handler coverage,
authenticated private export storage/download/expiry and orphan cleanup,
idempotent request acceptance, serialized durable deletion execution and fenced
external callbacks. All writers need privacy guards.

Deploying this process, its database permissions, ingress and gateway settings
is still a target-environment task. Rights commands, member wallet integration,
full contract-history replay, authenticated event consumers and funded Midnight
Preprod transactions with canonical finality evidence also remain outstanding.
No local/emulator test or successful image publication proves those tasks done.
