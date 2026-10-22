/** Automatic read-only recovery. No wallet, prover, broadcast, or client-supplied evidence. */
import { randomInt } from 'node:crypto';
import type { OperationStore } from './operations.js';
import type { OperationReconciler } from './reconciler.js';
import type { FinalizedEntitlementProjector } from './projection.js';
import type { SpannerReconciliationQueue } from './reconciliation-queue.js';

export class ReconciliationWorker {
  private stopping = false;
  private started = false;
  private timer?: ReturnType<typeof setTimeout>;
  private running?: Promise<{ processed: number; errors: number }>;
  constructor(private readonly o: {
    network: string; contractAddress: string; store: OperationStore;
    queue: Pick<SpannerReconciliationQueue, 'claim' | 'release' | 'complete'>;
    reconciler: Pick<OperationReconciler, 'reconcile'>; projector: Pick<FinalizedEntitlementProjector, 'project'>;
    report?: (counts: { processed: number; errors: number }) => void;
  }) { if (o.network === 'mainnet') throw new Error('Mainnet worker is disabled'); }

  /** No overlapping ticks in one process; the database lease fences other replicas. */
  tick(): Promise<{ processed: number; errors: number }> {
    if (this.running) return this.running;
    this.running = this.batch().finally(() => { this.running = undefined; });
    return this.running;
  }

  private async batch(): Promise<{ processed: number; errors: number }> {
    const counts = { processed: 0, errors: 0 };
    for (let i = 0; i < 10 && !this.stopping; i++) {
      let claim;
      try { claim = await this.o.queue.claim(this.o.network, this.o.contractAddress); }
      catch { counts.errors++; break; }
      if (!claim) break;
      counts.processed++;
      try {
        const op = await this.o.store.get(claim.operationId);
        if (!op) continue; // Privacy erasure wins; a missing journal is never recreated.
        const observed = await this.o.reconciler.reconcile(op.operationId);
        if (['Finalized', 'HandoverPending', 'HandoverAcknowledged'].includes(observed.state)) {
          const projection = await this.o.projector.project(observed);
          if (await this.o.queue.complete(claim, observed, projection)) continue;
        }
      } catch { counts.errors++; } // Provider errors can contain credentials; do not log their text.
      try {
        const delay = Math.min(900_000, 15_000 * 2 ** Math.min(claim.attempt - 1, 6) + randomInt(0, 1001));
        await this.o.queue.release(claim, delay);
      } catch { counts.errors++; } // Crash/release failure is recovered when the durable lease expires.
    }
    return counts;
  }

  start(): void {
    if (this.started || this.stopping) return;
    this.started = true;
    const run = () => {
      this.timer = undefined;
      void this.tick().then((counts) => {
        this.o.report?.(counts);
        if (!this.stopping) this.timer = setTimeout(run, 15_000);
      });
    };
    this.timer = setTimeout(run, 0);
  }

  async stop(): Promise<void> {
    this.stopping = true;
    if (this.timer) clearTimeout(this.timer);
    await this.running;
  }
}
