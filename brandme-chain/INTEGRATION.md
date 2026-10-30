# Durable operation integration

The chain service now provides authenticated status, on-demand reconciliation and a durable background worker backed by Spanner. It does not provide member command creation or wallet custody. `writesAuthorized` remains false; Mainnet writes remain disabled.

## Configure

1. Apply the repository migrations through V013 before enabling the store and outbox dispatcher (the chain worker itself requires V012). Startup refuses a configured database that is unavailable or missing the new schema. No database migrations or GKE deployments are performed by this change.
2. Configure `SPANNER_PROJECT_ID`, `SPANNER_INSTANCE_ID`, `SPANNER_DATABASE_ID`, `ENVIRONMENT` and a secret-manager `CHAIN_SERVICE_TOKEN` (at least 32 characters). The environment must match the gateway/domain deployment. Use a separate database for production; the production chain service refuses a Spanner emulator.
3. Set `CHAIN_SERVICE_URL` and the same `CHAIN_SERVICE_TOKEN` on the gateway. The gateway sends its verified internal member ID; incoming caller subject headers and bearer tokens are never forwarded. Restrict direct service access with the deployment's private network and TLS policy.
4. The read-only worker starts automatically when the store, contract and network endpoints are configured. `CHAIN_RECONCILIATION_ENABLED=false` pauses background work without disabling authenticated status or on-demand reconciliation. Mainnet workers are disabled. Use a separate database per environment because rights projections are keyed by network/contract/entitlement.
5. Configure `MIDNIGHT_NETWORK`, the matching deployed `MIDNIGHT_CONTRACT_ADDRESS`, and `MIDNIGHT_BLOCKFROST_PROJECT_ID` for Preprod. No token or wallet seed belongs in source, browser configuration or evidence reports.

The internal routes are `GET /midnight/operations/:id` and `POST /midnight/operations/reconcile`. The gateway exposes these through the existing v1 status/submission routes. Other members receive 404. Reconciliation accepts only a transaction identifier already bound by the submitter; it never attaches an arbitrary caller-reported transaction to an operation.

## Persistence and recovery

`RightsAdapter` accepts a `SpannerOperationStore` and the authenticated `ownerRef`. A future command service must authorize the specific entitlement/command before constructing the adapter; the store is not a replacement for domain authorization. Member secrets remain in the encrypted, account-scoped private-state provider, never in Spanner or the HTTP service.

- Idempotency is scoped to environment, owner, network and contract. The v2 request digest also commits to the owner and subject. Old v1 rows cannot be silently executed under this binding.
- Subject locks serialize conflicting operations across members. Every update validates the immutable request and uses a version compare-and-set.
- The balanced ledger transaction supplies a real identifier. It is persisted in `Reconciling` before broadcast. Only an acknowledged broadcast becomes `Submitted`. A timeout, process exit or unknown provider result cannot authorize another submission. A process exit before broadcast may leave a pending record requiring operator investigation; absence from one indexer query is not proof of failure.
- Reconciliation has no wallet or prover. It makes a bounded indexer query and verifies the persisted identifier, then verifies the observed block against the node's canonical finalized chain. Neither successful nor rejected observations become terminal without finality. Concurrent/repeated calls use the same compare-and-set.
- Observed/finalized journal updates and `chain.operation.observed` outbox events commit in one transaction. The worker separately reads the compiled contract ledger at the exact observed block, rechecks canonical finality, and projects public entitlement facts. Projection, its registered `rights.entitlement.projected` outbox event, and the durable completion marker commit atomically. Neither event establishes physical ownership.
- `rights.operations` exports member operation history without circuit arguments. Deletion freezes block new commands and the pre-broadcast commit. Unsubmitted history can be erased; unresolved broadcasts and unfinished public projections keep operation-history deletion pending, and a restore refuses to serve unresolved restored operations. Public ledger commitments remain non-erasable.

## Background reconciliation and projection

Each replica claims one due operation at a time using a database-clock lease, processing at most ten per batch. A 15-second poll and persisted exponential retry delay (capped at 15 minutes) avoid tight loops. Expired leases recover after a process exit; a stale worker cannot commit a projection or release a replacement lease. Provider messages and credential-bearing URLs never enter retry records or logs. The worker has no wallet, prover or resubmission capability.

The bounded indexer request uses the pinned Midnight.js contract-action block offset, checked against the [official v4 schema](https://github.com/midnightntwrk/midnight-indexer/blob/main/indexer-api/graphql/schema-v4.graphql) and [block-hash lookup implementation](https://github.com/midnightntwrk/midnight-indexer/blob/main/indexer-api/src/infra/storage/contract_action.rs). The returned contract address and transaction block must match the persisted evidence. The compiled runtime decodes the serialized ledger, and its network tag must match the configured network. Contract-derived IDs select issuance, accepted-transfer, revocation and manufactured-child entitlements. Unknown circuits or malformed/missing ledger state remain pending for investigation; they are not silently marked complete. Indexer/RPC providers are trusted read dependencies; this is not independent cryptographic verification of an indexer state proof. A ledger/protocol upgrade or state response above the 8 MiB bound fails closed and needs an explicit adapter upgrade.

Projection is monotonic in block height and epoch; conflicting facts at one block, epoch decreases and revoked-to-active changes are rejected. Repeated/stale work emits no duplicate projection event. The worker never creates a controller/member or asset link from an operation owner, subject or public commitment. An existing controller link is retained only within the same active epoch and cleared on transfer/revocation; concurrent privacy erasure wins through the database transaction. This worker covers locally journaled operations, not arbitrary external wallet transactions. A full contract history/replay consumer is still required. The [durable Pub/Sub dispatcher](../brandme_core/events/README.md) supplies outbox transport for registered rights/chain/privacy contracts. Provisioned topics/subscriptions and authenticated consumers remain required; broker acceptance is not a completed business effect.

## Verification

Run `pnpm --filter @brandme/chain test` for local contract/adapter/HTTP tests. Run `SPANNER_EMULATOR_HOST=localhost:9010 pnpm --filter @brandme/chain test:spanner` with Python dependencies from `scripts/python/requirements.lock`; `BRANDME_PYTHON` can select a virtual environment. The emulator tests apply the actual migration chain and verify restart recovery, request scoping, concurrent idempotency/subject locking, compare-and-set, outbox events, deletion freezes/tombstones, leased-worker races, projection/event atomicity, compiled-ledger decoding, event-schema/aggregate-ID compatibility with the Python registry, and automatic startup/shutdown of a real service process. The runtime test uses deterministic local HTTP read providers; it does not claim a funded-network run. CI runs this as a separate blocking Chain Service Tests job, with no skip when the emulator is absent.

## Still required

The [authenticated read service](../brandme_core/read_api/README.md) now serves
member entitlements, reprint status, claim-level passports, partial My Data
inventory and deletion status through the gateway. It has no command execution
capability and does not establish funded-network evidence. Deployment remains
required.

- A member wallet/session flow that journals client-proven operations (`offerTransfer`, `acceptTransfer`, `proveControl`) in this durable store before broadcast and keeps witnesses local. The [rights command service](../brandme_core/rights_commands/README.md) now authorizes and records the domain side: transfer intents with a recipient commitment bound through a private invite, the exact `offerTransfer` arguments, reprint quotes and challenge authorization. It does not journal operations. There is deliberately no raw circuit-execution HTTP endpoint.
- Deploy the outbox dispatcher with scoped Pub/Sub topics/subscriptions and authenticated downstream handlers; align the remaining domain catalogs. Contract-wide history ingestion/replay, including transactions outside this operation journal, remains required. The chain worker handles only the configured contract and its owned, durable operations.
- Rights/ownership command backend and full My Data service composition, including registration of real handlers for the remaining domains, authenticated export storage, and processing guards for all writers. The [My Data recovery library](../brandme_core/domains/privacy/README.md) now preserves pending cleanup and overlapping freezes, blocks incomplete restores, and supports resuming a specific restore run. It still requires serialized deletion execution, a preserved tombstone ledger and authenticated command composition; these safeguards are not a claim that account deletion is complete.
- Deployment configuration and migration verification in the target environment.
- Funded-wallet Preprod execution and evidence, using distinct test wallets, a Preprod Blockfrost credential, tNIGHT/DUST and a compatible prover. Local tests and emulator checks do not substitute for this. Mainnet writes remain disabled.
