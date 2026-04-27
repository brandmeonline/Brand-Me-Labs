/**
 * Cardano wallet bootstrap shim.
 * Keeps startup wiring stable while wallet logic lives in tx-builder service.
 */

import { logger } from '../config/logger';

export interface CardanoWalletConfig {
  network: string;
  mnemonicPath?: string;
  privateKeyPath?: string;
}

export function initCardanoWallet(config: CardanoWalletConfig): void {
  logger.info({
    event: 'cardano_wallet_init',
    network: config.network,
    has_mnemonic: Boolean(config.mnemonicPath),
    has_private_key: Boolean(config.privateKeyPath),
  }, 'Cardano wallet initialization configured');
}
