// Server-side reads for the provider and commerce operator pages (lane: opus-commerce-agents).
//
// The console shell is not an authorization boundary, and neither is this file:
// every read goes to the gateway's /api/v1 operator routes, which verify the
// caller's bearer token through foundation's principal middleware and require
// the operator role (provider:admin, commerce:operator). Only the incoming
// Authorization header is forwarded — never cookies — and nothing is rendered
// unless the gateway answers 200. Each non-200 outcome is a distinct, honest
// page state instead of placeholder data.
import { headers } from 'next/headers'

export type Loaded<T> =
  | { state: 'ok'; data: T }
  | { state: 'not_connected' }
  | { state: 'unauthenticated' }
  | { state: 'denied' }
  | { state: 'not_found' }
  | { state: 'not_built'; detail: string }
  | { state: 'unavailable'; detail: string }

async function problemDetail(r: Response, fallback: string): Promise<string> {
  try {
    const body = (await r.json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail.slice(0, 300) : fallback
  } catch {
    return fallback
  }
}

export async function loadFromGateway<T>(path: string): Promise<Loaded<T>> {
  const base = process.env.BRANDME_GATEWAY_URL
  if (!base) return { state: 'not_connected' }
  const auth = headers().get('authorization')
  if (!auth || !auth.startsWith('Bearer ')) return { state: 'unauthenticated' }
  let r: Response
  try {
    r = await fetch(`${base.replace(/\/$/, '')}/api/v1${path}`, {
      headers: { authorization: auth, accept: 'application/json' },
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    })
  } catch {
    return { state: 'unavailable', detail: 'The gateway did not answer.' }
  }
  if (r.status === 401) return { state: 'unauthenticated' }
  if (r.status === 403) return { state: 'denied' }
  if (r.status === 404) return { state: 'not_found' }
  if (r.status === 501) return { state: 'not_built', detail: await problemDetail(r, 'Not built in this release.') }
  if (!r.ok) return { state: 'unavailable', detail: await problemDetail(r, `The gateway answered ${r.status}.`) }
  try {
    return { state: 'ok', data: (await r.json()) as T }
  } catch {
    return { state: 'unavailable', detail: 'The gateway returned an unreadable response.' }
  }
}

// Shapes returned by the commerce domain (brandme_core/domains/commerce/http_api.py).
export type CapabilityRow = {
  name: string
  state: 'unconfigured' | 'sandbox' | 'verified' | 'degraded' | 'suspended' | 'unsupported'
  reason_code: string
  last_checked_at: string | null
  evidence_ref: string | null
  evidence_kind?: string | null
}

export type ProviderRow = {
  provider_id: string
  display_name: string
  environment: string
  capabilities: CapabilityRow[]
  country_codes: string[]
  disclosure: string
  access_level: string
  simulation: boolean
}

export type ProviderDetail = ProviderRow & {
  protocols: Record<string, string>
  allowed_redirect_hosts: string[]
  credential_configured: boolean
  version: string
}

export type ProviderHealth = {
  provider_id: string
  environment: string
  capabilities: CapabilityRow[]
  executable: string[]
  simulation: boolean
}

export type SetupItem = { key: string; state: 'done' | 'todo' | 'not_needed'; value?: unknown }
export type ProviderSetup = { provider_id: string; items: SetupItem[]; editable: boolean; note: string }

export type QueueOperation = {
  operation_id: string
  provider_id: string
  state: string
  reason_code: string | null
  attempts: number
  age_seconds: number
  updated_at: string
}
export type OperationsQueue = {
  environment: string
  observed_at: string
  outcome_unknown: QueueOperation[]
  stale_submitting: QueueOperation[]
  webhooks_pending: { provider_id: string; event_type: string; age_seconds: number }[]
}

export const EXECUTABLE = new Set(['sandbox', 'verified', 'degraded'])

export function capabilityLabel(c: CapabilityRow, simulation: boolean): string {
  if (c.state === 'sandbox' && simulation) return 'Simulated'
  return {
    unconfigured: 'Not configured',
    sandbox: 'Sandbox',
    verified: 'Verified',
    degraded: 'Degraded',
    suspended: 'Suspended',
    unsupported: 'Not offered',
  }[c.state]
}

export function age(seconds: number): string {
  if (seconds < 90) return `${seconds}s`
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`
  return `${Math.round(seconds / 3600)} h`
}
