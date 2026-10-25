/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/assistant — UNMOUNTED router (lane: opus-commerce-agents).
 * Tasks run in brandme_core/orchestrator, always under a grant: a member session drives
 * Brand.Me's assistant only through its grant to the `brandme-assistant` client; a bearer
 * agent uses its own grant. The event stream exposes goals, findings, proposed actions,
 * approvals and outcomes — never raw model reasoning.
 */

import { Router, type Request, type Response } from 'express';
import { z } from 'zod';
import { handle, problems } from '../../middleware/problem';
import {
  type CommerceDomainClient, domainProblem, forward, principalOf, rejectIdentityFields, requireAgentScope,
  requireIdempotencyKey, validate,
} from './commerce';

export const TaskCreate = z
  .object({
    goal: z.string().min(1).max(1000),
    assistance_mode: z.enum(['research', 'prepare', 'buy_within_rules']).default('research'),
    budget_hint: z.object({ amount_minor: z.string().regex(/^(0|[1-9][0-9]{0,17})$/), currency: z.string().regex(/^[A-Z]{3}$/) }).strict().optional(),
  })
  .strict();

export function createAssistantRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.use(rejectIdentityFields);
  router.post('/tasks', requireAgentScope('commerce:research'), requireIdempotencyKey, validate(TaskCreate),
    forward(client, 'assistant.task.create', (_req, res) => res.locals.input));
  router.post('/tasks/:id/cancel', requireAgentScope('commerce:research'),
    forward(client, 'assistant.task.cancel', (req) => ({ task_id: req.params.id })));
  router.get('/tasks/:id/events', requireAgentScope('commerce:research'), handle(async (req: Request, res: Response) => {
    const principal = principalOf(res);
    if (!principal) throw problems.unauthenticated();
    const after = req.get('Last-Event-ID') ?? undefined;
    const result = await client.call('assistant.task.events', principal, { task_id: req.params.id, after },
      { requestId: res.locals.requestId as string | undefined });
    if (result.status >= 400) throw domainProblem(result);
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'private, no-store');
    const events = (result.body as { events?: Array<{ seq: number; type: string; data: unknown }> }).events ?? [];
    for (const e of events) res.write(`id: ${e.seq}\nevent: ${e.type}\ndata: ${JSON.stringify(e.data)}\n\n`);
    res.end();
  }));
  return router;
}
