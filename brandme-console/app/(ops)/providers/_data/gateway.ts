// Server-side reads and operator changes for the provider and commerce pages (lane: opus-commerce-agents).
//
// The console shell is not an authorization boundary, and neither is this file:
// every call goes to the gateway's /api/v1 operator routes, which verify the
// caller's bearer token through foundation's principal middleware and require
// the operator role (provider:admin, commerce:operator). Only the incoming
// Authorization header is forwarded — never cookies — and nothing is rendered
// unless the gateway answers 200. Each non-200 outcome is a distinct, honest
// page state instead of placeholder data. Changes (setup saves, activation,
// connection tests) go through server actions in ./actions.ts.
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

// Outcome of an operator change sent through the gateway (server actions only).
export type Sent<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; code: string; detail: string }

async function problemOf(r: Response): Promise<{ code: string; detail: string }> {
  try {
    const body = (await r.json()) as { code?: unknown; detail?: unknown }
    const code = typeof body.code === 'string' && /^[a-z0-9_]{1,64}$/.test(body.code) ? body.code : 'refused'
    const detail = typeof body.detail === 'string' ? body.detail.slice(0, 300) : `The gateway answered ${r.status}.`
    return { code, detail }
  } catch {
    return { code: 'refused', detail: `The gateway answered ${r.status}.` }
  }
}

/**
 * PATCH/POST to an operator route with the incoming bearer only (never cookies). The gateway and
 * the domain authorize and validate; this only relays the outcome, including problem+json refusals.
 */
export async function sendToGateway<T>(method: 'PATCH' | 'POST' | 'PUT', path: string, body: unknown,
                                       ifMatch?: string): Promise<Sent<T>> {
  const base = process.env.BRANDME_GATEWAY_URL
  if (!base) return { ok: false, status: 0, code: 'not_connected', detail: 'Set BRANDME_GATEWAY_URL for the console server.' }
  const auth = (await headers()).get('authorization')
  if (!auth || !auth.startsWith('Bearer ')) {
    return { ok: false, status: 401, code: 'unauthenticated', detail: 'The gateway needs an operator bearer token on this request.' }
  }
  const h: Record<string, string> = { authorization: auth, accept: 'application/json', 'content-type': 'application/json' }
  if (ifMatch) h['if-match'] = ifMatch
  let r: Response
  try {
    r = await fetch(`${base.replace(/\/$/, '')}/api/v1${path}`, {
      method,
      headers: h,
      body: JSON.stringify(body),
      cache: 'no-store',
      signal: AbortSignal.timeout(10000),
    })
  } catch {
    return { ok: false, status: 0, code: 'unavailable', detail: 'The gateway did not answer. Nothing is known to have changed.' }
  }
  if (!r.ok) return { ok: false, status: r.status, ...(await problemOf(r)) }
  try {
    return { ok: true, status: r.status, data: (await r.json()) as T }
  } catch {
    return { ok: false, status: r.status, code: 'unreadable', detail: 'The gateway returned an unreadable response.' }
  }
}

export async function loadFromGateway<T>(path: string): Promise<Loaded<T>> {
  const base = process.env.BRANDME_GATEWAY_URL
  if (!base) return { state: 'not_connected' }
  const auth = (await headers()).get('authorization')
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

// The merchant's payment rail (operator only; never in the public provider DTO). Not a capability.
export type PaymentRail = {
  processor_id: string
  mode: 'simulated' | 'sandbox'
  label: string
  currencies: string[]
  api_version: string | null
  webhooks_configured: boolean
}

// Process-local counters from the merchant adapter: stuck money operations surface here.
export type RailHealth = {
  pending_money_ops: number
  needs_operator: number
  orphans_voided: number
  webhooks_ignored: number
  money_ops_refused: number
}

export type ProviderDetail = ProviderRow & {
  protocols: Record<string, string>
  allowed_redirect_hosts: string[]
  credential_configured: boolean
  version: string
  payment_rail?: PaymentRail | null
}

export type ProviderHealth = {
  provider_id: string
  environment: string
  capabilities: CapabilityRow[]
  executable: string[]
  simulation: boolean
  payment_rail?: PaymentRail | null
  rail_health?: RailHealth | null
}

export const STRIPE_TEST_NOTICE =
  'Payments use Stripe test mode. No real money moves; only Stripe test cards are used. Capability state is sandbox, never verified.'

export function railLabel(r: PaymentRail): string {
  return r.mode === 'sandbox' ? `${r.label} (${r.processor_id}, API ${r.api_version ?? 'unpinned'})` : r.label
}

export type SetupItem = {
  key: string
  label: string
  state: 'done' | 'todo' | 'not_needed' | 'blocked'
  detail?: string
  evidence_ref?: string
  recorded_at?: string
}
export type SetupSection = {
  key: 'enables' | 'prerequisites' | 'credentials' | 'data_use' | 'tests' | 'activation'
  title: string
  description?: string
  items: SetupItem[]
}
export type VerificationRunRow = {
  run_id: string
  provider_id: string
  environment: string
  capability: string
  mode: string | null
  result: 'passed' | 'failed' | 'blocked'
  evidence_kind: string
  evidence_ref: string
  sanitized_summary: string
  reason_code: string | null
  ran_at: string
}
export type ProviderSetup = {
  provider_id: string
  display_name: string
  environment: string
  simulation: boolean
  disclosure: string
  access_level: string
  access_levels: string[]
  editable_fields: string[]
  data_use_rights: string[]
  credential_configured: boolean
  credential_fingerprint: string | null
  credential_rotated_at: string | null
  version: string
  sections: SetupSection[]
  capabilities: CapabilityRow[]
  testable_capabilities: string[]
  connection_test_available: boolean
  freshness_hours: number
  recent_runs: VerificationRunRow[]
  editable: boolean
  /** Present only where a tier bounds something (3D/AR offered, or a tier already recorded). */
  tier?: PartnerTier
  tier_options?: TierOption[]
}
/** Partner tier (operator view). Placeholder tiers carry no price and sit at the two ends of each limit. */
export type TierIncludes = {
  shelf_variants: number | null
  customization: string
  analytics: string
  member_connection: string
}
export type PartnerTier = {
  tier_id: string | null
  source: 'assigned' | 'unassigned' | 'assigned_unknown' | 'unconfigured'
  table_version: string
  placeholder: boolean
  price_status: 'not_priced'
  price_label: string
  includes: TierIncludes
  label: string | null
}
export type TierOption = {
  tier_id: string
  display_name: string
  placeholder: boolean
  price_status: 'not_priced'
  price_label: string
  includes: TierIncludes
}
export type VerificationRuns = { provider_id: string; environment: string; simulation: boolean; items: VerificationRunRow[] }

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
