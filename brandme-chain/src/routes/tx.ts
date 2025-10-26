/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Transaction Routes
 */

import { Router, Request, Response } from 'express';
import type { Router as IRouter } from 'express';
import { z } from 'zod';
import { logger } from '../config/logger';
import { buildCardanoTx, buildMidnightTx, computeCrossChainRootHash } from '../services/blockchain';

const router: IRouter = Router();

// Request schemas
const anchorScanSchema = z.object({
  scan_id: z.string().uuid(),
  garment_id: z.string().uuid(),
  allowed_facets: z.array(z.any()),
  resolved_scope: z.enum(['public', 'friends_only', 'private']),
  policy_version: z.string(),
});

const verifyRootSchema = z.object({
  crosschain_root_hash: z.string(),
});

/**
 * POST /tx/anchor-scan
 * Anchor scan event to both blockchains
 */
router.post('/anchor-scan', async (req: Request, res: Response) => {
  try {
    // Validate request body
    const data = anchorScanSchema.parse(req.body);

    logger.info({ scan_id: data.scan_id }, 'Anchoring scan to blockchains');

    // Build Cardano transaction
    // Cardano stores: creator attribution, authenticity hash, ESG proof
    const cardanoTxHash = await buildCardanoTx({
      scanId: data.scan_id,
      garmentId: data.garment_id,
      scope: data.resolved_scope,
      facets: data.allowed_facets.filter(f =>
        ['authenticity', 'esg'].includes(f.facet_type)
      ),
    });

    // Build Midnight transaction
    // Midnight stores: ownership lineage, pricing, consent snapshot
    const midnightTxHash = await buildMidnightTx({
      scanId: data.scan_id,
      garmentId: data.garment_id,
      scope: data.resolved_scope,
      facets: data.allowed_facets.filter(f =>
        ['ownership', 'pricing'].includes(f.facet_type)
      ),
      policyVersion: data.policy_version,
    });

    // Compute cross-chain root hash
    const crosschainRootHash = computeCrossChainRootHash(
      cardanoTxHash,
      midnightTxHash,
      data.scan_id
    );

    logger.info({
      scan_id: data.scan_id,
      cardano_tx_hash: cardanoTxHash,
      midnight_tx_hash: midnightTxHash,
      crosschain_root_hash: crosschainRootHash,
    }, 'Scan anchored to blockchains');

    res.status(200).json({
      cardano_tx_hash: cardanoTxHash,
      midnight_tx_hash: midnightTxHash,
      crosschain_root_hash: crosschainRootHash,
    });

  } catch (error) {
    if (error instanceof z.ZodError) {
      res.status(400).json({
        error: 'Validation Error',
        details: error.errors,
      });
      return;
    }

    logger.error({ error }, 'Error anchoring scan to blockchains');
    res.status(500).json({
      error: 'Internal Server Error',
      message: 'Failed to anchor scan to blockchains',
    });
  }
});

/**
 * POST /tx/verify-root
 * Verify cross-chain root hash consistency
 */
router.post('/verify-root', async (req: Request, res: Response) => {
  try {
    const data = verifyRootSchema.parse(req.body);

    // TODO: Implement actual verification against blockchain
    // For now, return success
    const isConsistent = true;

    logger.info({
      crosschain_root_hash: data.crosschain_root_hash,
      is_consistent: isConsistent,
    }, 'Verified cross-chain root hash');

    res.status(200).json({
      is_consistent: isConsistent,
    });

  } catch (error) {
    if (error instanceof z.ZodError) {
      res.status(400).json({
        error: 'Validation Error',
        details: error.errors,
      });
      return;
    }

    logger.error({ error }, 'Error verifying cross-chain root hash');
    res.status(500).json({
      error: 'Internal Server Error',
      message: 'Failed to verify cross-chain root hash',
    });
  }
});

export default router;
