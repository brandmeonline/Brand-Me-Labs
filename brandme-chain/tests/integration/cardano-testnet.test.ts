/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Cardano Testnet Integration Tests
 * ==================================
 * Integration tests against real Cardano testnet
 *
 * IMPORTANT: These tests require:
 * 1. Blockfrost API key (BLOCKFROST_API_KEY)
 * 2. Funded testnet wallet (CARDANO_MNEMONIC_PATH)
 * 3. CARDANO_FALLBACK_MODE=false
 *
 * Run with: INTEGRATION=true pnpm test:integration
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { buildCardanoTx } from '@/services/blockchain';
import { initCardanoWallet, getCardanoWallet } from '@/services/cardano-wallet';
import { initCardanoTxBuilder, getCardanoTxBuilder } from '@/services/cardano-tx-builder';
import { sampleCardanoTxData } from '../mocks/cardano-mocks';

const INTEGRATION_ENABLED = process.env.INTEGRATION === 'true';
const SKIP_MESSAGE = 'Skipping integration test (set INTEGRATION=true to run)';

describe.skipIf(!INTEGRATION_ENABLED)('Cardano Testnet Integration', () => {
  beforeAll(() => {
    const mnemonicPath = process.env.CARDANO_MNEMONIC_PATH;
    const blockfrostKey = process.env.BLOCKFROST_API_KEY;
    const network = (process.env.CARDANO_NETWORK as any) || 'preprod';

    if (!mnemonicPath || !blockfrostKey) {
      throw new Error(
        'Integration tests require CARDANO_MNEMONIC_PATH and BLOCKFROST_API_KEY'
      );
    }

    // Initialize wallet and transaction builder
    initCardanoWallet({
      network,
      mnemonicPath,
    });

    initCardanoTxBuilder(blockfrostKey, network);
  });

  describe('Wallet Operations', () => {
    it('should have initialized wallet with valid address', () => {
      const wallet = getCardanoWallet();
      const address = wallet.getAddress();

      expect(address).toBeDefined();
      expect(address).toMatch(/^addr_test1/); // Testnet address prefix
    });

    it('should query wallet UTXOs', async () => {
      const wallet = getCardanoWallet();
      const txBuilder = getCardanoTxBuilder();
      const address = wallet.getAddress();

      // This will query Blockfrost for real UTXOs
      const utxos = await (txBuilder as any).getUtxos(address);

      expect(Array.isArray(utxos)).toBe(true);

      if (utxos.length === 0) {
        console.warn(
          `⚠️  Wallet ${address} has no UTXOs. Fund it from testnet faucet: https://docs.cardano.org/cardano-testnet/tools/faucet/`
        );
      }
    });
  });

  describe('Transaction Building', () => {
    it('should build real Cardano transaction', async () => {
      const txHash = await buildCardanoTx({
        ...sampleCardanoTxData,
        scanId: `integration-test-${Date.now()}`,
      });

      expect(txHash).toBeDefined();
      expect(typeof txHash).toBe('string');
      expect(txHash.length).toBe(64);

      console.log(`✅ Transaction submitted: ${txHash}`);
      console.log(`🔍 View on explorer: https://preprod.cardanoscan.io/transaction/${txHash}`);
    }, 60000); // 60s timeout for blockchain operations

    it('should verify transaction on chain', async () => {
      // First build and submit a transaction
      const txHash = await buildCardanoTx({
        ...sampleCardanoTxData,
        scanId: `verification-test-${Date.now()}`,
      });

      // Wait a bit for chain confirmation
      await new Promise((resolve) => setTimeout(resolve, 20000)); // 20s

      // Verify the transaction
      const txBuilder = getCardanoTxBuilder();
      const isConfirmed = await txBuilder.verifyTransaction(txHash);

      expect(isConfirmed).toBe(true);
    }, 90000); // 90s timeout

    it('should retrieve transaction metadata', async () => {
      // Build transaction with specific metadata
      const testScanId = `metadata-test-${Date.now()}`;
      const txHash = await buildCardanoTx({
        ...sampleCardanoTxData,
        scanId: testScanId,
      });

      // Wait for confirmation
      await new Promise((resolve) => setTimeout(resolve, 20000));

      // Retrieve metadata
      const txBuilder = getCardanoTxBuilder();
      const metadata = await txBuilder.getTransactionMetadata(txHash);

      expect(metadata).toBeDefined();
      expect(Array.isArray(metadata)).toBe(true);

      // Find Brand.Me metadata (label 1967)
      const brandmeMetadata = metadata.find((m: any) => m.label === '1967');
      expect(brandmeMetadata).toBeDefined();
      expect(brandmeMetadata?.json_metadata?.scan_id).toBe(testScanId);
      expect(brandmeMetadata?.json_metadata?.protocol).toBe('Brand.Me-Provenance-v1');
    }, 90000);
  });

  describe('Fee Estimation', () => {
    it('should calculate transaction fees', async () => {
      const txBuilder = getCardanoTxBuilder();
      const protocolParams = await (txBuilder as any).getProtocolParameters();

      expect(protocolParams).toBeDefined();
      expect(protocolParams.min_fee_a).toBeDefined();
      expect(protocolParams.min_fee_b).toBeDefined();

      console.log(`Min fee per byte: ${protocolParams.min_fee_a}`);
      console.log(`Min fee constant: ${protocolParams.min_fee_b}`);
    });
  });

  describe('Network Health', () => {
    it('should query latest protocol parameters', async () => {
      const txBuilder = getCardanoTxBuilder();
      const params = await (txBuilder as any).getProtocolParameters();

      expect(params).toBeDefined();
      expect(params.max_tx_size).toBeGreaterThan(0);
      expect(params.max_val_size).toBeGreaterThan(0);
      expect(params.coins_per_utxo_size).toBeDefined();
    });
  });
});
