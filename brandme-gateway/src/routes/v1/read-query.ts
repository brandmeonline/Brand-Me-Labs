import { z } from 'zod';
import { ApiProblem } from '../../middleware/problem';

/** Closed pagination input: never forward caller-supplied visibility or identity. */
export function readQuery(query: unknown, cursor: z.ZodString): string {
  const parsed = z.object({
    cursor: cursor.optional(),
    limit: z.string().regex(/^[1-9][0-9]{0,2}$/).refine((v) => Number(v) <= 100).optional(),
  }).strict().safeParse(query);
  if (!parsed.success) throw new ApiProblem(400, 'invalid_query', 'Invalid query', 'Use a valid cursor and a limit between 1 and 100.');
  const params = new URLSearchParams();
  if (parsed.data.cursor) params.set('cursor', parsed.data.cursor);
  if (parsed.data.limit) params.set('limit', parsed.data.limit);
  return params.size ? `?${params}` : '';
}
