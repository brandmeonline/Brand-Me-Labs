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

  it('strict modes refuse a plaintext JWKS URI and http CORS origins (unset CORS_ORIGINS defaults to localhost)', () => {
    const v = checkGatewayMode(loadConfig({ ...prodEnv, OIDC_JWKS_URI: 'http://idp.example.invalid/jwks.json', CORS_ORIGINS: 'https://app.example.invalid,http://evil.example.invalid' }), {}).join(' | ');
    expect(v).toMatch(/OIDC_JWKS_URI must be https/);
    expect(v).toMatch(/CORS_ORIGINS entry 'http:\/\/evil.example.invalid' must be https/);
    const withoutCors: Record<string, string> = { ...prodEnv };
    delete withoutCors.CORS_ORIGINS;
    expect(checkGatewayMode(loadConfig(withoutCors), {}).join(' | ')).toMatch(/CORS_ORIGINS entry 'http:\/\/localhost:3000' must be https/);
    expect(checkGatewayMode(loadConfig({ ...prodEnv, OIDC_JWKS_URI: 'https://idp.example.invalid/jwks.json' }), {})).toEqual([]);
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

describe('strict modes: emulators and service tokens', () => {
  const EMULATORS = ['SPANNER_EMULATOR_HOST', 'FIRESTORE_EMULATOR_HOST', 'PUBSUB_EMULATOR_HOST'];
  const BACKENDS = [
    ['RIGHTS_SERVICE_URL', 'RIGHTS_SERVICE_TOKEN'],
    ['PRIVACY_SERVICE_URL', 'PRIVACY_SERVICE_TOKEN'],
    ['PRIVACY_EXPORT_SERVICE_URL', 'PRIVACY_EXPORT_SERVICE_TOKEN'],
    ['CHAIN_SERVICE_URL', 'CHAIN_SERVICE_TOKEN'],
  ] as const;
  const token = (c: string) => `${c}`.repeat(40);
  const guard = (env: Record<string, string>) => checkGatewayMode(loadConfig(env), env);
  const allBackends = Object.fromEntries(BACKENDS.map(([url]) => [url, `https://${url.toLowerCase()}.example.invalid`]));

  it.each(['production', 'sandbox'])('%s refuses each emulator host', (mode) => {
    for (const name of EMULATORS) {
      const v = guard({ ...prodEnv, BRANDME_MODE: mode, [name]: '127.0.0.1:9010' });
      expect(v).toEqual([`${name} points at a local emulator; strict modes use real services`]);
    }
  });

  it('demo/development keep emulator hosts and need no service tokens', () => {
    const env = { ...allBackends, ...Object.fromEntries(EMULATORS.map((n) => [n, '127.0.0.1:1'])) };
    expect(guard({ ...env, BRANDME_MODE: 'development' })).toEqual([]);
    expect(guard({ ...env, BRANDME_MODE: 'demo' })).toEqual([]);
  });

  it('requires the service token of every backend whose URL is set', () => {
    for (const [url, name] of BACKENDS) {
      const env = { ...prodEnv, [url]: 'https://svc.example.invalid' };
      expect(guard(env), url).toEqual([`${name} is required when ${url} is set`]);
      expect(guard({ ...env, [name]: token('a') }), url).toEqual([]);
    }
  });

  it('the default chain URL is not "configured": no chain token required until CHAIN_SERVICE_URL is set', () => {
    expect(loadConfig(prodEnv).chainUrl).toBe('http://localhost:3003');
    expect(guard(prodEnv)).toEqual([]);
  });

  it('requires all configured service tokens to be pairwise distinct, naming variables only', () => {
    const shared = token('s');
    const env = { ...prodEnv, ...allBackends, RIGHTS_SERVICE_TOKEN: shared, PRIVACY_SERVICE_TOKEN: shared, PRIVACY_EXPORT_SERVICE_TOKEN: token('e'), CHAIN_SERVICE_TOKEN: shared };
    const v = guard(env);
    expect(v).toEqual([
      'RIGHTS_SERVICE_TOKEN and PRIVACY_SERVICE_TOKEN must be distinct',
      'RIGHTS_SERVICE_TOKEN and CHAIN_SERVICE_TOKEN must be distinct',
      'PRIVACY_SERVICE_TOKEN and CHAIN_SERVICE_TOKEN must be distinct',
    ]);
    expect(v.join(' ')).not.toContain(shared);
    // Tokens set without their URL still count for distinctness.
    expect(guard({ ...prodEnv, RIGHTS_SERVICE_TOKEN: shared, CHAIN_SERVICE_TOKEN: shared })).toEqual(['RIGHTS_SERVICE_TOKEN and CHAIN_SERVICE_TOKEN must be distinct']);
    const distinct = { ...prodEnv, ...allBackends, RIGHTS_SERVICE_TOKEN: token('r'), PRIVACY_SERVICE_TOKEN: token('p'), PRIVACY_EXPORT_SERVICE_TOKEN: token('e'), CHAIN_SERVICE_TOKEN: token('c') };
    expect(guard(distinct)).toEqual([]);
  });

  it('the boot guard refuses these configurations', () => {
    const env = { ...prodEnv, SPANNER_EMULATOR_HOST: '127.0.0.1:9010', RIGHTS_SERVICE_URL: 'https://r.example.invalid' };
    expect(() => assertGatewayMode(loadConfig(env), env)).toThrow(/SPANNER_EMULATOR_HOST.*RIGHTS_SERVICE_TOKEN is required/);
  });
});
