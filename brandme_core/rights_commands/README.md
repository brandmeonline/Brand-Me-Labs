# Rights command service

A separate, authenticated HTTP process packaged in the core image, beside the
read-only [read API](../read_api/README.md). It creates transfer intents, binds
a recipient's commitment, evaluates reprint quotes and authorizes
ownership-proof challenges. It never holds a wallet, a witness or a prover, and
never broadcasts a transaction: the member's wallet proves and submits. Domain
rules live in `brandme_core/domains/rights/commands.py`.

| Public gateway path | Backend path | Gateway checks | Service re-checks |
| --- | --- | --- | --- |
| `POST /api/v1/assets/{assetId}/transfers` | `/rights/assets/{assetId}/transfers` | `rights:transfer`, recent auth (10 min), `Idempotency-Key` | scope, recent auth, key |
| `POST /api/v1/transfers/{transferId}/accept` | `/rights/transfers/{transferId}/accept` | `rights:transfer`, recent auth, `Idempotency-Key` | scope, recent auth, key |
| `GET /api/v1/transfers/{transferId}` | `/rights/transfers/{transferId}` | `rights:read` | scope |
| `POST /api/v1/assets/{assetId}/reprint-quotes` | `/rights/assets/{assetId}/reprint-quotes` | `rights:reprint` | scope |
| `POST /api/v1/ownership/challenges` | `/rights/challenges` | `rights:read` | scope |

The two `/transfers` routes are in `brandme-gateway/src/routes/v1/transfers.ts`
and are **not mounted**: the mount file is foundation's (`routes/v1/index.ts`).
Cookie sessions also pass the gateway's CSRF check before any of these calls.

## Transfer flow

1. The sender's app generates a high-entropy invite (43–128 base64url
   characters) and gives it to the recipient privately. The intent stores only
   its SHA-256 digest. The intent fixes the terms the wallet will prove:
   `offerTransfer(entitlementId, nonce, recipientCommitment, expiry, termsDigest)`.
   An open intent holds the entitlement; a second one is refused until it ends.
2. The recipient presents the invite with the commitment their wallet computed
   locally for the next epoch. The intent becomes `ReadyToProve`. A wrong invite
   and a missing intent both return 404.
3. The sender's `GET` view then carries the exact proving arguments. The
   recipient's later `acceptTransfer` proof, observed and finalized on chain,
   is what moves the right. Journaling those client-proven operations in the
   durable store before broadcast is still required (`brandme-chain/INTEGRATION.md`).

Every command checks, in its own transaction: the restore barrier, the privacy
processing guard for both members, the member's single active controlled
entitlement on the configured network and contract, and the entitlement's
current epoch. A projection is evidence of past chain state; the contract
re-checks control, epoch and recipient when the proof lands.

Reprint quotes are read-only and never reserve or consume quota; no price
source exists yet, so `price` is `null` with `price_status: "unavailable"`.
Challenges store nothing: `proveControl` records the challenge key on chain,
which enforces single use. The returned `audience_digest` is the circuit's
`audience` argument, shared by the wallet and the verifier.

## Deploy explicitly

Apply and verify the repository migrations through V016 before startup; the
service checks the migration ledger and the columns it uses, and never applies
migrations. Configure through the deployment and secret manager:

```text
BRANDME_MODE=development
ENVIRONMENT=development
SPANNER_PROJECT_ID=<project>
SPANNER_INSTANCE_ID=<instance>
SPANNER_DATABASE_ID=<database reserved for this environment>
RIGHTS_COMMAND_NETWORK=preprod
RIGHTS_COMMAND_CONTRACT_ADDRESS=<64 lowercase hex characters>
RIGHTS_COMMAND_SERVICE_TOKEN=<independent random service credential, 32–256 characters>
PORT=8000
```

The credential differs from every other rights-lane service credential
(`RIGHTS_SERVICE_TOKEN`, `PRIVACY_SERVICE_TOKEN`, `PRIVACY_EXPORT_SERVICE_TOKEN`,
`CHAIN_SERVICE_TOKEN`); the service refuses an equal value. Configure the
gateway with `RIGHTS_COMMAND_SERVICE_URL` and the same credential. The process
writes only `TransferIntents`, `IdempotencyRecords` and `OutboxEvents`; it reads
the rights projections, the privacy ledger (freezes, deletion jobs, tombstones,
restore runs) and `SchemaMigrations`. Keep the listener private behind
authenticated ingress and TLS. Access logging is off; database errors are never relayed or logged.

```sh
python -m brandme_core.rights_commands --check
python -m brandme_core.rights_commands
```

**Strict modes refuse this process.** It has no audited entry in the shared
trust-path inventory (`brandme_core/config.py`), which is foundation's mode-guard
policy; `brandme_core.boot.guard("rights_commands")` therefore refuses sandbox
and production until that entry exists. There is no Mainnet mode.

## Verification

`tests/test_rights_commands.py` runs the service against the Spanner emulator
with the real migration chain. `brandme-gateway/src/routes/v1/commands-backend.test.ts`
runs signed OIDC through the mounted gateway into the real Python process.
`brandme-gateway/src/routes/v1/v1-routes.test.ts` covers the route checks,
including the unmounted `/transfers` router.
