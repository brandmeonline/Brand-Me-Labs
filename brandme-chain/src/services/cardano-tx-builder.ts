/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Cardano Transaction Builder
 * ===========================
 *
 * Builds and submits transactions to Cardano blockchain using:
 * - cardano-serialization-lib for transaction construction
 * - Blockfrost API for chain queries and submission
 *
 * Transaction Metadata Structure:
 * - Label 721: NFT metadata standard (CIP-25)
 * - Label 1967: Brand.Me provenance data
 */

import * as CardanoWasm from '@emurgo/cardano-serialization-lib-nodejs';
import { BlockFrostAPI } from '@blockfrost/blockfrost-js';
import { createHash } from 'crypto';
import { logger } from '../config/logger';
import { getCardanoWallet } from './cardano-wallet';

export interface CardanoTxData {
  scanId: string;
  garmentId: string;
  scope: string;
  facets: any[];
  creatorAttribution?: {
    creator_id: string;
    creator_name: string;
    created_at: string;
  };
  authenticity?: {
    hash: string;
    verified: boolean;
  };
  esg?: {
    score: string;
    details: any;
  };
}

export class CardanoTxBuilder {
  private blockfrost: BlockFrostAPI;
  private network: 'mainnet' | 'testnet' | 'preprod' | 'preview';

  constructor(
    blockfrostApiKey: string,
    network: 'mainnet' | 'testnet' | 'preprod' | 'preview' = 'preprod'
  ) {
    this.network = network;
    this.blockfrost = new BlockFrostAPI({
      projectId: blockfrostApiKey,
      network: network === 'mainnet' ? 'mainnet' : network,
    });

    logger.info({ network }, 'Cardano TX Builder initialized');
  }

  /**
   * Build and submit provenance transaction
   */
  async buildProvenanceTx(data: CardanoTxData): Promise<string> {
    try {
      logger.info({ scan_id: data.scanId }, 'Building Cardano provenance transaction');

      const wallet = getCardanoWallet();
      const address = wallet.getAddress();

      // Get UTXOs
      const utxos = await this.getUtxos(address);
      if (utxos.length === 0) {
        throw new Error('No UTXOs available. Wallet needs ADA.');
      }

      // Get protocol parameters
      const protocolParams = await this.getProtocolParameters();

      // Build transaction metadata
      const metadata = this.buildProvenanceMetadata(data);

      // Build transaction
      const txBuilder = this.createTxBuilder(protocolParams);

      // Add metadata
      const auxData = CardanoWasm.AuxiliaryData.new();
      const generalMetadata = CardanoWasm.GeneralTransactionMetadata.new();

      // Add Brand.Me provenance metadata (label 1967)
      const metadataValue = this.jsonToMetadataValue(metadata);
      generalMetadata.insert(
        CardanoWasm.BigNum.from_str('1967'),
        metadataValue
      );

      auxData.set_metadata(generalMetadata);
      txBuilder.set_auxiliary_data(auxData);

      // Add inputs (use first UTXO for simplicity)
      const utxo = utxos[0];
      const input = CardanoWasm.TransactionInput.new(
        CardanoWasm.TransactionHash.from_bytes(Buffer.from(utxo.tx_hash, 'hex')),
        utxo.output_index
      );

      const utxoValue = CardanoWasm.Value.new(
        CardanoWasm.BigNum.from_str(utxo.amount[0].quantity)
      );

      txBuilder.add_input(
        CardanoWasm.Address.from_bech32(address),
        input,
        utxoValue
      );

      // Add output (send back to self minus fee)
      txBuilder.add_change_if_needed(CardanoWasm.Address.from_bech32(address));

      // Build transaction body
      const txBody = txBuilder.build();

      // Sign transaction
      const witnesses = wallet.signTransaction(txBody);

      // Assemble final transaction
      const transaction = CardanoWasm.Transaction.new(
        txBody,
        witnesses,
        auxData
      );

      // Submit transaction
      const txHash = await this.submitTransaction(transaction);

      logger.info({
        scan_id: data.scanId,
        tx_hash: txHash,
      }, 'Cardano transaction submitted successfully');

      return txHash;

    } catch (error) {
      logger.error({ error, scan_id: data.scanId }, 'Failed to build Cardano transaction');
      throw new Error(`Cardano transaction failed: ${error.message}`);
    }
  }

  /**
   * Build provenance metadata following CIP-25 and Brand.Me standards
   */
  private buildProvenanceMetadata(data: CardanoTxData): any {
    return {
      scan_id: data.scanId,
      garment_id: data.garmentId,
      timestamp: new Date().toISOString(),
      provenance: {
        creator: data.creatorAttribution,
        authenticity: data.authenticity,
        esg: data.esg,
      },
      scope: data.scope,
      policy_version: this.computeHash(JSON.stringify(data)),
      version: '1.0.0',
      protocol: 'Brand.Me-Provenance-v1',
    };
  }

  /**
   * Convert JSON to Cardano metadata value
   */
  private jsonToMetadataValue(json: any): CardanoWasm.TransactionMetadatum {
    if (typeof json === 'string') {
      return CardanoWasm.TransactionMetadatum.new_text(json);
    }

    if (typeof json === 'number') {
      return CardanoWasm.TransactionMetadatum.new_int(
        CardanoWasm.Int.new_i32(json)
      );
    }

    if (Array.isArray(json)) {
      const list = CardanoWasm.MetadataList.new();
      for (const item of json) {
        list.add(this.jsonToMetadataValue(item));
      }
      return CardanoWasm.TransactionMetadatum.new_list(list);
    }

    if (typeof json === 'object' && json !== null) {
      const map = CardanoWasm.MetadataMap.new();
      for (const [key, value] of Object.entries(json)) {
        map.insert(
          CardanoWasm.TransactionMetadatum.new_text(key),
          this.jsonToMetadataValue(value)
        );
      }
      return CardanoWasm.TransactionMetadatum.new_map(map);
    }

    throw new Error(`Unsupported metadata type: ${typeof json}`);
  }

  /**
   * Get UTXOs for address
   */
  private async getUtxos(address: string): Promise<any[]> {
    try {
      const utxos = await this.blockfrost.addressesUtxos(address);
      return utxos;
    } catch (error) {
      logger.error({ error, address }, 'Failed to fetch UTXOs');
      return [];
    }
  }

  /**
   * Get protocol parameters
   */
  private async getProtocolParameters(): Promise<any> {
    return await this.blockfrost.epochsLatestParameters();
  }

  /**
   * Create transaction builder with protocol parameters
   */
  private createTxBuilder(protocolParams: any): CardanoWasm.TransactionBuilder {
    const linearFee = CardanoWasm.LinearFee.new(
      CardanoWasm.BigNum.from_str(protocolParams.min_fee_a.toString()),
      CardanoWasm.BigNum.from_str(protocolParams.min_fee_b.toString())
    );

    const txBuilderCfg = CardanoWasm.TransactionBuilderConfigBuilder.new()
      .fee_algo(linearFee)
      .pool_deposit(CardanoWasm.BigNum.from_str(protocolParams.pool_deposit))
      .key_deposit(CardanoWasm.BigNum.from_str(protocolParams.key_deposit))
      .max_value_size(protocolParams.max_val_size)
      .max_tx_size(protocolParams.max_tx_size)
      .coins_per_utxo_byte(CardanoWasm.BigNum.from_str(protocolParams.coins_per_utxo_size))
      .build();

    return CardanoWasm.TransactionBuilder.new(txBuilderCfg);
  }

  /**
   * Submit transaction to Cardano network
   */
  private async submitTransaction(tx: CardanoWasm.Transaction): Promise<string> {
    try {
      const txBytes = tx.to_bytes();
      const txHash = await this.blockfrost.txSubmit(txBytes);
      return txHash;
    } catch (error) {
      logger.error({ error }, 'Failed to submit transaction');
      throw error;
    }
  }

  /**
   * Query transaction by hash
   */
  async getTransaction(txHash: string): Promise<any> {
    try {
      const tx = await this.blockfrost.txs(txHash);
      return tx;
    } catch (error) {
      logger.error({ error, tx_hash: txHash }, 'Failed to query transaction');
      throw error;
    }
  }

  /**
   * Get transaction metadata
   */
  async getTransactionMetadata(txHash: string): Promise<any> {
    try {
      const metadata = await this.blockfrost.txsMetadata(txHash);
      return metadata;
    } catch (error) {
      logger.error({ error, tx_hash: txHash }, 'Failed to query transaction metadata');
      throw error;
    }
  }

  /**
   * Verify transaction on chain
   */
  async verifyTransaction(txHash: string): Promise<boolean> {
    try {
      const tx = await this.getTransaction(txHash);
      // Transaction exists and is confirmed
      return tx && tx.block_height > 0;
    } catch (error) {
      return false;
    }
  }

  /**
   * Helper: Compute SHA256 hash
   */
  private computeHash(data: string): string {
    return createHash('sha256').update(data).digest('hex');
  }
}

// Singleton instance
let cardanoTxBuilderInstance: CardanoTxBuilder | null = null;

/**
 * Initialize Cardano TX Builder
 */
export function initCardanoTxBuilder(
  blockfrostApiKey: string,
  network: 'mainnet' | 'testnet' | 'preprod' | 'preview' = 'preprod'
): CardanoTxBuilder {
  if (!cardanoTxBuilderInstance) {
    cardanoTxBuilderInstance = new CardanoTxBuilder(blockfrostApiKey, network);
  }
  return cardanoTxBuilderInstance;
}

/**
 * Get Cardano TX Builder instance
 */
export function getCardanoTxBuilder(): CardanoTxBuilder {
  if (!cardanoTxBuilderInstance) {
    throw new Error('Cardano TX Builder not initialized');
  }
  return cardanoTxBuilderInstance;
}
