import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  canVerify, isWellFormedProbe, NON_VERIFYING_EVIDENCE, PROBE_MODES, PROBE_RESULTS, VERIFYING_EVIDENCE,
  type ProbeResult, type VerifiableProvider, type VerificationRun,
} from '../src/index.ts';

const passed = (evidence_kind: ProbeResult['evidence_kind']): ProbeResult => ({
  result: 'passed', evidence_kind, evidence_ref: 'fx:run:1', sanitized_summary: 'Read one bounded page.',
});

test('only a passing test with verifying evidence can verify', () => {
  for (const kind of VERIFYING_EVIDENCE) assert.equal(canVerify(passed(kind)), true);
  for (const kind of NON_VERIFYING_EVIDENCE) assert.equal(canVerify(passed(kind)), false);
  assert.equal(canVerify({ ...passed('sandbox_operation'), result: 'failed' }), false);
  assert.equal(canVerify({ ...passed('conformance_suite'), result: 'blocked' }), false);
});

test('a host or link check never verifies', () => {
  assert.equal(canVerify(passed('host_reachability')), false);
  assert.equal(canVerify(passed('link_validation')), false);
});

test('a blocked test carries no evidence', () => {
  const blocked: ProbeResult = {
    result: 'blocked', evidence_kind: 'none', evidence_ref: 'blocked:no_connection_test_for_adapter',
    sanitized_summary: 'This adapter has no connection test.', reason_code: 'no_connection_test_for_adapter',
  };
  assert.equal(isWellFormedProbe(blocked), true);
  assert.equal(isWellFormedProbe({ ...blocked, evidence_kind: 'conformance_suite' }), false);
  assert.equal(isWellFormedProbe({ ...blocked, evidence_ref: '' }), false);
});

test('vocabularies are closed and disjoint', () => {
  assert.deepEqual([...PROBE_RESULTS], ['passed', 'failed', 'blocked']);
  assert.deepEqual([...PROBE_MODES], ['read_only_test', 'staging_ingestion']);
  const verifying: readonly string[] = VERIFYING_EVIDENCE;
  assert.equal(NON_VERIFYING_EVIDENCE.some((k) => verifying.includes(k)), false);
});

test('a verifiable adapter and its persisted run type-check', async () => {
  const adapter: VerifiableProvider = {
    descriptor: { provider_id: 'fixture-shop', mode: 'simulated', environment: 'demo',
      simulation_label: 'Simulated store — no real order', capabilities: ['catalog.search'] },
    async probe(capability, mode, now) {
      assert.equal(capability, 'catalog.search');
      assert.equal(mode, 'read_only_test');
      return { ...passed('conformance_suite'), evidence_ref: `sim:fixture-shop:probe:${capability}:${now}` };
    },
  };
  const r = await adapter.probe('catalog.search', 'read_only_test', '2026-10-05T12:00:00Z');
  const run: VerificationRun = { ...r, run_id: '6f1c2a0e-6c38-4d43-9a4e-6e0b9a1d2c11', provider_id: 'fixture-shop',
    environment: 'demo', capability: 'catalog.search', mode: 'read_only_test', ran_at: '2026-10-05T12:00:00Z' };
  assert.equal(canVerify(run), true);
});
