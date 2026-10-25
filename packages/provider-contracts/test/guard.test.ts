import { test } from 'node:test';
import assert from 'node:assert/strict';
import { assertAdapterAllowed, CAPABILITY_NAMES, type AdapterDescriptor } from '../src/index.ts';

const d = (over: Partial<AdapterDescriptor>): AdapterDescriptor => ({
  provider_id: 'fixture-shop', mode: 'simulated', environment: 'demo',
  simulation_label: 'Simulated store — no real order', capabilities: ['cart.create'], ...over,
});

test('production refuses simulated and sandbox adapters', () => {
  assert.throws(() => assertAdapterAllowed('production', d({ environment: 'production' })));
  assert.throws(() => assertAdapterAllowed('production', d({ environment: 'production', mode: 'sandbox' })));
  assert.doesNotThrow(() => assertAdapterAllowed('production', d({ environment: 'production', mode: 'live', simulation_label: null })));
});
test('sandbox refuses simulated adapters', () => {
  assert.throws(() => assertAdapterAllowed('sandbox', d({ environment: 'sandbox' })));
});
test('demo requires a visible label on simulated adapters', () => {
  assert.doesNotThrow(() => assertAdapterAllowed('demo', d({})));
  assert.throws(() => assertAdapterAllowed('demo', d({ simulation_label: ' ' })));
});
test('adapter built for another environment is refused', () => {
  assert.throws(() => assertAdapterAllowed('development', d({ environment: 'demo' })));
});
test('capability list matches chapter 05 (24 names)', () => {
  assert.equal(new Set(CAPABILITY_NAMES).size, 24);
});

test('unlisted capability reads as unsupported, never available', async () => {
  const { canExecute, capabilityOf } = await import('../src/index.ts');
  const p = {
    provider_id: 'fixture-shop', display_name: 'Fixture', environment: 'demo' as const, country_codes: ['US'],
    disclosure: 'Simulated store — no real order',
    capabilities: [
      { name: 'cart.create' as const, state: 'sandbox' as const, reason_code: 'deterministic_local_simulation', last_checked_at: null, evidence_ref: null },
      { name: 'checkout.submit' as const, state: 'suspended' as const, reason_code: 'operator_suspended', last_checked_at: null, evidence_ref: null },
    ],
  };
  assert.equal(canExecute(p, 'cart.create'), true);
  assert.equal(canExecute(p, 'checkout.submit'), false);
  assert.equal(capabilityOf(p, 'orders.webhook').state, 'unsupported');
  assert.equal(canExecute(p, 'orders.webhook'), false);
});
test('a transmitted request is never retryable', async () => {
  const { ProviderError } = await import('../src/index.ts');
  assert.equal(new ProviderError('transient', 'p', 'x').retryable, true);
  assert.equal(new ProviderError('transient', 'p', 'x', null, true).retryable, false);
  const unknown = new ProviderError('outcome_unknown', 'p', 'timed out after send');
  assert.equal(unknown.transmitted, true);
  assert.equal(unknown.retryable, false);
});
