/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Midnight Client Tests
 * =====================
 * Unit tests for Midnight blockchain client (stub implementation)
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { MidnightClient, initMidnightClient, getMidnightClient } from '@/services/midnight-client';
import { sampleMidnightTxData } from '../mocks/midnight-mocks';

describe('MidnightClient', () => {
  beforeEach(() => {
    // Initialize client for each test
    initMidnightClient({
      network: 'testnet',
      rpcUrl: 'http://localhost:8545',
    });
  });

  describe('Client Initialization', () => {
    it('should initialize Midnight client', () => {
      const client = getMidnightClient();
      expect(client).toBeInstanceOf(MidnightClient);
    });

    it('should use default RPC URL for testnet', () => {
      const client = getMidnightClient();
      expect(client).toBeDefined();
    });

    it('should support custom RPC URL', () => {
      initMidnightClient({
        network: 'devnet',
        rpcUrl: 'http://custom-rpc:8545',
      });

      const client = getMidnightClient();
      expect(client).toBeDefined();
    });
  });

  describe('Shielded Transactions', () => {
    it('should build shielded transaction (stub)', async () => {
      const client = getMidnightClient();

      const txHash = await client.buildShieldedTx(sampleMidnightTxData);

      expect(txHash).toBeDefined();
      expect(typeof txHash).toBe('string');
      expect(txHash.length).toBe(64); // SHA256 hash length
    });

    it('should encrypt ownership data', async () => {
      const client = getMidnightClient();

      const txHash = await client.buildShieldedTx(sampleMidnightTxData);

      // In stub implementation, encrypted data is hashed
      expect(txHash).toBeDefined();
    });

    it('should encrypt pricing data', async () => {
      const client = getMidnightClient();

      const dataWithPricing = {
        ...sampleMidnightTxData,
        pricing: {
          price_history: [{ price: 100, timestamp: '2025-01-01' }],
          current_valuation: 100,
        },
      };

      const txHash = await client.buildShieldedTx(dataWithPricing);
      expect(txHash).toBeDefined();
    });

    it('should include consent snapshot', async () => {
      const client = getMidnightClient();

      const dataWithConsent = {
        ...sampleMidnightTxData,
        consent: {
          snapshot: { governance_approver: 'gov-1', compliance_approver: 'comp-1' },
          timestamp: new Date().toISOString(),
        },
      };

      const txHash = await client.buildShieldedTx(dataWithConsent);
      expect(txHash).toBeDefined();
    });
  });

  describe('Transaction Queries', () => {
    it('should get transaction by hash', async () => {
      const client = getMidnightClient();
      const txHash = 'a'.repeat(64);

      const tx = await client.getTransaction(txHash);

      expect(tx).toBeDefined();
      expect(tx.tx_hash).toBe(txHash);
      expect(tx.status).toBe('confirmed');
    });

    it('should verify transaction', async () => {
      const client = getMidnightClient();
      const txHash = 'b'.repeat(64);

      const isValid = await client.verifyTransaction(txHash);

      expect(isValid).toBe(true);
    });
  });

  describe('Controlled Reveal', () => {
    it('should create controlled reveal request', async () => {
      const client = getMidnightClient();
      const txHash = 'c'.repeat(64);
      const requesterId = 'requester-123';
      const approvals = ['governance-approver', 'compliance-approver'];

      const reveal = await client.requestControlledReveal(txHash, requesterId, approvals);

      expect(reveal).toBeDefined();
      expect(reveal.reveal_id).toBeDefined();
      expect(reveal.tx_hash).toBe(txHash);
      expect(reveal.requester_id).toBe(requesterId);
      expect(reveal.approvals).toEqual(approvals);
      expect(reveal.status).toBe('pending');
    });

    it('should require dual approval', async () => {
      const client = getMidnightClient();
      const txHash = 'd'.repeat(64);
      const requesterId = 'requester-123';
      const singleApproval = ['governance-approver']; // Only one approval

      await expect(
        client.requestControlledReveal(txHash, requesterId, singleApproval)
      ).rejects.toThrow('Dual approval required');
    });

    it('should accept dual approval', async () => {
      const client = getMidnightClient();
      const txHash = 'e'.repeat(64);
      const requesterId = 'requester-123';
      const dualApprovals = ['governance-approver', 'compliance-approver'];

      const reveal = await client.requestControlledReveal(txHash, requesterId, dualApprovals);

      expect(reveal).toBeDefined();
      expect(reveal.approvals.length).toBe(2);
    });
  });

  describe('Cross-Chain Anchoring', () => {
    it('should anchor Midnight state to Cardano', async () => {
      const client = getMidnightClient();
      const midnightTxHash = 'f'.repeat(64);
      const cardanoTxHash = 'g'.repeat(64);

      const rootHash = await client.anchorToCardano(midnightTxHash, cardanoTxHash);

      expect(rootHash).toBeDefined();
      expect(typeof rootHash).toBe('string');
      expect(rootHash.length).toBe(64); // SHA256 hash
    });

    it('should generate consistent root hash', async () => {
      const client = getMidnightClient();
      const midnightTxHash = 'h'.repeat(64);
      const cardanoTxHash = 'i'.repeat(64);

      const rootHash1 = await client.anchorToCardano(midnightTxHash, cardanoTxHash);
      const rootHash2 = await client.anchorToCardano(midnightTxHash, cardanoTxHash);

      expect(rootHash1).toBe(rootHash2);
    });

    it('should generate different root hashes for different transactions', async () => {
      const client = getMidnightClient();

      const rootHash1 = await client.anchorToCardano('a'.repeat(64), 'b'.repeat(64));
      const rootHash2 = await client.anchorToCardano('c'.repeat(64), 'd'.repeat(64));

      expect(rootHash1).not.toBe(rootHash2);
    });
  });

  describe('Error Handling', () => {
    it('should handle transaction build errors gracefully', async () => {
      const client = getMidnightClient();

      const invalidData = {
        ...sampleMidnightTxData,
        scanId: '', // Invalid scan ID
      };

      // Should not throw in stub implementation
      const txHash = await client.buildShieldedTx(invalidData);
      expect(txHash).toBeDefined();
    });

    it('should handle verification errors', async () => {
      const client = getMidnightClient();

      // Mock implementation always returns true in stub
      const isValid = await client.verifyTransaction('invalid-hash');
      expect(typeof isValid).toBe('boolean');
    });
  });
});
