# Durable operation integration

The chain service now provides authenticated status and on-demand reconciliation backed by Spanner. It does not provide member command creation or wallet custody. `writesAuthorized` remains false; Mainnet writes remain disabled.

## Configure

1. Apply the repository migrations through V011 to the target database before enabling the store. Startup refuses a configured database that is unavailable or missing the new schema. No database migrations or GKE deployments are performed by this change.
2. Configure `SPANNER_PROJECT_ID`, `SPANNER_INSTANCE_ID`, `SPANNER_DATABASE_ID`, `ENVIRONMENT` and a secret-manager `CHAIN_SERVICE_TOKEN` (at least 32 characters). The environment must match the gateway/domain deployment. Use a separate database for production; the production chain service refuses a Spanner emulator.
3. Set `CHAIN_SERVICE_URL` and the same `CHAIN_SERVICE_TOKEN` on the gateway. The gateway sends its verified internal member ID; incoming caller subject headers and bearer tokens are never forwarded. Restrict direct service access with the deployment's private network and TLS policy.
4. Configure `MIDNIGHT_NETWORK`, the matching deployed `MIDNIGHT_CONTRACT_ADDRESS`, and `MIDNIGHT_BLOCKFROST_PROJECT_ID` for Preprod. No token or wallet seed belongs in source, browser configuration or evidence reports.

The internal routes are `GET /midnight/operations/:id` and `POST /midnight/operations/reconcile`. The gateway exposes these through the existing v1 status/submission routes. Other members receive 404. Reconciliation accepts only a transaction identifier already bound by the submitter; it never attaches an arbitrary caller-reported transaction to an operation.

## Persistence and recovery

`RightsAdapter` accepts a `SpannerOperationStore` and the authenticated `ownerRef`. A future command service must authorize the specific entitlement/command before constructing the adapter; the store is not a replacement for domain authorization. Member secrets remain in the encrypted, account-scoped private-state provider, never in Spanner or the HTTP service.

- Idempotency is scoped to environment, owner, network and contract. The v2 request digest also commits to the owner and subject. Old v1 rows cannot be silently executed under this binding.
- Subject locks serialize conflicting operations across members. Every update validates the immutable request and uses a version compare-and-set.
- The balanced ledger transaction supplies a real identifier. It is persisted in `Reconciling` before broadcast. Only an acknowledged broadcast becomes `Submitted`. A timeout, process exit or unknown provider result cannot authorize another submission. A process exit before broadcast may leave a pending record requiring operator investigation; absence from one indexer query is not proof of failure.
- Reconciliation has no wallet or prover. It makes a bounded indexer query and verifies the persisted identifier, then verifies the observed block against the node's canonical finalized chain. Neither successful nor rejected observations become terminal without finality. Concurrent/repeated calls use the same compare-and-set.
- Observed/finalized journal updates and `chain.operation.observed` outbox events commit in one transaction. The downstream entitlement projection consumer is still required; these events alone do not update rights or establish physical ownership.
- `rights.operations` exports member operation history without circuit arguments. Deletion freezes block new commands and the pre-broadcast commit. Unsubmitted history can be erased; unresolved broadcasts keep deletion pending, and a restore refuses to serve unresolved restored operations. Public ledger commitments remain non-erasable.

## Verification

Run `pnpm --filter @brandme/chain test` for local contract/adapter/HTTP tests. Run `SPANNER_EMULATOR_HOST=localhost:9010 pnpm --filter @brandme/chain test:spanner` with Python dependencies from `scripts/python/requirements.lock`; `BRANDME_PYTHON` can select a virtual environment. The emulator tests apply the actual migration chain and verify restart recovery, request scoping, concurrent idempotency/subject locking, compare-and-set, outbox events, and deletion freezes/tombstones. CI runs this as a separate blocking Chain Service Tests job, with no skip when the emulator is absent.

## Still required

- Authenticated domain command construction and a member wallet/session flow that injects the durable journal, validates recipient commitments and keeps witnesses local. There is deliberately no raw circuit-execution HTTP endpoint.
- A durable reconciliation scheduler, event delivery, and a verified chain-to-entitlement projection consumer. The current reconciliation endpoint runs on demand.
- Rights/ownership command backend and full My Data service composition, including registration of real handlers for the remaining domains, authenticated export storage, and processing guards for all writers. The new rights operation handler is not a claim that account deletion is complete.
- Deployment configuration and migration verification in the target environment.
- Funded-wallet Preprod execution and evidence, using distinct test wallets, a Preprod Blockfrost credential, tNIGHT/DUST and a compatible prover. Local tests and emulator checks do not substitute for this. Mainnet writes remain disabled.
