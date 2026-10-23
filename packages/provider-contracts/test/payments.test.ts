import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  assertPaymentRailAllowed, ORDER_PAYMENT_STATUSES, PAYMENT_STATES, RAIL_MODES, type PaymentRailDescriptor,
} from '../src/index.ts';

const rail = (over: Partial<PaymentRailDescriptor>): PaymentRailDescriptor => ({
  processor_id: 'simulated', mode: 'simulated', environment: 'demo', label: 'Simulated payment — no real payment occurs.',
  payee_ref: 'demo-payee', currencies: ['USD'], api_version: null, webhooks_configured: false, ...over,
});

test('production refuses both payment rail modes', () => {
  for (const mode of RAIL_MODES) {
    assert.throws(() => assertPaymentRailAllowed('production', rail({ environment: 'production', mode })));
  }
});
test('sandbox refuses the simulated rail and allows Stripe test mode', () => {
  assert.throws(() => assertPaymentRailAllowed('sandbox', rail({ environment: 'sandbox' })));
  assert.doesNotThrow(() => assertPaymentRailAllowed('sandbox', rail({ environment: 'sandbox', mode: 'sandbox',
    processor_id: 'stripe_test', label: 'Stripe test mode — no real money moves.' })));
});
test('a blank or over-long rail label is refused', () => {
  assert.doesNotThrow(() => assertPaymentRailAllowed('development', rail({ environment: 'development' })));
  assert.throws(() => assertPaymentRailAllowed('demo', rail({ label: '  ' })));
  assert.throws(() => assertPaymentRailAllowed('demo', rail({ label: 'x'.repeat(201) })));
});
test('a rail built for another environment is refused', () => {
  assert.throws(() => assertPaymentRailAllowed('development', rail({ environment: 'demo' })));
});
test('order payment statuses are the seven the order record allows', () => {
  assert.equal(ORDER_PAYMENT_STATUSES.length, 7);
  assert.ok(ORDER_PAYMENT_STATUSES.includes('voided'));
  assert.ok(!(ORDER_PAYMENT_STATUSES as readonly string[]).includes('requires_action'));
  assert.ok(PAYMENT_STATES.includes('requires_action'));
});
