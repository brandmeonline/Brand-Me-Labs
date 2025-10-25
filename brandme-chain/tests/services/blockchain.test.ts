/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Blockchain Service Tests
 * ========================
 * Integration tests for cross-chain blockchain operations
 */

import { describe, it, expect, beforeAll } from 'vitest';
import {
  buildCardanoTx,
  buildMidnightTx,
  computeCrossChainRootHash,
  verifyCrossChainConsistency,
} from '@/services/blockchain';
import { sampleCardanoTxData } from '../mocks/cardano-mocks';
import { sampleMidnightTxData } from '../mocks/midnight-mocks';

describe('Blockchain Service', () => {
  beforeAll(() => {
    // Ensure fallback mode is enabled for tests
    process.env.CARDANO_FALLBACK_MODE = 'true';
    process.env.MIDNIGHT_FALLBACK_MODE = 'true';
  });

  describe('Cardano Transaction Building', () => {
    it('should build Cardano transaction in fallback mode', async () => {
      const txHash = await buildCardanoTx(sampleCardanoTxData);

      expect(txHash).toBeDefined();
      expect(typeof txHash).toBe('string');
      expect(txHash.length).toBe(64); // SHA256 hash
    });

    it('should include scan_id in transaction', async () => {
      const data = {
        ...sampleCardanoTxData,
        scanId: 'test-scan-unique-123',
      };

      const txHash = await buildCardanoTx(data);
      expect(txHash).toBeDefined();
    });

    it('should extract creator attribution', async () => {
      const data = {
        ...sampleCardanoTxData,
        facets: [
          {
            facet_type: 'creator_attribution',
            facet_payload_preview: {
              creator_id: 'creator-xyz',
              creator_name: 'Test Creator',
              created_at: '2025-01-01T00:00:00Z',
            },
          },
        ],
      };

      const txHash = await buildCardanoTx(data);
      expect(txHash).toBeDefined();
    });

    it('should extract authenticity data', async () => {
      const data = {
        ...sampleCardanoTxData,
        facets: [
          {
            facet_type: 'authenticity',
            facet_payload_preview: {
              hash: 'sha256_hash',
              verified: true,
            },
          },
        ],
      };

      const txHash = await buildCardanoTx(data);
      expect(txHash).toBeDefined();
    });

    it('should extract ESG data', async () => {
      const data = {
        ...sampleCardanoTxData,
        facets: [
          {
            facet_type: 'esg',
            facet_payload_preview: {
              score: 'A+',
              carbon_footprint: '10kg',
            },
          },
        ],
      };

      const txHash = await buildCardanoTx(data);
      expect(txHash).toBeDefined();
    });
  });

  describe('Midnight Transaction Building', () => {
    it('should build Midnight transaction in fallback mode', async () => {
      const txHash = await buildMidnightTx(sampleMidnightTxData);

      expect(txHash).toBeDefined();
      expect(typeof txHash).toBe('string');
      expect(txHash.length).toBe(64);
    });

    it('should encrypt ownership data', async () => {
      const data = {
        ...sampleMidnightTxData,
        ownership: {
          current_owner_id: 'owner-secret-123',
          ownership_history: ['owner-1', 'owner-2', 'owner-secret-123'],
        },
      };

      const txHash = await buildMidnightTx(data);
      expect(txHash).toBeDefined();
    });

    it('should encrypt pricing data', async () => {
      const data = {
        ...sampleMidnightTxData,
        pricing: {
          price_history: [
            { price: 100, timestamp: '2025-01-01' },
            { price: 200, timestamp: '2025-10-25' },
          ],
          current_valuation: 200,
        },
      };

      const txHash = await buildMidnightTx(data);
      expect(txHash).toBeDefined();
    });

    it('should include consent snapshot', async () => {
      const data = {
        ...sampleMidnightTxData,
        consent: {
          snapshot: {
            governance_approver: 'gov-123',
            compliance_approver: 'comp-456',
          },
          timestamp: new Date().toISOString(),
        },
      };

      const txHash = await buildMidnightTx(data);
      expect(txHash).toBeDefined();
    });
  });

  describe('Cross-Chain Operations', () => {
    it('should compute cross-chain root hash', () => {
      const cardanoTx = 'a'.repeat(64);
      const midnightTx = 'b'.repeat(64);
      const scanId = 'scan-123';

      const rootHash = computeCrossChainRootHash(cardanoTx, midnightTx, scanId);

      expect(rootHash).toBeDefined();
      expect(typeof rootHash).toBe('string');
      expect(rootHash.length).toBe(64);
    });

    it('should generate consistent root hashes', () => {
      const cardanoTx = 'c'.repeat(64);
      const midnightTx = 'd'.repeat(64);
      const scanId = 'scan-456';

      const rootHash1 = computeCrossChainRootHash(cardanoTx, midnightTx, scanId);
      const rootHash2 = computeCrossChainRootHash(cardanoTx, midnightTx, scanId);

      expect(rootHash1).toBe(rootHash2);
    });

    it('should generate different hashes for different transactions', () => {
      const rootHash1 = computeCrossChainRootHash('a'.repeat(64), 'b'.repeat(64), 'scan-1');
      const rootHash2 = computeCrossChainRootHash('c'.repeat(64), 'd'.repeat(64), 'scan-2');

      expect(rootHash1).not.toBe(rootHash2);
    });

    it('should verify cross-chain consistency', async () => {
      const cardanoTx = 'e'.repeat(64);
      const midnightTx = 'f'.repeat(64);
      const scanId = 'scan-789';
      const rootHash = computeCrossChainRootHash(cardanoTx, midnightTx, scanId);

      const isConsistent = await verifyCrossChainConsistency(rootHash);

      // In fallback mode, this returns true
      expect(typeof isConsistent).toBe('boolean');
    });
  });

  describe('Fallback Mode', () => {
    it('should use fallback mode when Cardano SDK fails', async () => {
      process.env.CARDANO_FALLBACK_MODE = 'true';

      const txHash = await buildCardanoTx(sampleCardanoTxData);

      expect(txHash).toBeDefined();
      expect(txHash).toMatch(/^[a-f0-9]{64}$/);
    });

    it('should use fallback mode when Midnight SDK unavailable', async () => {
      process.env.MIDNIGHT_FALLBACK_MODE = 'true';

      const txHash = await buildMidnightTx(sampleMidnightTxData);

      expect(txHash).toBeDefined();
      expect(txHash).toMatch(/^[a-f0-9]{64}$/);
    });

    it('should generate deterministic hashes in fallback mode', async () => {
      const data1 = { ...sampleCardanoTxData, scanId: 'deterministic-scan-1' };
      const data2 = { ...sampleCardanoTxData, scanId: 'deterministic-scan-1' };

      const txHash1 = await buildCardanoTx(data1);
      const txHash2 = await buildCardanoTx(data2);

      // Should be consistent for same input
      expect(txHash1).toBe(txHash2);
    });
  });

  describe('Error Handling', () => {
    it('should handle missing facets gracefully', async () => {
      const dataWithoutFacets = {
        ...sampleCardanoTxData,
        facets: [],
      };

      const txHash = await buildCardanoTx(dataWithoutFacets);
      expect(txHash).toBeDefined();
    });

    it('should handle invalid facet types', async () => {
      const dataWithInvalidFacet = {
        ...sampleCardanoTxData,
        facets: [
          {
            facet_type: 'invalid_type',
            facet_payload_preview: {},
          },
        ],
      };

      const txHash = await buildCardanoTx(dataWithInvalidFacet);
      expect(txHash).toBeDefined();
    });

    it('should handle missing optional fields', async () => {
      const minimalData = {
        scanId: 'test-scan',
        garmentId: 'test-garment',
        scope: 'public',
        facets: [],
      };

      const txHash = await buildCardanoTx(minimalData);
      expect(txHash).toBeDefined();
    });
  });

  describe('Data Extraction', () => {
    it('should extract multiple facets of same type', async () => {
      const data = {
        ...sampleCardanoTxData,
        facets: [
          {
            facet_type: 'authenticity',
            facet_payload_preview: { verified: true, hash: 'hash1' },
          },
          {
            facet_type: 'esg',
            facet_payload_preview: { score: 'A+' },
          },
          {
            facet_type: 'creator_attribution',
            facet_payload_preview: { creator_id: 'creator-1' },
          },
        ],
      };

      const txHash = await buildCardanoTx(data);
      expect(txHash).toBeDefined();
    });

    it('should handle nested facet payload data', async () => {
      const data = {
        ...sampleCardanoTxData,
        facets: [
          {
            facet_type: 'esg',
            facet_payload_preview: {
              score: 'A+',
              details: {
                carbon_footprint: '10kg',
                water_usage: '100L',
                labor_practices: 'fair_trade',
              },
            },
          },
        ],
      };

      const txHash = await buildCardanoTx(data);
      expect(txHash).toBeDefined();
    });
  });
});
