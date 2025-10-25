/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Midnight Test Mocks
 * ===================
 * Mock implementations for Midnight SDK components
 */

import { MidnightTxData } from '@/services/midnight-client';

/**
 * Sample Midnight transaction data
 */
export const sampleMidnightTxData: MidnightTxData = {
  scanId: 'test-scan-123',
  garmentId: 'test-garment-456',
  scope: 'private',
  facets: [
    {
      facet_type: 'ownership',
      facet_payload_preview: {
        current_owner_id: 'owner-123',
      },
    },
  ],
  policyVersion: 'policy_hash',
  ownership: {
    current_owner_id: 'owner-123',
    ownership_history: ['owner-000', 'owner-123'],
  },
  pricing: {
    price_history: [
      { price: 100, timestamp: '2025-01-01T00:00:00.000Z' },
      { price: 150, timestamp: '2025-10-25T00:00:00.000Z' },
    ],
    current_valuation: 150,
  },
  consent: {
    snapshot: {
      governance_approver: 'approver-1',
      compliance_approver: 'approver-2',
    },
    timestamp: '2025-10-25T12:00:00.000Z',
  },
};

/**
 * Mock Midnight transaction hash
 */
export const MOCK_MIDNIGHT_TX_HASH = 'b'.repeat(64);

/**
 * Mock Midnight transaction response
 */
export const mockMidnightTransaction = {
  tx_hash: MOCK_MIDNIGHT_TX_HASH,
  status: 'confirmed',
  block_height: 12345,
  timestamp: new Date().toISOString(),
  note: 'STUB implementation',
};

/**
 * Mock controlled reveal request
 */
export const mockControlledRevealRequest = {
  reveal_id: 'reveal_' + 'c'.repeat(60),
  tx_hash: MOCK_MIDNIGHT_TX_HASH,
  requester_id: 'requester-123',
  approvals: ['governance-approver', 'compliance-approver'],
  status: 'pending',
  note: 'STUB implementation - requires actual Midnight SDK',
};
