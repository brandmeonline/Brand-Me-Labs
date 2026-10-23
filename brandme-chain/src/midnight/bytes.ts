/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 */

import { randomBytes as nodeRandomBytes } from 'node:crypto';

export const toHex = (b: Uint8Array): string => Buffer.from(b).toString('hex');

export function fromHex(hex: string, expectedLength?: number): Uint8Array {
  if (!/^(?:[0-9a-f]{2})*$/i.test(hex)) throw new Error('malformed hex');
  const b = new Uint8Array(Buffer.from(hex, 'hex'));
  if (expectedLength !== undefined && b.length !== expectedLength) {
    throw new Error(`expected ${expectedLength} bytes, got ${b.length}`);
  }
  return b;
}

/** 32 cryptographically random bytes (identifiers, nonces, holder secrets). */
export const random32 = (): Uint8Array => new Uint8Array(nodeRandomBytes(32));

export const bytesEqual = (a: Uint8Array, b: Uint8Array): boolean =>
  a.length === b.length && a.every((v, i) => v === b[i]);
