# brandme_rights — contract design and privacy statement

Source: `contracts/src/brandme_rights.compact` · compiler `compactc 0.31.1` (language 0.23.0, runtime 0.16.0) · hashes in `artifact-manifest.json`.

**Status:** locally tested (constraint, property, adversarial suites). **Not externally audited.** Not deployed to Mainnet. Ch.04 requires protocol/contract review before valuable rights are issued; that review has not happened.

## Why one contract, not three

Ch.04 §4 allows the issuer registry, transferable entitlement and licensed reproduction domains to share a deployed contract "only after complexity analysis". Two facts decide it on the pinned tuple:

1. Compact 0.31.1 has no contract-to-contract calls. `grantReprintAllowance` must read the entitlement's issuer and reprint right, and `consumeReprintAllowance` must prove entitlement control, inside the same verifiable transition. Split contracts would turn these into server-side `if`s, which ch.04 forbids.
2. Circuit sizes stay small after the merge. Each circuit only touches the maps it needs. Proving keys run 2.8–5.2 MB per circuit, so the merge adds no prover cost to the simpler circuits.

## Deployment in two phases (observed constraint)

On the local network (node 1.0.300), a deploy transaction carrying all 15 verifier keys (~37 KB) is rejected with `1010: Invalid Transaction: Transaction would exhaust the block limits`. With 8 keys (~21 KB) it is accepted. `deployRightsContract` therefore:

1. deploys with the 8 core circuits (`DEPLOY_CIRCUITS`);
2. inserts the other 7 keys with signed contract-maintenance transactions (`submitInsertVerifierKeyTx`);
3. runs `findDeployedContract`, which fails unless every on-chain key equals our manifest-verified compiled key.

**Maintenance authority is a governance power.** The deploy's maintenance signing key can insert, remove or replace verifier keys, which changes what the contract accepts. Replacements are visible on chain (never a hidden rewrite), but the key must be held under governance custody. Before any valuable rights are issued, either move it to a multi-party authority or rotate it away (`replaceAuthority`). This is a production gate; nothing in this build relinquishes it automatically.

## Authorization

Every role proves knowledge of a 32-byte secret `s`. The circuit computes `persistentHash([domain, instanceSalt, networkTag, scope, s])` and compares it with the commitment stored on the ledger. Witnesses only supply `s`. A missing secret throws (`MissingWitnessError`), and a wrong one fails `assert`. Nothing in the trust path returns `true`.

| Role | Scope | Stored at |
|---|---|---|
| governance | — | `governanceCommitment` (constructor) |
| issuer | issuerId | `issuers[issuerId].authCommitment` |
| manufacturer | manufacturerId | `manufacturers[id].authCommitment` |
| holder | entitlementId + epoch | `entitlements[id].controllerCommitment` |

The holder commitment includes the epoch. After a transfer the old holder's secret no longer matches anything, and the recipient's commitment is computed for `epoch + 1`, so it is only valid once the old control is consumed.

## Public ledger vs private state

| Item | Where | Notes |
|---|---|---|
| issuer/manufacturer/entitlement/offer/allowance ids | public | random 32-byte values chosen off-chain; never derived from names, SKUs, emails or GTINs |
| asset commitment, policy/terms/design/evidence digests | public | digests of documents held in restricted off-chain storage. Callers MUST blind low-entropy inputs with a random salt before hashing (the adapter's `blindedDigest` does this) |
| controller / recipient commitments | public | hash of a fresh random per-entitlement secret, so commitments are unlinkable across entitlements |
| epoch, status, quota, quantities, expiry times | public | needed to enforce invariants |
| role and holder secrets | private state only | encrypted, account-scoped local storage (level provider, password-derived key). Never sent to the application backend |
| instance salt, network tag | public (sealed) | bind every commitment to one deployment and one network |

### Linkability (stated plainly)

- An entitlement's lifecycle is publicly linkable by its id: issuance, each transfer (epoch bump), each `proveControl`, and each reprint consumption. The holder behind each epoch is hidden. The fact that "this entitlement moved" is not.
- `proveControl` records `hash(entitlementId, epoch, challenge, audience)` so a proof cannot be replayed to the same audience. Observers can count proofs per entitlement.
- Transaction timing, fee payer and wallet network metadata are visible to the network and are **not** hidden by this contract. Ch.04 §2 warns about these links, and they apply here.

## Who sees witness inputs

| Proving mode | Who sees holder/issuer secrets |
|---|---|
| Local proof server (`midnightntwrk/proof-server:8.1.0` on the user's machine or companion) | Only that machine |
| Wallet-provided proving through the DApp connector | The wallet/prover the user selected |
| Remote/managed prover | **The prover operator sees every witness input.** Requires a separate disclosure naming the operator plus explicit consent (ch.04 §3). Not enabled, and never a silent fallback |

## Invariant → enforcement map (ch.04 §4)

| # | Invariant | Enforced by | Test |
|---|---|---|---|
| 1 | one active controller per epoch | `assertController` + single `controllerCommitment` per entitlement | property suite (controller count ≤ 1 after every step) |
| 2 | offer completes once, incl. concurrent | `offer.state == open`, `epoch == senderEpoch`, epoch bump in `acceptTransfer` | constraints: concurrent offers, re-accept |
| 3 | no cross network/contract/right/epoch/audience replay | salt + network tag in every commitment; epoch in holder commitment; `usedChallenges` | constraints: cross-network binding, challenge replay |
| 4 | no issuance beyond policy | `issued < maxIssuance` | constraints: cap |
| 5 | reprint quota consumed once | nullifier `hash(allowance, job)` checked first; `remaining` only decreases | constraints + callback-storm property |
| 6 | revoked/expired issuer cannot mint | `active`, `blockTimeLt(validUntil)` in `assertIssuer` | constraints |
| 7 | zero/negative/overflow/malformed fail | explicit asserts; `Uint<32>` range checks in runtime | constraints |
| 8 | failed proof does not advance state | ledger atomicity; adapter only projects observed chain state | simulator `attempt()` asserts byte-identical state; adapter tests |
| 9 | projections cannot make chain state valid | projection reads chain → never writes | adapter design (`operations.ts`) |
| 10 | privacy statement matches ledger | this document | review |

## Not implemented in the contract (by design)

- Physical possession, NFC tag verification, ESG claims and payment status are kept out of the contract (ch.04 §6–7).
- Off-chain signed transfer offers. Offers are on-chain records.
- Custodial mode.
