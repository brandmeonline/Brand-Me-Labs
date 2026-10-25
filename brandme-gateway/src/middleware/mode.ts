/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Gateway mode guard. Mirrors brandme_core/config.py: sandbox and production
 * fail closed. The gateway's own trust-path component is identity:
 *   - the dev identity provider is a labelled simulation (demo/development only)
 *   - production/sandbox require OIDC issuer + audience (JWKS-verified)
 *   - legacy shared-secret JWT and stub fallback flags are refused outright
 *   - emulator hosts (Spanner, Firestore, Pub/Sub) are refused
 *   - every backend whose *_SERVICE_URL is set needs its service token, and
 *     all configured service tokens must differ (one leaked token must not
 *     authorize several backends)
 */

import type { GatewayConfig } from '../config';

export class ModeGuardError extends Error {
  constructor(public readonly violations: string[], mode: string) {
    super(`BRANDME_MODE=${mode} refuses to boot: ${violations.join('; ')}`);
    this.name = 'ModeGuardError';
  }
}

export const DEV_IDENTITY_ISSUER = 'urn:brandme:dev-identity-provider';
export const DEV_IDENTITY_LABEL = 'Simulated sign-in: fictional test identity, not a verified account';

const STUB_FLAGS = ['ENABLE_STUB_MODE', 'MIDNIGHT_FALLBACK_MODE', 'CARDANO_FALLBACK_MODE', 'ALLOW_STUB_FALLBACK', 'ZK_ALLOW_STUB_FALLBACK'];
const EMULATOR_HOSTS = ['SPANNER_EMULATOR_HOST', 'FIRESTORE_EMULATOR_HOST', 'PUBSUB_EMULATOR_HOST'];
const truthy = (v: string | undefined) => ['1', 'true', 'yes', 'on'].includes(String(v ?? '').trim().toLowerCase());

/** Backend URL → bearer token pairs the gateway sends (services/rights.ts). */
function serviceTokens(cfg: GatewayConfig) {
  return [
    { url: 'RIGHTS_SERVICE_URL', token: 'RIGHTS_SERVICE_TOKEN', urlSet: Boolean(cfg.rightsServiceUrl), value: cfg.rightsServiceToken },
    { url: 'PRIVACY_SERVICE_URL', token: 'PRIVACY_SERVICE_TOKEN', urlSet: Boolean(cfg.privacyServiceUrl), value: cfg.privacyServiceToken },
    { url: 'PRIVACY_EXPORT_SERVICE_URL', token: 'PRIVACY_EXPORT_SERVICE_TOKEN', urlSet: Boolean(cfg.privacyExportServiceUrl), value: cfg.privacyExportServiceToken },
    { url: 'CHAIN_SERVICE_URL', token: 'CHAIN_SERVICE_TOKEN', urlSet: cfg.chainUrlExplicit, value: cfg.chainServiceToken },
  ];
}

export function isStrict(mode: GatewayConfig['mode']): boolean {
  return mode === 'sandbox' || mode === 'production';
}

export function checkGatewayMode(cfg: GatewayConfig, env: NodeJS.ProcessEnv = process.env): string[] {
  const v: string[] = [];
  if (!isStrict(cfg.mode)) {
    if (cfg.identityProvider === 'oidc' && (!cfg.oidcIssuer || !cfg.oidcAudience)) {
      v.push('IDENTITY_PROVIDER=oidc requires OIDC_ISSUER and OIDC_AUDIENCE');
    }
    return v;
  }
  if (cfg.identityProvider !== 'oidc') v.push(`identity provider '${cfg.identityProvider}' is a simulation; set IDENTITY_PROVIDER=oidc`);
  if (!cfg.oidcIssuer) v.push('OIDC_ISSUER is required');
  if (!cfg.oidcAudience) v.push('OIDC_AUDIENCE is required');
  if (cfg.oidcIssuer && !cfg.oidcIssuer.startsWith('https://')) v.push('OIDC_ISSUER must be https');
  // Signing keys fetched over plaintext could be swapped on the path, minting tokens for any subject.
  if (cfg.oidcJwksUri && !cfg.oidcJwksUri.startsWith('https://')) v.push('OIDC_JWKS_URI must be https');
  for (const alg of cfg.oidcAlgorithms) {
    if (!/^(RS|PS|ES)(256|384|512)$|^EdDSA$/.test(alg)) v.push(`OIDC_ALGORITHMS contains disallowed '${alg}' (asymmetric only)`);
  }
  if (env.JWT_SECRET) v.push('JWT_SECRET (shared-secret token verification) is not accepted; use OIDC/JWKS');
  for (const flag of STUB_FLAGS) if (truthy(env[flag])) v.push(`${flag} enables a stub fallback`);
  for (const origin of cfg.publicOrigins) if (!origin.startsWith('https://')) v.push(`PUBLIC_ORIGINS entry '${origin}' must be https`);
  for (const origin of cfg.corsOrigins) if (!origin.startsWith('https://')) v.push(`CORS_ORIGINS entry '${origin}' must be https`);
  for (const name of EMULATOR_HOSTS) if (String(env[name] ?? '').trim()) v.push(`${name} points at a local emulator; strict modes use real services`);
  // Violations name variables only, never token values.
  const tokens = serviceTokens(cfg);
  for (const t of tokens) if (t.urlSet && !t.value) v.push(`${t.token} is required when ${t.url} is set`);
  const configured = tokens.filter((t) => t.value);
  for (let i = 0; i < configured.length; i++) {
    for (let j = i + 1; j < configured.length; j++) {
      if (configured[i].value === configured[j].value) v.push(`${configured[i].token} and ${configured[j].token} must be distinct`);
    }
  }
  return v;
}

export function assertGatewayMode(cfg: GatewayConfig, env: NodeJS.ProcessEnv = process.env): void {
  const violations = checkGatewayMode(cfg, env);
  if (violations.length) throw new ModeGuardError(violations, cfg.mode);
}
