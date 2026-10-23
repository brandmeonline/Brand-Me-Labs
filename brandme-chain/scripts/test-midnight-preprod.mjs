#!/usr/bin/env node
// Keep credentials out of Vitest's error reporter as well as application logs.
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';

const token = process.env.MIDNIGHT_BLOCKFROST_PROJECT_ID ?? '';
const seeds = (process.env.MN_PREPROD_SEEDS ?? '').split(',').map(s => s.trim()).filter(Boolean);
if (!/^nightpreprod[A-Za-z0-9_-]{8,}$/.test(token) || seeds.length < 3 ||
    new Set(seeds).size !== seeds.length || seeds.some(s => !/^[0-9a-f]{64}$/i.test(s))) {
  console.error('Preprod verification needs MIDNIGHT_BLOCKFROST_PROJECT_ID and MN_PREPROD_SEEDS (3+ distinct test wallet seeds with tNIGHT and DUST). Configure them through your secret manager. No transactions were attempted.');
  process.exit(1);
}
const redact = text => [token, ...seeds].reduce((s, secret) => s.split(secret).join('[REDACTED]'), text)
  .replace(/([?&]project_id=)[^\s&"'\\<>]+/gi, '$1[REDACTED]')
  .replace(/night(?:preprod|mainnet)[A-Za-z0-9_-]+/g, '[REDACTED]');
const child = spawn(process.execPath, ['node_modules/vitest/vitest.mjs', 'run', '--config', 'vitest.network.config.ts'], {
  env: { ...process.env, MIDNIGHT_NETWORK: 'preprod' }, stdio: ['ignore', 'pipe', 'pipe'],
});
for (const [stream, target] of [[child.stdout, process.stdout], [child.stderr, process.stderr]]) {
  // Buffer complete lines so a credential split across chunks cannot escape redaction.
  createInterface({ input: stream, crlfDelay: Infinity }).on('line', line => target.write(`${redact(line)}\n`));
}
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
child.on('error', () => { console.error('Could not start Preprod verification.'); process.exitCode = 1; });
child.on('exit', (code) => { process.exitCode = code ?? 1; });
