# Credential rotation and exposure runbook (stub)

Status (2026-10-23, base `744d593`): **a stub for the founder to adopt and extend.**
Nothing here has been run against a deployed environment. No sandbox or production
deployment exists yet, and no credential has been provisioned. Commands marked
*(proposed)* depend on changes that are not implemented. The repository is
**public**.

Spec requirements:

- rotation without losing ingestion cursors or in-flight reconciliation
  ([03](../../design/brandme/03-architecture-data-api.md), Security);
- a documented credential rotation ([06](../../design/brandme/06-delivery-verification.md)).

## 1. Scope

The scope is every row of
[credential-manifest.yaml](../security/credential-manifest.yaml) with `status: active`
(and `planned` rows once they become active). Each row gives:

- the Secret Manager id pattern;
- the GitHub location;
- the validation regex;
- `distinct_from`;
- `rotation_class` and `cadence_days`;
- the consumers, each as `path:line`.

Rows with status `legacy-unread` or `refused` are never provisioned, so there is
nothing to rotate. If one is found set anywhere, treat it as an exposure (section 5)
and delete it.

Naming and identities: [secrets-conventions.md](../security/secrets-conventions.md),
[lane-service-accounts.md](../security/lane-service-accounts.md).

## 2. Roles

| Role | Who | Does |
|---|---|---|
| Owner lane | `lane_owner` in the manifest (`rts` owns the four service tokens and Midnight credentials; `com` owns commerce keys and provider references; `fnd` owns CI and GCP identity) | keeps the row current, approves format changes |
| Rotator | an operator with `secretmanager.versions.add` on that secret only | generates and adds the new version, rolls the workloads, records evidence |
| Approver | a second person (GitHub Environment reviewer for `sandbox` and `production`) | approves the change window and the evidence |
| Break-glass | founder, or a named delegate with project owner rights | revokes or disables during an exposure, outside the normal window |

No workload identity can add secret versions. Only people in the rotator role can.

## 3. Classes

| Class | Examples | Cadence | Rule |
|---|---|---|---|
| internal-bearer | `RIGHTS_SERVICE_TOKEN`, `PRIVACY_SERVICE_TOKEN`, `PRIVACY_EXPORT_SERVICE_TOKEN`, `CHAIN_SERVICE_TOKEN` | about 90 days, and on any exposure | Generate a new random value. All four stay pairwise distinct. |
| provider-token | `MIDNIGHT_BLOCKFROST_PROJECT_ID`, `MAGIC_API_KEY` | on exposure, or per provider policy | Regenerate at the provider, then revoke the old one there. Never reuse a value across modes. |
| test-wallet-seeds | `MN_PREPROD_SEEDS` | per test campaign, and on exposure | **Replace and sweep, never edit:** fund new wallets, move remaining funds out of the old ones, then swap the secret. |
| signing-key | `COMMERCE_DOMAIN_ASSERTION_KEY` (planned), MCP authorization-server keys | about 180 days | **Overlap by kid:** publish the new public key before signing with it, and remove the old one after the longest token lifetime. |
| gcp-keyless | every Google service account (WIF for CI, Workload Identity for pods, ADC in code) | nothing to rotate | **No keys exist.** Alert on any key creation (section 4.5). |
| gcp-sa-key-legacy | `GCP_SA_KEY` (CI today) | retire, do not rotate | Move CI to WIF, then delete the key. If it is exposed first, delete the key immediately. |

## 4. Procedures

Never put a value on a command line, in shell history, a ticket, a log or a
commit. Pipe it from the generator straight into `gcloud ... --data-file=-`, or
paste it into the GitHub Environment secret UI.

### 4.1 Internal bearer tokens

1. **Generate** a value that matches `^[A-Za-z0-9._~+/-]{32,256}$`, and check that it
   differs from the other three tokens. For example, this pipe prints nothing:

   ```sh
   python3 -c 'import secrets; print(secrets.token_urlsafe(48), end="")' \
     | gcloud secrets versions add brandme-<mode>-rts-<name-kebab> --data-file=- --project <project>
   ```

   `token_urlsafe(48)` yields 64 characters of `[A-Za-z0-9_-]`, which every
   consumer accepts:
   - gateway: `brandme-gateway/src/config/index.ts:39-42`;
   - read API: `brandme_core/read_api/config.py:35`;
   - export API: `brandme_core/privacy_exports/config.py:42`;
   - chain: `brandme-chain/src/config/index.ts:20`.
2. **Roll the server and the gateway together.** Today every server compares
   against exactly one token:
   - `brandme_core/read_api/app.py:76` (rights and privacy);
   - `brandme_core/privacy_exports/app.py:31` (exports);
   - `brandme-chain/src/routes/operations.ts:35` (chain).

   So a rotation is a **coordinated restart**: restart the backend and the gateway
   in the same window. Between the two restarts, gateway calls get 401/403, which
   the gateway reports as 503 "could not authorize"
   (`brandme-gateway/src/services/rights.ts:31`). Pick a quiet window. Chain
   reconciliation resumes from its Spanner operation store, so no in-flight
   operation or ingestion cursor is lost (section 4.6).

   *(Proposed, cross-lane, not implemented.)* Servers would also accept an
   optional `<NAME>_NEXT`, validated with the same regex and distinctness rules
   and compared in constant time. The order would then be:
   1. set `_NEXT` on the server and roll it;
   2. switch the gateway to the new value and roll it;
   3. promote the new value to `<NAME>`, clear `_NEXT` and roll the server again.

   This removes the 401 window. It touches midnight-rights code (read API, exports,
   chain) and foundation code (gateway config).
3. **Verify.** Run each command with the deployed environment. Each prints a
   one-line JSON status and exits 0, or prints `{"status":"startup_refused"}` and
   exits 2:
   - `python -m brandme_core.read_api --check` checks `RIGHTS_SERVICE_TOKEN` and
     `PRIVACY_SERVICE_TOKEN`, migrations and the restore barrier.
   - `python -m brandme_core.privacy_exports --check` checks
     `PRIVACY_EXPORT_SERVICE_TOKEN`, the bucket policy and the schema.
   - `python -m brandme_core.events.worker --check` checks that the outbox
     worker's ADC, topics and schema are intact after the restart.
   - The gateway: `GET /healthz` only proves that the process is up. Also run one
     request per backend through the gateway (for example a public passport read,
     which needs the rights credential). Confirm that none returns 503 "could not
     authorize".
   - The chain: `GET /health`, then one authenticated operation request from the
     gateway.
4. **Retire the old version:** run
   `gcloud secrets versions disable <old-version> --secret <id>`, then destroy it
   after 7 days if nothing broke.
5. **Record the evidence** (section 6).

### 4.2 Provider tokens (Blockfrost Midnight)

1. Create a new project token in the Blockfrost dashboard, for the right network
   only:
   - `nightpreprod...` for sandbox;
   - `nightmainnet...` for production.

   The value must match `^night(preprod|mainnet)[A-Za-z0-9_-]{8,}$`
   (`brandme-chain/src/midnight/network.ts:37`).
2. Add it as a new version of `brandme-<mode>-rts-midnight-blockfrost-project-id`
   (from stdin). If it is also used by the reviewer-gated Preprod workflow, update
   the GitHub Environment `sandbox` secret `MIDNIGHT_BLOCKFROST_PROJECT_ID`.
3. Restart the chain service. Verify with `GET /midnight/capability` on the chain
   service (`brandme-chain/src/routes/midnight.ts:16`): the status must not drop to
   `unavailable`. For sandbox, run `pnpm test:midnight:preprod`; the runner redacts
   the token.
4. Revoke the old token at Blockfrost. Disable the old secret version.

### 4.3 Test-wallet seeds (`MN_PREPROD_SEEDS`)

1. Create three or more **new** Preprod wallets. Fund them with tNIGHT and DUST.
2. Sweep the remaining funds out of the old wallets. Never edit or reuse a seed.
3. Replace the GitHub Environment `sandbox` secret. The format is comma-separated
   64-hex seeds, all distinct
   (`brandme-chain/scripts/test-midnight-preprod.mjs:8-9`).
4. Run `pnpm test:midnight:preprod` behind the Environment reviewer.
5. Record the new wallet **addresses** (public), never the seeds.

### 4.4 Signing keys (planned: `COMMERCE_DOMAIN_ASSERTION_KEY` / `_KID`)

1. Generate a new ES256 key pair offline. Store the PKCS8 PEM as a new version of
   `brandme-<mode>-com-domain-assertion-key` and pick a new kid.
2. Publish the new public key in the JWKS **alongside** the old one. Verifiers
   select keys by kid (as in `brandme_core/mcp/authz.py:99`).
3. Switch the gateway signer to the new key and kid (`COMMERCE_DOMAIN_ASSERTION_KID`).
4. Wait longer than the longest assertion lifetime. The reference signer uses 30
   seconds (`brandme_core/mcp/authz.py:199`). Then remove the old public key, and
   disable and destroy the old version.

### 4.5 GCP: keyless, nothing to rotate

- CI authenticates with Workload Identity Federation, pods with GKE Workload
  Identity, and code with ADC:
  - `brandme_core/events/pubsub.py:62-65`;
  - `brandme_core/privacy_exports/storage.py:50-52`.
- With `--enforce-no-sa-keys`, the provisioning script enforces the org policy
  `iam.disableServiceAccountKeyCreation`.
- Alert on key creation with a log-based alert on
  `protoPayload.methodName="google.iam.admin.v1.CreateServiceAccountKey"`, routed
  to the break-glass owner. Not configured yet.
- **Retire `GCP_SA_KEY`:**
  1. Set the repository variables `BM_GCP_WIF_PROVIDER` and `BM_GCP_DEPLOYER_SA`.
  2. Switch `google-github-actions/auth` to WIF and add `id-token: write`.
  3. Make one green run.
  4. List the keys with
     `gcloud iam service-accounts keys list --iam-account <old SA>`.
  5. Delete the user-managed keys with `gcloud iam service-accounts keys delete`.
  6. Delete the GitHub secret.

### 4.6 What rotation must never touch

- Ingestion cursors.
- The Spanner outbox/inbox.
- The chain operation store.

Rotation only changes credentials. Workloads resume from Spanner state after the
restart. Do not reset reconciliation or replay events as part of a rotation.

## 5. Exposure path (a value was seen where it should not be)

1. **Revoke first, investigate second.** Take whichever applies:
   - disable the exposed Secret Manager version;
   - regenerate at the provider (Blockfrost);
   - sweep the wallets (seeds);
   - delete the key (`GCP_SA_KEY`).
2. **Rotate** with the class procedure. For bearer tokens, accept the coordinated
   restart window.
3. **Treat any committed value as burned**, even after a history rewrite.
   - The repository is public: forks, clones, caches and secret scanners may
     already hold it.
   - Never "fix" an exposure by force-pushing alone.
4. **Audit:**
   - the Secret Manager data-access audit logs (`AccessSecretVersion`) since the
     exposure;
   - the provider dashboards;
   - the wallet histories;
   - the GitHub Actions run logs.
5. **Close the hole.** Possible causes:
   - a template carrying a value (the checker warns on this);
   - a log line;
   - a missing `.gitignore` rule;
   - a token that reached a browser through `NEXT_PUBLIC_` (the checker fails on
     this).

   Then add a test for it.
6. Record the incident in the evidence log with the timeline and no values.

## 6. Evidence log template (never record a value)

Store the log next to deployment evidence. Redact command output down to the
status line.

| Date (UTC) | Secret id / credential | Old version | New version | Class | Reason (scheduled / exposure / format change) | Rotator | Approver | Checks run and result (redacted) | Old version disabled / destroyed on |
|---|---|---|---|---|---|---|---|---|---|
| YYYY-MM-DD | brandme-sandbox-rts-chain-service-token | 3 | 4 | internal-bearer | scheduled | name | name | `read_api --check` exit 0 `{"status":"ready","read_only":true}`; gateway backend smoke 200 | YYYY-MM-DD / YYYY-MM-DD |

## Open items (not done in this change)

- **Startup distinctness** *(proposed)*. The gateway strict-mode guard
  (`brandme-gateway/src/middleware/mode.ts`) should:
  - require each `*_SERVICE_TOKEN` whose `*_SERVICE_URL` is set;
  - require all configured tokens to be pairwise distinct.

  The read API should also reject equality with `CHAIN_SERVICE_TOKEN` and
  `PRIVACY_EXPORT_SERVICE_TOKEN`.
- **`<NAME>_NEXT` dual-accept** (section 4.1) *(proposed, cross-lane)*.
- **Legacy deploy script.** `scripts/deploy.sh:38-46` still sources
  `.env.${ENVIRONMENT}` and exits when the file is missing. The legacy env files it
  read were deleted with this runbook. That script is already non-functional:
  - it builds images from service-directory contexts, while the Dockerfiles need
    the repository root;
  - its chart does not render.

  Retire it, or point it at an untracked operator file.
- **Alerting.** Configure a log-based alert for service-account key creation.
