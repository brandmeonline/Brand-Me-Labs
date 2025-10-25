# Blockchain SDK Integration Guide

**Copyright (c) Brand.Me, Inc. All rights reserved.**

## Overview

This document provides comprehensive documentation for the Cardano and Midnight blockchain SDK integration in the Brand.Me Chain Service.

---

## Cardano Integration

### SDK Used

- **@emurgo/cardano-serialization-lib-nodejs**: Transaction building and signing
- **@blockfrost/blockfrost-js**: Blockchain queries and transaction submission
- **bip39**: Mnemonic phrase handling for HD wallets

### Features Implemented

✅ **Wallet Management** (`cardano-wallet.ts`)
- HD wallet derivation from mnemonic (BIP39/BIP32)
- Support for both mnemonic and raw private key
- Secure key handling (never logged)
- Address generation (Base Address with payment + stake credentials)

✅ **Transaction Builder** (`cardano-tx-builder.ts`)
- Real transaction construction using cardano-serialization-lib
- Transaction metadata (Label 1967: Brand.Me provenance)
- UTXO management via Blockfrost API
- Automatic fee calculation
- Transaction signing with wallet private key
- Submission to Cardano network via Blockfrost

✅ **On-Chain Verification**
- Transaction confirmation queries
- Metadata retrieval
- Block height verification

### Transaction Metadata Structure

Brand.Me uses **Metadata Label 1967** for provenance data:

```json
{
  "scan_id": "uuid",
  "garment_id": "uuid",
  "timestamp": "ISO8601",
  "provenance": {
    "creator": {
      "creator_id": "uuid",
      "creator_name": "string",
      "created_at": "ISO8601"
    },
    "authenticity": {
      "hash": "sha256",
      "verified": true
    },
    "esg": {
      "score": "A+",
      "details": {}
    }
  },
  "scope": "public",
  "policy_version": "sha256",
  "version": "1.0.0",
  "protocol": "Brand.Me-Provenance-v1"
}
```

### Setup Instructions

#### 1. Get Blockfrost API Key

```bash
# Sign up at https://blockfrost.io (free tier available)
# Create a project for your target network (mainnet/testnet/preprod)
# Copy the project ID
```

#### 2. Generate or Import Wallet

**Option A: Generate New Wallet**

```bash
# Install cardano-cli (or use any BIP39 tool)
cardano-cli address key-gen \
  --verification-key-file payment.vkey \
  --signing-key-file payment.skey

# Generate mnemonic (24 words)
# Save securely in /secrets/cardano-mnemonic.txt
```

**Option B: Use Existing Mnemonic**

```bash
# If you have an existing wallet (Daedalus, Yoroi, etc.)
# Extract the 24-word mnemonic phrase
# Save it to /secrets/cardano-mnemonic.txt
```

#### 3. Fund Wallet (Testnet)

```bash
# Get your wallet address from logs when service starts
# Visit https://docs.cardano.org/cardano-testnet/tools/faucet/
# Request testnet ADA (tADA) to your address
# Wait for confirmation (usually 20 seconds)
```

#### 4. Configure Environment

```bash
CARDANO_NETWORK=preprod
CARDANO_MNEMONIC_PATH=/secrets/cardano-mnemonic.txt
BLOCKFROST_API_KEY=preprodXXXXXXXXXXXXXXXX
CARDANO_FALLBACK_MODE=false
```

### Transaction Flow

```
1. Service receives anchor request
   ↓
2. CardanoTxBuilder.buildProvenanceTx()
   ↓
3. Query UTXOs via Blockfrost
   ↓
4. Build transaction body with metadata
   ↓
5. Sign with wallet private key
   ↓
6. Submit to Cardano via Blockfrost
   ↓
7. Return transaction hash
```

### Verification

```typescript
// Verify transaction on chain
const txHash = 'abc123...';
const isConfirmed = await verifyCardanoTx(txHash);

// Get transaction metadata
const txBuilder = getCardanoTxBuilder();
const metadata = await txBuilder.getTransactionMetadata(txHash);
console.log(metadata); // Brand.Me provenance data
```

### Network Fees

| Network | Typical Fee | Source |
|---------|------------|--------|
| Mainnet | ~0.17 ADA | Actual transaction |
| Testnet | ~0.17 tADA | Free from faucet |
| Preprod | ~0.17 ADA | Free from faucet |

---

## Midnight Integration

### Current Status

⚠️ **Midnight SDK is in development by IOG (Input Output Global)**

The integration architecture is **future-ready** and will be updated when the official SDK is released.

### Architecture Implemented

✅ **Midnight Client** (`midnight-client.ts`)
- Shielded transaction builder (stub)
- Zero-knowledge proof generation (placeholder)
- Encrypted data storage (placeholder)
- Controlled reveal mechanism (dual approval)
- Cross-chain anchoring

### What's Ready

```typescript
// Interface is production-ready
const midnightClient = getMidnightClient();

// Build shielded transaction (currently simulated)
const txHash = await midnightClient.buildShieldedTx({
  scanId: 'uuid',
  garmentId: 'uuid',
  scope: 'private',
  facets: [...],
  policyVersion: 'sha256',
  ownership: { ... },  // Will be encrypted
  pricing: { ... },    // Will be encrypted
  consent: { ... }     // Consent snapshot
});

// When SDK is released, this will create real zk-SNARK transactions
```

### Features (When SDK is Available)

🔮 **Planned Features**:
- Zero-knowledge proofs for privacy-preserving transactions
- Shielded transactions hiding ownership/pricing data
- Selective reveal with dual approval (governance + compliance)
- Cross-chain verification with Cardano
- Private smart contracts

### Integration Checklist

When Midnight SDK is released:

- [ ] Replace `midnight-client.ts` stub with real SDK
- [ ] Implement actual zero-knowledge proof generation
- [ ] Add real encryption for private data
- [ ] Update shielded transaction builder
- [ ] Implement cross-chain bridge
- [ ] Add controlled reveal with zk-proofs
- [ ] Update tests with real chain integration

---

## Cross-Chain Architecture

### Cross-Chain Root Hash

Brand.Me creates a cryptographic link between Cardano and Midnight:

```typescript
const rootHash = computeCrossChainRootHash(
  cardanoTxHash,    // Public provenance on Cardano
  midnightTxHash,   // Private data on Midnight
  scanId            // Unique scan identifier
);

// rootHash = SHA256(cardanoTx:midnightTx:scanId)
```

### Anchoring Flow

```
Scan Event
  ├─→ Cardano: Public Provenance
  │   - Creator attribution
  │   - Authenticity hash
  │   - ESG score
  │
  └─→ Midnight: Private Data (encrypted)
      - Ownership lineage
      - Pricing history
      - Consent snapshot

Cross-Chain Root Hash
  ↓
Stored in audit_log + chain_anchor tables
```

### Verification

```typescript
// Verify cross-chain consistency
const isConsistent = await verifyCrossChainConsistency(rootHash);

// Checks:
// 1. Cardano transaction exists and is confirmed
// 2. Midnight transaction exists and is confirmed
// 3. Root hash matches both chains
```

---

## Development Modes

### Fallback Mode (Development)

When blockchain SDKs are unavailable or fail:

```bash
CARDANO_FALLBACK_MODE=true
MIDNIGHT_FALLBACK_MODE=true
```

**Behavior**:
- Generates simulated transaction hashes
- No actual on-chain submission
- Useful for local development and testing
- All API endpoints work identically

### Production Mode

```bash
CARDANO_FALLBACK_MODE=false
MIDNIGHT_FALLBACK_MODE=false
```

**Behavior**:
- Real transactions submitted to blockchains
- Requires funded wallets
- API keys for Blockfrost (Cardano)
- Throws errors if submission fails

---

## Security

### Wallet Key Management

**NEVER commit wallet keys to git!**

```bash
# ✅ CORRECT: Load from K8s secrets
CARDANO_MNEMONIC_PATH=/secrets/cardano-mnemonic.txt

# ❌ WRONG: Hardcoded in code or .env
CARDANO_MNEMONIC="word1 word2 word3..."
```

### Logging

All loggers automatically redact sensitive fields:

```typescript
// Logger configuration (config/logger.ts)
redact: {
  paths: [
    '*.wallet',
    '*.privateKey',
    '*.secret',
    '*.password',
  ],
  censor: '[REDACTED]',
}
```

### Kubernetes Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: blockchain-secrets
  namespace: brandme
type: Opaque
stringData:
  cardano-mnemonic: |
    word1 word2 word3 ... word24
  blockfrost-api-key: preprodXXXXXXXXXXXXX
  midnight-wallet: |
    <wallet-key-data>
```

Mount as files:

```yaml
volumeMounts:
  - name: blockchain-secrets
    mountPath: /secrets
    readOnly: true
```

---

##API Endpoints

### POST /tx/anchor-scan

Anchor scan event to both blockchains.

**Request**:
```json
{
  "scan_id": "uuid",
  "garment_id": "uuid",
  "allowed_facets": [
    {
      "facet_type": "authenticity",
      "facet_payload_preview": { ... }
    }
  ],
  "resolved_scope": "public",
  "policy_version": "sha256_hash"
}
```

**Response**:
```json
{
  "cardano_tx_hash": "abc123...",
  "midnight_tx_hash": "def456...",
  "crosschain_root_hash": "ghi789..."
}
```

### POST /tx/verify-root

Verify cross-chain root hash.

**Request**:
```json
{
  "crosschain_root_hash": "ghi789..."
}
```

**Response**:
```json
{
  "is_consistent": true
}
```

---

## Testing

### Unit Tests

```bash
pnpm test
```

### Integration Tests (Requires Testnet)

```bash
# Set testnet credentials
export CARDANO_NETWORK=preprod
export BLOCKFROST_API_KEY=preprodXXXX
export CARDANO_MNEMONIC_PATH=./test-wallet-mnemonic.txt

# Run integration tests
pnpm test:integration
```

### Manual Testing

```bash
# Test Cardano transaction
curl -X POST http://localhost:3001/tx/anchor-scan \
  -H "Content-Type: application/json" \
  -d '{
    "scan_id": "test-scan-123",
    "garment_id": "test-garment-456",
    "allowed_facets": [
      {
        "facet_type": "authenticity",
        "facet_payload_preview": {"verified": true}
      }
    ],
    "resolved_scope": "public",
    "policy_version": "test_policy_v1"
  }'

# Check transaction on Cardano explorer
# Preprod: https://preprod.cardanoscan.io/transaction/<tx_hash>
# Mainnet: https://cardanoscan.io/transaction/<tx_hash>
```

---

## Monitoring

### Health Checks

```bash
curl http://localhost:3001/health
```

Returns blockchain connection status:

```json
{
  "status": "ok",
  "timestamp": "2025-10-25T12:00:00.000Z",
  "service": "brandme-chain",
  "cardano": {
    "connected": true,
    "network": "preprod"
  },
  "midnight": {
    "connected": true,
    "network": "testnet",
    "mode": "fallback"
  }
}
```

### Metrics

Key metrics to monitor:

- `cardano_transactions_total`: Total Cardano transactions
- `cardano_transactions_failed`: Failed transactions
- `cardano_average_fee_ada`: Average transaction fee
- `midnight_transactions_total`: Total Midnight transactions
- `cross_chain_anchors_total`: Total cross-chain anchors

---

## Troubleshooting

### "No UTXOs available" Error

**Problem**: Wallet has no ADA
**Solution**: Fund wallet from testnet faucet or transfer ADA

### "Blockfrost API error 403"

**Problem**: Invalid or expired API key
**Solution**: Check BLOCKFROST_API_KEY is correct for your network

### "Invalid mnemonic phrase"

**Problem**: Mnemonic file has wrong format
**Solution**: Ensure 24 words, space-separated, no extra whitespace

### "Transaction too large"

**Problem**: Metadata exceeds Cardano limit
**Solution**: Reduce facet data or split into multiple transactions

---

## Resources

### Cardano
- **Cardano Docs**: https://docs.cardano.org
- **Blockfrost**: https://blockfrost.io
- **Testnet Faucet**: https://docs.cardano.org/cardano-testnet/tools/faucet/
- **Explorer (Mainnet)**: https://cardanoscan.io
- **Explorer (Preprod)**: https://preprod.cardanoscan.io

### Midnight
- **Midnight Website**: https://midnight.network
- **IOG Blog**: https://iohk.io/en/blog
- **Developer Portal**: (Coming soon)

### Tools
- **Cardano CLI**: https://github.com/input-output-hk/cardano-node
- **Serialization Lib**: https://github.com/Emurgo/cardano-serialization-lib

---

## Support

For blockchain integration issues:
- **Internal**: Slack #brandme-blockchain
- **Cardano**: Cardano Stack Exchange, Discord
- **Midnight**: IOG Discord (when available)

---

**Last Updated**: 2025-10-25
**Maintained By**: Brand.Me Blockchain Team
