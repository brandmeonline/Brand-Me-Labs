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
