/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Cardano Test Mocks
 * ==================
 * Mock implementations for Cardano SDK components
 */

import { vi } from 'vitest';

/**
 * Mock Blockfrost API responses
 */
export const mockBlockfrostResponses = {
  // Mock UTXO response
  utxos: [
    {
      tx_hash: 'abc123def456',
      output_index: 0,
      amount: [
        {
          unit: 'lovelace',
          quantity: '10000000', // 10 ADA
        },
      ],
      block: 'block_hash',
      data_hash: null,
    },
  ],

  // Mock protocol parameters
  protocolParameters: {
    min_fee_a: 44,
    min_fee_b: 155381,
    max_tx_size: 16384,
    max_block_header_size: 1100,
    key_deposit: '2000000',
    pool_deposit: '500000000',
    min_pool_cost: '340000000',
    price_mem: 0.0577,
    price_step: 0.0000721,
    max_val_size: 5000,
    collateral_percent: 150,
    max_collateral_inputs: 3,
    coins_per_utxo_size: '4310',
  },

  // Mock transaction response
  transaction: {
    hash: 'tx_hash_123',
    block: 'block_hash_456',
    block_height: 1234567,
    block_time: 1234567890,
    slot: 12345678,
    index: 0,
    output_amount: [
      {
        unit: 'lovelace',
        quantity: '9500000',
      },
    ],
    fees: '500000',
    deposit: '0',
    size: 512,
    invalid_before: null,
    invalid_hereafter: null,
    utxo_count: 2,
    withdrawal_count: 0,
    mir_cert_count: 0,
    delegation_count: 0,
    stake_cert_count: 0,
    pool_update_count: 0,
    pool_retire_count: 0,
    asset_mint_or_burn_count: 0,
    redeemer_count: 0,
    valid_contract: true,
  },

  // Mock metadata response
  metadata: [
    {
      label: '1967',
      json_metadata: {
        scan_id: 'test-scan-123',
        garment_id: 'test-garment-456',
        timestamp: '2025-10-25T12:00:00.000Z',
        provenance: {
          creator: {
            creator_id: 'creator-123',
            creator_name: 'Test Creator',
            created_at: '2025-01-01T00:00:00.000Z',
          },
          authenticity: {
            hash: 'sha256_hash',
            verified: true,
          },
          esg: {
            score: 'A+',
            details: {},
          },
        },
        scope: 'public',
        policy_version: 'policy_hash',
        version: '1.0.0',
        protocol: 'Brand.Me-Provenance-v1',
      },
    },
  ],
};

/**
 * Create mock Blockfrost API
 */
export function createMockBlockfrost() {
  return {
    addressesUtxos: vi.fn().mockResolvedValue(mockBlockfrostResponses.utxos),
    epochsLatestParameters: vi.fn().mockResolvedValue(mockBlockfrostResponses.protocolParameters),
    txSubmit: vi.fn().mockResolvedValue('tx_hash_123'),
    txs: vi.fn().mockResolvedValue(mockBlockfrostResponses.transaction),
    txsMetadata: vi.fn().mockResolvedValue(mockBlockfrostResponses.metadata),
  };
}

/**
 * Test mnemonic phrase (DO NOT USE IN PRODUCTION)
 */
export const TEST_MNEMONIC =
  'test walk nut penalty hip pave soap entry language right filter choice';

/**
 * Test wallet addresses
 */
export const TEST_ADDRESSES = {
  mainnet: 'addr1qx2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzer3n0d3vllmyqwsx5wktcd8cc3sq835lu7drv2xwl2wywfgs68faae',
  testnet: 'addr_test1qz2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzer3n0d3vllmyqwsx5wktcd8cc3sq835lu7drv2xwl2wywfgsxj90mg',
};

/**
 * Mock transaction hash
 */
export const MOCK_TX_HASH = 'a'.repeat(64);

/**
 * Sample transaction data for testing
 */
export const sampleCardanoTxData = {
  scanId: 'test-scan-123',
  garmentId: 'test-garment-456',
  scope: 'public',
  facets: [
    {
      facet_type: 'authenticity',
      facet_payload_preview: {
        verified: true,
        hash: 'sha256_hash',
      },
    },
  ],
  creatorAttribution: {
    creator_id: 'creator-123',
    creator_name: 'Test Creator',
    created_at: '2025-01-01T00:00:00.000Z',
  },
  authenticity: {
    hash: 'sha256_hash',
    verified: true,
  },
  esg: {
    score: 'A+',
    details: {},
  },
};
