# Midnight integration checkpoint — 2026-10-22

## Main CI repaired first

PR #41 repaired Chain Service Tests. PR #42 repaired the existing Docker matrix and merged as `1ac8f97da6b326cfe6f425e26abd0daac6044917`.

- [Main Build, Test, and Deploy](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39863069281): all five images built, passed runtime smoke checks, and published to GCR. The tag-only GKE deployment was skipped.
- [Main Chain Service Tests](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39863069283): passed.
- [Main Module Regression](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39863069284): passed.

## Integrated application boundaries

The gateway now mounts `/api/v1/chain`, `/rights`, `/ownership`, `/assets`, and the My Data routes under `/me`. Private routes resolve the existing verified OIDC/session principal, enforce scopes, and pass the internal member ID downstream. Caller-supplied subject headers and bearer tokens are not forwarded. Cookie writes retain CSRF checks; exports and deletion require recent server-side session creation or verified OIDC `auth_time` (token issuance is not reauthentication).

Configuration:

| Variable | Purpose |
| --- | --- |
| `CHAIN_SERVICE_URL` | Chain capability service; local default `http://localhost:3003` (set chain `PORT=3003` to match) |
| `RIGHTS_SERVICE_URL` | Trusted internal rights API base URL, without a trailing resource path |
| `PRIVACY_SERVICE_URL` | Trusted internal My Data API base URL |
| `RIGHTS_SERVICE_TOKEN` | Server-only credential (at least 32 characters) required for both domain services |

Missing domain URLs/token return 503. Domain endpoints must authenticate this credential, authorize every resource against the internal member ID, and implement durable command idempotency before they are configured. Use TLS or an authenticated service mesh for credential transport. This change supplies the gateway boundary; it does **not** create the missing HTTP command backends.

Capability parsing rejects malformed status/network values, derives test-network badges locally, and cannot enable Mainnet writes. Endpoint/contract configuration alone no longer reports write readiness: application submission, durable persistence and reconciliation are still missing. Unexpected upstream errors do not expose internal provider URLs or credentials.

## Domain events and privacy correctness

Seven exact, closed payload contracts are registered: `ownership.transfer.requested`, `chain.operation.observed`, `license.issued`, `reprint.attested`, `rights.entitlement.projected`, `privacy.deletion.requested`, and `privacy.deletion.completed`. Payloads carry bounded references; secret fields, arbitrary extra fields and Mainnet network evidence are rejected.

Verified entitlement projection writes `rights.entitlement.projected` in the same Spanner transaction as the projection. Replayed/stale/rejected observations emit nothing. V010 adds a projection revision independent of chain epoch. **Apply V010 before deploying this projection code.** Previously applied migrations are unchanged. Projection callers must provide the explicit Brand.Me environment and must remain trusted reconciler code; a client-submitted transaction ID is not finalized evidence.

Deletion requests and completion write outbox events atomically with the job state. Completed retries preserve the original receipt and do not emit another completion. Pending derived deletion retains its processing freeze and emits no completion. An older category deletion cannot lift a newer job's freeze. Public ledger receipts no longer claim that selecting only the public-commitments category also removed separate control links.

The other four registered event types still need producers in the application command/reconciliation adapters. Registration is not evidence of dispatch, projection delivery or end-to-end application completion.

## Preprod verification

The [official network reference](https://docs.midnight.network/guides/networks-and-environments) states that Midnight-hosted Preprod endpoints were retired on October 9, 2026. The service and network runner now use Blockfrost HTTP/WebSocket endpoints and require a `nightpreprod` project token. Mainnet tokens are rejected for Preprod. Provider error history, test logging, evidence and the Preprod command's console output redact provider credentials. Test wallet seeds are also redacted from runner output/evidence.

The root commands now invoke real chain scripts:

```sh
pnpm test:midnight:local
pnpm test:midnight:preprod
```

Before running Preprod, provision `MIDNIGHT_BLOCKFROST_PROJECT_ID` and `MN_PREPROD_SEEDS` through a secret manager in the test runner environment. `MN_PREPROD_SEEDS` needs at least three distinct 32-byte hex seeds for **test wallets only**. Each needs tNIGHT and usable DUST; follow the [official funding guide](https://docs.midnight.network/guides/acquire-tokens). Run the pinned local proof server from `brandme-chain/contracts/toolchain.json` on loopback port 6300 (or set `MN_PROOF_PORT`). Do not place tokens in frontend configuration, source, PR text or screenshots. Do not share raw SDK logs or wallet state directories.

No funded Preprod wallet seeds or Blockfrost token are present in this execution environment. The preflight correctly refuses to attempt transactions. No Preprod transaction, deployed contract address or finality evidence is claimed. Local circuit/adapter tests are separate evidence.

## Remaining launch requirements

- Implement and wire authenticated rights/My Data HTTP command adapters with per-resource authorization and principal/environment-scoped durable idempotency.
- Replace `InMemoryOperationStore` with a transactional durable store, connect the trusted indexer/finality reconciler, and publish the remaining registered events. Keep write capability disabled until these are verified together.
- Register the real application domains in My Data, wire their export/deletion handlers and processing-freeze checks, and verify account-wide deletion/restore. Fixture tests are not proof of these registrations.
- Run funded-wallet Preprod issue → prove → transfer → reprint/private-state-restore scenarios, recording actual transaction IDs, blocks and finality. Keep Mainnet writes disabled.

Local verification covers gateway authentication/CSRF/reauth boundaries, database/outbox atomicity and retries with a real Spanner emulator, migration application, chain type checking and compiled-contract tests. GitHub Actions additionally builds and smoke-tests every packaged image before publishing on main. This checkpoint does not claim a vulnerability-free dependency graph or a production launch.
