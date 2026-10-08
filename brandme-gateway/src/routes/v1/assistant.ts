/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/assistant — UNMOUNTED router (lane: opus-commerce-agents).
 * Tasks run in brandme_core/orchestrator. The event stream exposes goals, findings, proposed
 * actions, approvals and outcomes — never raw model reasoning.
 */

import { Router, Response } from 'express';
import { z } from 'zod';
import { CommerceDomainClient, PrincipalRequest, forward, problem, rejectIdentityFields, requireScope, validate } from './commerce';

const TaskCreate = z
  .object({
    goal: z.string().min(1).max(1000),
    assistance_mode: z.enum(['research', 'prepare', 'buy_within_rules']).default('research'),
    budget_hint: z.object({ amount_minor: z.string().regex(/^(0|[1-9][0-9]{0,17})$/), currency: z.string().regex(/^[A-Z]{3}$/) }).strict().optional(),
  })
  .strict();

export function createAssistantRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.use(rejectIdentityFields);
  router.post('/tasks', requireScope('commerce:research'), validate(TaskCreate),
    forward(client, 'assistant.task.create', (r) => r.body));
  router.post('/tasks/:id/cancel', requireScope('commerce:research'),
    forward(client, 'assistant.task.cancel', (r) => ({ task_id: r.params.id })));
  router.get('/tasks/:id/events', requireScope('commerce:research'), async (req: PrincipalRequest, res: Response, next) => {
    try {
      const after = req.get('Last-Event-ID') ?? undefined;
      const result = await client.call('assistant.task.events', req.principal ?? null, { task_id: req.params.id, after });
      if (result.status !== 200) {
        problem(res, result.status, 'task_unavailable', 'task not found or not accessible', req.requestId);
        return;
      }
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'private, no-store');
      const events = (result.body as { events?: Array<{ seq: number; type: string; data: unknown }> }).events ?? [];
      for (const e of events) {
        res.write(`id: ${e.seq}\nevent: ${e.type}\ndata: ${JSON.stringify(e.data)}\n\n`);
      }
      res.end();
    } catch (err) {
      next(err);
    }
  });
  return router;
}
