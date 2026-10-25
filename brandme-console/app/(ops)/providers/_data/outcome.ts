// Outcome of a setup server action, carried to the re-rendered page in the query string
// (lane: opus-commerce-agents). Only a kind, an HTTP status, a problem code, the domain's short
// detail and a run id travel — never a submitted value, so a refused secret is not reflected.
export type Outcome =
  | { kind: 'saved' | 'activated' }
  | { kind: 'tested'; run: string; result: string }
  | { kind: 'refused'; status: number; code: string; detail: string }

type Search = Record<string, string | string[] | undefined>

const CODE = /^[a-z0-9_]{1,64}$/
const RUN = /^[0-9a-f-]{36}$/

export function outcomeQuery(o: Outcome): string {
  const q = new URLSearchParams({ outcome: o.kind })
  if (o.kind === 'tested') {
    q.set('run', o.run)
    q.set('result', o.result)
  }
  if (o.kind === 'refused') {
    q.set('status', String(o.status))
    q.set('code', o.code)
    q.set('detail', o.detail.slice(0, 300))
  }
  return q.toString()
}

const one = (v: string | string[] | undefined): string => (typeof v === 'string' ? v : '')

export function readOutcome(sp: Search): Outcome | null {
  const kind = one(sp.outcome)
  if (kind === 'saved' || kind === 'activated') return { kind }
  if (kind === 'tested') {
    const run = one(sp.run)
    const result = one(sp.result)
    return RUN.test(run) && ['passed', 'failed', 'blocked'].includes(result) ? { kind, run, result } : null
  }
  if (kind === 'refused') {
    const status = Number(one(sp.status))
    const code = one(sp.code)
    if (!Number.isInteger(status) || status < 0 || status > 599 || !CODE.test(code)) return null
    return { kind, status, code, detail: one(sp.detail).slice(0, 300) }
  }
  return null
}
