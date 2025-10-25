# Testing Guide

**Copyright (c) Brand.Me, Inc. All rights reserved.**

## Overview

This document describes the testing strategy for the Brand.Me Chain Service.

---

## Test Types

### 1. Unit Tests

Test individual components in isolation with mocked dependencies.

**Location**: `tests/services/*.test.ts`

**Coverage**:
- Cardano wallet management
- Midnight client operations
- Transaction building logic
- Cross-chain verification
- Error handling

**Run**:
```bash
pnpm test
```

### 2. Integration Tests

Test against real Cardano testnet with actual blockchain interactions.

**Location**: `tests/integration/*.test.ts`

**Requirements**:
- Blockfrost API key
- Funded testnet wallet
- `INTEGRATION=true` environment variable

**Run**:
```bash
# Set up test wallet first (see below)
export BLOCKFROST_API_KEY=preprodXXXXXXXXXXXXXX
export CARDANO_MNEMONIC_PATH=/path/to/test-wallet-mnemonic.txt
export CARDANO_NETWORK=preprod

# Run integration tests
INTEGRATION=true pnpm test:integration
```

---

## Test Setup

### Unit Tests (No Setup Required)

Unit tests run in **fallback mode** by default and don't require real blockchain connections.

```bash
# Install dependencies
pnpm install

# Run tests
pnpm test

# Run with coverage
pnpm test:coverage

# Run in watch mode
pnpm test:watch
```

### Integration Tests (Requires Setup)

#### Step 1: Get Blockfrost API Key

1. Sign up at https://blockfrost.io (free tier available)
2. Create a project for **Preprod** network
3. Copy the project ID (starts with `preprod...`)

#### Step 2: Generate Test Wallet

**Option A: Generate New Mnemonic**

```bash
# Install cardano-cli (if needed)
# Or use any BIP39 tool to generate 24 words

# Example using Node.js
node -e "const bip39 = require('bip39'); console.log(bip39.generateMnemonic(256))"
```

Save the 24-word mnemonic to a file:
```bash
echo "word1 word2 word3 ... word24" > /tmp/test-wallet-mnemonic.txt
chmod 600 /tmp/test-wallet-mnemonic.txt
```

**Option B: Use Existing Testnet Wallet**

If you have a Daedalus or Yoroi testnet wallet, extract the 24-word mnemonic and save it.

#### Step 3: Fund Test Wallet

```bash
# Run the wallet initialization to get your address
export CARDANO_MNEMONIC_PATH=/tmp/test-wallet-mnemonic.txt
export CARDANO_NETWORK=preprod
export BLOCKFROST_API_KEY=preprodXXXXXXXXXXXXXX

# Start the service to see your wallet address in logs
pnpm dev

# Look for log: "Cardano wallet address: addr_test1..."
```

Visit the Cardano testnet faucet:
- https://docs.cardano.org/cardano-testnet/tools/faucet/
- Enter your `addr_test1...` address
- Request 1000 tADA (testnet ADA)
- Wait ~20 seconds for confirmation

#### Step 4: Run Integration Tests

```bash
# Set environment variables
export BLOCKFROST_API_KEY=preprodXXXXXXXXXXXXXX
export CARDANO_MNEMONIC_PATH=/tmp/test-wallet-mnemonic.txt
export CARDANO_NETWORK=preprod
export CARDANO_FALLBACK_MODE=false

# Run integration tests
INTEGRATION=true pnpm test:integration
```

**Expected Output**:
```
✓ tests/integration/cardano-testnet.test.ts (4)
  ✓ Cardano Testnet Integration
    ✓ should have initialized wallet with valid address
    ✓ should build real Cardano transaction
      ✅ Transaction submitted: abc123def456...
      🔍 View on explorer: https://preprod.cardanoscan.io/transaction/abc123...
    ✓ should verify transaction on chain
    ✓ should retrieve transaction metadata

 Test Files  1 passed (1)
      Tests  4 passed (4)
```

---

## Test Scripts

### Available Commands

```bash
# Run all unit tests
pnpm test

# Run tests in watch mode (auto-rerun on file changes)
pnpm test:watch

# Run tests with coverage report
pnpm test:coverage

# Run integration tests (requires setup)
INTEGRATION=true pnpm test:integration

# Run specific test file
pnpm test cardano-wallet

# Run tests matching pattern
pnpm test --grep "Cardano"
```

### package.json Scripts

Add these to `package.json`:

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "test:integration": "vitest run tests/integration",
    "test:ui": "vitest --ui"
  }
}
```

---

## Test Structure

### Test Organization

```
brandme-chain/
├── tests/
│   ├── setup.ts                        # Global test setup
│   ├── mocks/
│   │   ├── cardano-mocks.ts           # Cardano SDK mocks
│   │   └── midnight-mocks.ts          # Midnight client mocks
│   ├── services/
│   │   ├── cardano-wallet.test.ts     # Wallet management tests
│   │   ├── midnight-client.test.ts    # Midnight client tests
│   │   └── blockchain.test.ts         # Cross-chain tests
│   └── integration/
│       └── cardano-testnet.test.ts    # Real blockchain tests
├── vitest.config.ts
├── .env.test
└── TESTING.md
```

### Mock Data

Test mocks are located in `tests/mocks/`:

- **cardano-mocks.ts**: Mock Blockfrost responses, test mnemonic, sample transaction data
- **midnight-mocks.ts**: Mock Midnight transactions, shielded data

Example usage:
```typescript
import { sampleCardanoTxData, mockBlockfrostResponses } from '../mocks/cardano-mocks';

const txHash = await buildCardanoTx(sampleCardanoTxData);
```

---

## Testing Best Practices

### 1. Use Fallback Mode for Unit Tests

```typescript
beforeAll(() => {
  process.env.CARDANO_FALLBACK_MODE = 'true';
  process.env.MIDNIGHT_FALLBACK_MODE = 'true';
});
```

### 2. Mock External Dependencies

```typescript
vi.mock('@blockfrost/blockfrost-js', () => ({
  BlockFrostAPI: vi.fn().mockImplementation(() => ({
    addressesUtxos: vi.fn().mockResolvedValue([...]),
  })),
}));
```

### 3. Test Error Paths

```typescript
it('should handle transaction failure', async () => {
  mockBlockfrost.txSubmit.mockRejectedValue(new Error('Network error'));

  await expect(buildCardanoTx(data)).rejects.toThrow('Network error');
});
```

### 4. Use Descriptive Test Names

```typescript
// ✅ Good
it('should generate consistent addresses from same mnemonic', ...)

// ❌ Bad
it('test address generation', ...)
```

### 5. Clean Up After Tests

```typescript
afterEach(() => {
  if (existsSync(tempFilePath)) {
    unlinkSync(tempFilePath);
  }
});
```

### 6. Don't Commit Secrets

**NEVER** commit:
- Real mnemonic phrases
- Blockfrost API keys
- Wallet private keys
- Mainnet credentials

Use environment variables or secure vaults.

---

## Continuous Integration

### GitHub Actions

Tests run automatically on:
- Pull requests
- Pushes to main branch
- Nightly builds (integration tests)

**CI Configuration** (`.github/workflows/test.yml`):
```yaml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
      - name: Install dependencies
        run: pnpm install
      - name: Run unit tests
        run: pnpm test:coverage
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  integration-tests:
    runs-on: ubuntu-latest
    # Only run on main branch
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
      - name: Install dependencies
        run: pnpm install
      - name: Run integration tests
        env:
          BLOCKFROST_API_KEY: ${{ secrets.BLOCKFROST_API_KEY_TESTNET }}
          CARDANO_MNEMONIC_PATH: ${{ secrets.CARDANO_TEST_MNEMONIC_PATH }}
          INTEGRATION: true
        run: pnpm test:integration
```

---

## Coverage Requirements

### Target Coverage

- **Statements**: 80%+
- **Branches**: 75%+
- **Functions**: 80%+
- **Lines**: 80%+

### Excluded from Coverage

- Configuration files (`*.config.ts`)
- Type definitions (`*.d.ts`)
- Test files themselves
- External SDK wrappers (Cardano serialization lib)

### View Coverage Report

```bash
pnpm test:coverage

# Open HTML report
open coverage/index.html
```

---

## Debugging Tests

### VS Code Debug Configuration

Add to `.vscode/launch.json`:
```json
{
  "type": "node",
  "request": "launch",
  "name": "Debug Vitest Tests",
  "runtimeExecutable": "pnpm",
  "runtimeArgs": ["test", "--run", "--threads", "false"],
  "console": "integratedTerminal"
}
```

### Debug Specific Test

```bash
# Run single test file with debugging
node --inspect-brk ./node_modules/.bin/vitest run tests/services/cardano-wallet.test.ts
```

### Enable Verbose Logging

```bash
# Set log level to debug
DEBUG=brandme:* pnpm test

# Or in test file
import { logger } from '@/config/logger';
logger.level = 'debug';
```

---

## Troubleshooting

### "No UTXOs available" in Integration Tests

**Problem**: Wallet has no funds

**Solution**:
1. Check wallet address in logs
2. Fund from testnet faucet: https://docs.cardano.org/cardano-testnet/tools/faucet/
3. Wait 20 seconds for confirmation
4. Retry tests

### "Blockfrost API error 403"

**Problem**: Invalid API key

**Solution**:
1. Verify `BLOCKFROST_API_KEY` is correct
2. Ensure key is for correct network (preprod, not mainnet)
3. Check Blockfrost dashboard for quota limits

### "Transaction too large"

**Problem**: Metadata exceeds Cardano limit (16KB)

**Solution**:
1. Reduce facet data in test
2. Split into multiple transactions
3. Use IPFS for large data

### Tests Timeout

**Problem**: Blockchain operations are slow

**Solution**:
1. Increase test timeout: `{ timeout: 60000 }`
2. Use fallback mode for faster tests
3. Check network connectivity

---

## Resources

### Testing Tools

- **Vitest**: https://vitest.dev
- **Vitest UI**: https://vitest.dev/guide/ui.html
- **V8 Coverage**: https://v8.dev/blog/javascript-code-coverage

### Cardano Resources

- **Testnet Faucet**: https://docs.cardano.org/cardano-testnet/tools/faucet/
- **Preprod Explorer**: https://preprod.cardanoscan.io
- **Blockfrost Docs**: https://docs.blockfrost.io

### Support

- **Internal**: Slack #brandme-blockchain
- **Issues**: GitHub Issues

---

**Last Updated**: 2025-10-25
**Maintained By**: Brand.Me Blockchain Team
