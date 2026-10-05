import { describe, expect, it } from 'vitest';
import { loadConfig } from '../config';
import { checkGatewayMode, assertGatewayMode, ModeGuardError } from './mode';

const prodEnv = {
  BRANDME_MODE: 'production',
  IDENTITY_PROVIDER: 'oidc',
  OIDC_ISSUER: 'https://idp.example.invalid',
  OIDC_AUDIENCE: 'brandme-api',
  PUBLIC_ORIGINS: 'https://app.example.invalid',
  CORS_ORIGINS: 'https://app.example.invalid',
};

describe('gateway mode guard (BM-BASE-002)', () => {
  it('requires BRANDME_MODE', () => {
    expect(() => loadConfig({})).toThrow();
  });

  it('production with the dev identity simulation fails closed', () => {
    const cfg = loadConfig({ ...prodEnv, IDENTITY_PROVIDER: 'dev' });
    expect(() => assertGatewayMode(cfg, {})).toThrow(ModeGuardError);
  });

  it('production without OIDC issuer/audience fails closed', () => {
    const cfg = loadConfig({ BRANDME_MODE: 'production', IDENTITY_PROVIDER: 'oidc' });
    const v = checkGatewayMode(cfg, {});
    expect(v.join(' ')).toMatch(/OIDC_ISSUER/);
    expect(v.join(' ')).toMatch(/OIDC_AUDIENCE/);
  });

  it('production refuses shared-secret JWTs, stub flags, symmetric algorithms and http origins', () => {
    const cfg = loadConfig({ ...prodEnv, OIDC_ALGORITHMS: 'RS256,HS256', PUBLIC_ORIGINS: 'http://localhost:3000' });
    const v = checkGatewayMode(cfg, { JWT_SECRET: 'x'.repeat(40), MIDNIGHT_FALLBACK_MODE: 'true' }).join(' | ');
    expect(v).toMatch(/JWT_SECRET/);
    expect(v).toMatch(/MIDNIGHT_FALLBACK_MODE/);
    expect(v).toMatch(/HS256/);
    expect(v).toMatch(/must be https/);
  });

  it('sandbox applies the same rules', () => {
    expect(checkGatewayMode(loadConfig({ BRANDME_MODE: 'sandbox' }), {}).length).toBeGreaterThan(0);
  });

  it('a correctly configured production gateway passes', () => {
    expect(checkGatewayMode(loadConfig(prodEnv), {})).toEqual([]);
  });

  it('demo/development allow the labelled dev identity provider', () => {
    expect(checkGatewayMode(loadConfig({ BRANDME_MODE: 'demo' }), {})).toEqual([]);
    expect(checkGatewayMode(loadConfig({ BRANDME_MODE: 'development' }), {})).toEqual([]);
  });
});
