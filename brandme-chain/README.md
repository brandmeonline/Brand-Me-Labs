# brandme-chain

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Blockchain integration service for Cardano and Midnight chains.

## Features

- **TX Builder**: Build and submit transactions to Cardano and Midnight
- **Cross-Chain Verifier**: Verify consistency between chains
- **Wallet Management**: Secure key management via Kubernetes secrets

## API Endpoints

### POST /tx/anchor-scan

Anchor scan event to both blockchains.

**Request**:
```json
{
  "scan_id": "uuid",
  "garment_id": "uuid",
  "allowed_facets": [],
  "resolved_scope": "public",
  "policy_version": "sha256_hash"
}
```

**Response**:
```json
{
  "cardano_tx_hash": "string",
  "midnight_tx_hash": "string",
  "crosschain_root_hash": "string"
}
```

### POST /tx/verify-root

Verify cross-chain root hash consistency.

**Request**:
```json
{
  "crosschain_root_hash": "string"
}
```

**Response**:
```json
{
  "is_consistent": true
}
```

## Development

```bash
# Install dependencies
pnpm install

# Run development server
pnpm dev

# Build
pnpm build

# Start production
pnpm start
```

## Security

- **Wallet keys stored only in Kubernetes secrets**
- **No plaintext keys in repository**
- **No logging of private keys**
- **All transactions are logged (hashes only)**

## Blockchain Integration

### Cardano
- Public provenance data
- Creator attribution
- ESG proof hash
- Authenticity verification

### Midnight
- Private ownership lineage
- Pricing history
- Consent snapshots
- Permissioned data access

### Cross-Chain Verification
- Generates cryptographic link between chains
- Anchors Midnight state hash to Cardano
- Enables verifiable privacy-preserving proofs

## License

Copyright (c) Brand.Me, Inc. All rights reserved.
