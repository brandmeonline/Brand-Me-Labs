/** Real service process + Spanner; deterministic HTTP providers, no network writes. */
import { createServer } from 'node:http';
import { execFileSync, spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { operationDatabase, SpannerOperationStore } from '../../src/midnight/spanner-store.js';
import { newOperation, transition } from '../../src/midnight/operations.js';
import { Actor, RightsSimulator, registerIssuer, issue } from '../support/scenario.js';
import { toHex } from '../../src/midnight/bytes.js';

it('starts its scheduled worker from configuration and shuts down cleanly after projection', async () => {
  const databaseId = `runtime-${randomUUID().slice(0, 8)}`;
  const setup = (action: string) => execFileSync(process.env.BRANDME_PYTHON ?? 'python3',
    [fileURLToPath(new URL('../support/store-database.py', import.meta.url)), action, databaseId],
    { env: { ...process.env, BRANDME_MODE: 'development' }, stdio: 'pipe' });
  setup('create');
  const db = operationDatabase('test-project', 'brandme-instance', databaseId);
  const store = new SpannerOperationStore(db, 'development');
  const sim = new RightsSimulator(); const issuer = new Actor('issuer');
  const issuerId = registerIssuer(sim, issuer); const { eid, issuanceId } = issue(sim, issuer, issuerId, new Actor('holder'));
  const hash = 'ab'.repeat(32); const txHash = 'cd'.repeat(32);
  let op = await store.create(newOperation({ network: 'undeployed', contractAddress: sim.address,
    circuit: 'issueEntitlement', args: [issuerId, issuanceId], ownerRef: randomUUID() }));
  op = (await store.update(transition(op, 'Proving'), op.version))!;
  op = (await store.update(transition(op, 'Reconciling', { evidence: { txId: randomUUID(), observedAt: new Date().toISOString() } }), op.version))!;
  const calls: string[] = [];
  const provider = createServer(async (req, res) => {
    const chunks: Buffer[] = []; for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString());
    let response;
    if (body.method) {
      calls.push(body.method);
      const result = body.method === 'chain_getHeader' ? { number: '0xf' } : `0x${hash}`;
      response = { jsonrpc: '2.0', id: body.id, result };
    } else if (body.query.includes('OperationTransaction')) {
      calls.push('transaction');
      response = { data: { transactions: [{ hash: txHash, identifiers: [op.evidence!.txId],
        block: { height: 12, hash }, transactionResult: { status: 'SUCCESS' } }] } };
    } else {
      calls.push('ledger');
      response = { data: { contractAction: { address: sim.address, state: sim.serializedState(),
        transaction: { block: { height: 12, hash } } } } };
    }
    res.setHeader('content-type', 'application/json'); res.end(JSON.stringify(response));
  });
  provider.listen(0, '127.0.0.1'); await new Promise<void>((resolve) => provider.once('listening', resolve));
  const port = (provider.address() as { port: number }).port;
  // CI uses the source entry point; a built entry point can also be verified locally.
  const args = process.env.BRANDME_CHAIN_BUILT_RUNTIME ? ['dist/src/index.js'] : ['--import', 'tsx', 'src/index.ts'];
  const child = spawn(process.execPath, args, { cwd: fileURLToPath(new URL('../..', import.meta.url)),
    env: { ...process.env, PORT: '0', ENVIRONMENT: 'development', LOG_LEVEL: 'error', CHAIN_RECONCILIATION_ENABLED: 'true',
      SPANNER_PROJECT_ID: 'test-project', SPANNER_INSTANCE_ID: 'brandme-instance', SPANNER_DATABASE_ID: databaseId,
      CHAIN_SERVICE_TOKEN: 'test-only-chain-runtime-credential-123456789', MIDNIGHT_NETWORK: 'undeployed',
      MIDNIGHT_CONTRACT_ADDRESS: sim.address, MIDNIGHT_LOCAL_NODE_PORT: String(port), MIDNIGHT_LOCAL_INDEXER_PORT: String(port) },
    stdio: ['ignore', 'pipe', 'pipe'] });
  let output = ''; child.stdout.on('data', (value) => { output += value; }); child.stderr.on('data', (value) => { output += value; });
  const exited = new Promise<number | null>((resolve) => child.once('exit', resolve));
  try {
    let done = false;
    for (let i = 0; i < 200; i++) {
      if (child.exitCode !== null) throw new Error(`chain service exited before projection: ${output}`);
      const [rows] = await db.run({ sql: 'SELECT projection_completed_at FROM ChainOperations WHERE operation_id = @id', params: { id: op.operationId }, json: true });
      if ((rows[0] as any).projection_completed_at) { done = true; break; }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    expect(done, output).toBe(true);
    const [rows] = await db.run({ sql: 'SELECT entitlement_id, controller_subject_ref FROM RightsEntitlements', json: true });
    expect(rows).toEqual([{ entitlement_id: toHex(eid), controller_subject_ref: null }]);
    expect(calls).toContain('ledger');
    expect(calls.every((v) => ['chain_getFinalizedHead', 'chain_getHeader', 'chain_getBlockHash', 'transaction', 'ledger'].includes(v))).toBe(true);
    child.kill('SIGTERM'); expect(await exited).toBe(0);
  } finally {
    if (child.exitCode === null) child.kill('SIGKILL');
    await exited;
    await new Promise<void>((resolve) => { provider.close(() => resolve()); provider.closeAllConnections(); });
    await db.close(); setup('drop');
  }
});
