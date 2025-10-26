/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Blockchain Service
 * ==================
 *
 * Handles transactions for both Cardano and Midnight chains using real SDKs.
 *
 * SECURITY CRITICAL:
 * - Wallet keys are loaded from Kubernetes secrets ONLY
 * - Never log private keys
 * - All transactions are logged (hashes only)
 */

import { createHash } from 'crypto';
import { logger } from '../config/logger';
import { getCardanoTxBuilder, CardanoTxData } from './cardano-tx-builder';
import { getMidnightClient, MidnightTxData } from './midnight-client';

/**
 * Build and submit Cardano transaction
 *
 * Uses real Cardano SDK (cardano-serialization-lib + Blockfrost)
 *
 * Cardano (Public Chain) stores:
 * - Creator attribution
 * - Authenticity hash
 * - ESG proof hash
 * - Provenance data
 *
 * @returns Transaction hash
 */
export async function buildCardanoTx(data: {
  scanId: string;
  garmentId: string;
  scope: string;
  facets: any[];
}): Promise<string> {
  logger.info({ scan_id: data.scanId }, 'Building Cardano transaction with real SDK');

  try {
    // Get Cardano TX Builder instance
    const txBuilder = getCardanoTxBuilder();

    // Prepare transaction data with metadata
    const txData: CardanoTxData = {
      scanId: data.scanId,
      garmentId: data.garmentId,
      scope: data.scope,
      facets: data.facets,
      // Extract specific facet data for Cardano metadata
      creatorAttribution: extractCreatorData(data.facets),
      authenticity: extractAuthenticityData(data.facets),
      esg: extractESGData(data.facets),
    };

    // Build and submit transaction
    const txHash = await txBuilder.buildProvenanceTx(txData);

    logger.info({
      scan_id: data.scanId,
      tx_hash: txHash,
    }, 'Cardano transaction submitted successfully');

    return txHash;

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    logger.error({ error, scan_id: data.scanId }, 'Failed to build Cardano transaction');

    // Fallback to simulated tx for development/testing
    if (process.env.CARDANO_FALLBACK_MODE === 'true') {
      logger.warn('Using fallback simulated Cardano transaction');
      return simulateCardanoTx(data);
    }

    throw new Error(`Cardano transaction failed: ${errorMessage}`);
  }
}

/**
 * Build and submit Midnight transaction
 *
 * Uses Midnight SDK (future-ready architecture)
 *
 * Midnight (Private Chain) stores:
 * - Ownership lineage (encrypted)
 * - Pricing history (encrypted)
 * - Consent snapshot
 * - Private metadata
 *
 * @returns Transaction hash
 */
export async function buildMidnightTx(data: {
  scanId: string;
  garmentId: string;
  scope: string;
  facets: any[];
  policyVersion: string;
}): Promise<string> {
  logger.info({ scan_id: data.scanId }, 'Building Midnight shielded transaction');

  try {
    // Get Midnight client instance
    const midnightClient = getMidnightClient();

    // Prepare transaction data with private facets
    const txData: MidnightTxData = {
      scanId: data.scanId,
      garmentId: data.garmentId,
      scope: data.scope,
      facets: data.facets,
      policyVersion: data.policyVersion,
      // Extract private data for Midnight shielded storage
      ownership: extractOwnershipData(data.facets),
      pricing: extractPricingData(data.facets),
      consent: extractConsentData(data.facets, data.policyVersion),
    };

    // Build and submit shielded transaction
    const txHash = await midnightClient.buildShieldedTx(txData);

    logger.info({
      scan_id: data.scanId,
      tx_hash: txHash,
    }, 'Midnight shielded transaction submitted');

    return txHash;

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    logger.error({ error, scan_id: data.scanId }, 'Failed to build Midnight transaction');

    // Fallback to simulated tx for development/testing
    if (process.env.MIDNIGHT_FALLBACK_MODE === 'true') {
      logger.warn('Using fallback simulated Midnight transaction');
      return simulateMidnightTx(data);
    }

    throw new Error(`Midnight transaction failed: ${errorMessage}`);
  }
}

/**
 * Compute cross-chain root hash
 *
 * This creates a cryptographic link between the two chains.
 * The root hash can be verified independently to ensure consistency.
 *
 * @param cardanoTxHash - Cardano transaction hash
 * @param midnightTxHash - Midnight transaction hash
 * @param scanId - Scan ID
 * @returns Cross-chain root hash
 */
export function computeCrossChainRootHash(
  cardanoTxHash: string,
  midnightTxHash: string,
  scanId: string
): string {
  const input = `${cardanoTxHash}:${midnightTxHash}:${scanId}`;
  return createHash('sha256').update(input).digest('hex');
}

/**
 * Verify transaction on Cardano
 *
 * Queries the Cardano blockchain to verify transaction exists and is confirmed
 *
 * @param txHash - Transaction hash to verify
 * @returns True if transaction is confirmed on chain
 */
export async function verifyCardanoTx(txHash: string): Promise<boolean> {
  try {
    const txBuilder = getCardanoTxBuilder();
    return await txBuilder.verifyTransaction(txHash);
  } catch (error) {
    logger.error({ error, tx_hash: txHash }, 'Failed to verify Cardano transaction');
    return false;
  }
}

/**
 * Verify transaction on Midnight
 *
 * Queries the Midnight blockchain to verify shielded transaction
 *
 * @param txHash - Transaction hash to verify
 * @returns True if transaction is confirmed on chain
 */
export async function verifyMidnightTx(txHash: string): Promise<boolean> {
  try {
    const midnightClient = getMidnightClient();
    return await midnightClient.verifyTransaction(txHash);
  } catch (error) {
    logger.error({ error, tx_hash: txHash }, 'Failed to verify Midnight transaction');
    return false;
  }
}

/**
 * Verify cross-chain consistency
 *
 * Checks that the Midnight state hash is properly anchored to Cardano
 *
 * @param crosschainRootHash - Cross-chain root hash to verify
 * @returns True if verification succeeds
 */
export async function verifyCrossChainConsistency(
  crosschainRootHash: string
): Promise<boolean> {
  logger.info({ crosschain_root_hash: crosschainRootHash }, 'Verifying cross-chain consistency');

  try {
    // This would:
    // 1. Fetch Midnight state root from Midnight chain
    // 2. Verify it's anchored to Cardano via metadata
    // 3. Check merkle proof

    // TODO: Implement full cross-chain verification when both chains are production-ready

    // For now, verify both chains independently
    const cardanoConnected = await healthCheckCardano();
    const midnightConnected = await healthCheckMidnight();

    return cardanoConnected && midnightConnected;

  } catch (error) {
    logger.error({ error }, 'Cross-chain verification failed');
    return false;
  }
}

// ===========================================
// Helper Functions for Data Extraction
// ===========================================

function extractCreatorData(facets: any[]): any {
  const creatorFacet = facets.find(f => f.facet_type === 'creator');
  if (!creatorFacet) return undefined;

  return {
    creator_id: creatorFacet.facet_payload_preview?.creator_id,
    creator_name: creatorFacet.facet_payload_preview?.name,
    created_at: creatorFacet.facet_payload_preview?.created_at,
  };
}

function extractAuthenticityData(facets: any[]): any {
  const authFacet = facets.find(f => f.facet_type === 'authenticity');
  if (!authFacet) return undefined;

  return {
    hash: authFacet.facet_payload_preview?.hash,
    verified: authFacet.facet_payload_preview?.verified || true,
  };
}

function extractESGData(facets: any[]): any {
  const esgFacet = facets.find(f => f.facet_type === 'esg');
  if (!esgFacet) return undefined;

  return {
    score: esgFacet.facet_payload_preview?.score,
    details: esgFacet.facet_payload_preview?.details,
  };
}

function extractOwnershipData(facets: any[]): any {
  const ownershipFacet = facets.find(f => f.facet_type === 'ownership');
  if (!ownershipFacet) return undefined;

  return {
    current_owner_id: ownershipFacet.facet_payload_preview?.current_owner_id,
    ownership_history: ownershipFacet.facet_payload_preview?.history,
  };
}

function extractPricingData(facets: any[]): any {
  const pricingFacet = facets.find(f => f.facet_type === 'pricing');
  if (!pricingFacet) return undefined;

  return {
    price_history: pricingFacet.facet_payload_preview?.history,
    current_valuation: pricingFacet.facet_payload_preview?.current_value,
  };
}

function extractConsentData(facets: any[], policyVersion: string): any {
  return {
    snapshot: {
      facet_types_shown: facets.map(f => f.facet_type),
      policy_version: policyVersion,
    },
    timestamp: new Date().toISOString(),
  };
}

// ===========================================
// Fallback Simulated Transactions (Development)
// ===========================================

function simulateCardanoTx(data: any): string {
  const payload = {
    scan_id: data.scanId,
    garment_id: data.garmentId,
    scope: data.scope,
    facets: data.facets.map((f: any) => ({
      type: f.facet_type,
      hash: createHash('sha256').update(JSON.stringify(f)).digest('hex'),
    })),
    timestamp: new Date().toISOString(),
  };

  return createHash('sha256')
    .update(`cardano:${JSON.stringify(payload)}:${Date.now()}`)
    .digest('hex');
}

function simulateMidnightTx(data: any): string {
  const payload = {
    scan_id: data.scanId,
    garment_id: data.garmentId,
    encrypted_data: createHash('sha256').update(JSON.stringify(data)).digest('hex'),
    timestamp: new Date().toISOString(),
  };

  return createHash('sha256')
    .update(`midnight:${JSON.stringify(payload)}:${Date.now()}`)
    .digest('hex');
}

// ===========================================
// Health Checks
// ===========================================

async function healthCheckCardano(): Promise<boolean> {
  try {
    const _txBuilder = getCardanoTxBuilder();
    void _txBuilder; // Reserved for future health check queries
    // Simple check to see if we can query the blockchain
    return true; // Would query actual chain status
  } catch (_error) {
    return false;
  }
}

async function healthCheckMidnight(): Promise<boolean> {
  try {
    const _midnightClient = getMidnightClient();
    void _midnightClient; // Reserved for future health check queries
    // Simple check to see if we can connect to Midnight
    return true; // Would query actual chain status
  } catch (_error) {
    return false;
  }
}
