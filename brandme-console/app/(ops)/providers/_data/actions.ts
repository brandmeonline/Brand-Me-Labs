'use server'
// Server actions for /providers/[id]/setup (lane: opus-commerce-agents).
//
// Each action relays one operator change to the gateway with the incoming bearer only, then
// redirects back to the setup page with the outcome. Nothing here decides anything: the domain
// validates input, refuses secret values, requires provider:admin, and enables a capability only
// through activation backed by a fresh passing connection test. "Connect" is never a local switch.
import { redirect } from 'next/navigation'
import { sendToGateway, type VerificationRunRow } from './gateway'
import { outcomeQuery, type Outcome } from './outcome'

const PROVIDER_ID = /^[a-z0-9_]{1,80}$/
const CAPABILITY = /^[a-z0-9]+\.[a-z0-9_]+$/
const TEXT_FIELDS = ['approval_evidence_ref', 'account_ref', 'catalog_ref', 'endpoint_descriptor_ref', 'credential_secret_ref']

function back(providerId: string, o: Outcome): never {
  redirect(`/providers/${encodeURIComponent(providerId)}/setup?${outcomeQuery(o)}#outcome`)
}

function refused(status: number, code: string, detail: string): Outcome {
  return { kind: 'refused', status, code, detail }
}

function ifMatch(form: FormData): string | undefined {
  const v = form.get('version')
  return typeof v === 'string' && /^\d{1,12}$/.test(v) ? `"${v}"` : undefined
}

function field(form: FormData, name: string): string {
  const v = form.get(name)
  return typeof v === 'string' ? v.trim() : ''
}

export async function saveSetup(providerId: string, form: FormData): Promise<void> {
  if (!PROVIDER_ID.test(providerId)) back('unknown', refused(404, 'not_found', 'Unknown provider.'))
  const body: Record<string, unknown> = {}
  for (const name of TEXT_FIELDS) {
    const v = field(form, name)
    if (v) body[name] = v
  }
  const level = field(form, 'access_level')
  if (level) body.access_level = level
  const applied = field(form, 'program_application_opened')
  if (applied === 'yes' || applied === 'no') body.program_application_opened = applied === 'yes'
  const rights = form.getAll('data_use_right').filter((r): r is string => typeof r === 'string')
  const marks = rights.map((r) => [r, field(form, `data_use:${r}`)] as const)
  if (marks.some(([, v]) => v)) {
    if (marks.some(([, v]) => v !== 'yes' && v !== 'no')) {
      back(providerId, refused(400, 'data_use_incomplete', 'Mark every data-use right, or leave all of them unchanged.'))
    }
    body.data_use = Object.fromEntries(marks.map(([r, v]) => [r, v === 'yes']))
  }
  if (Object.keys(body).length === 0) {
    back(providerId, refused(400, 'empty_update', 'Nothing to save: every field was left unchanged.'))
  }
  const r = await sendToGateway(`PATCH`, `/providers/${encodeURIComponent(providerId)}/setup`, body, ifMatch(form))
  back(providerId, r.ok ? { kind: 'saved' } : refused(r.status, r.code, r.detail))
}

export async function activateCapability(providerId: string, form: FormData): Promise<void> {
  const capability = field(form, 'capability')
  if (!PROVIDER_ID.test(providerId) || !CAPABILITY.test(capability)) {
    back(PROVIDER_ID.test(providerId) ? providerId : 'unknown', refused(400, 'unknown_capability', 'Unknown capability.'))
  }
  const r = await sendToGateway('PATCH', `/providers/${encodeURIComponent(providerId)}/setup`, { activate: capability },
    ifMatch(form))
  back(providerId, r.ok ? { kind: 'activated' } : refused(r.status, r.code, r.detail))
}

export async function runConnectionTest(providerId: string, form: FormData): Promise<void> {
  const capability = field(form, 'capability')
  const mode = field(form, 'mode') || 'read_only_test'
  if (!PROVIDER_ID.test(providerId) || !CAPABILITY.test(capability)) {
    back(PROVIDER_ID.test(providerId) ? providerId : 'unknown', refused(400, 'unknown_capability', 'Unknown capability.'))
  }
  const r = await sendToGateway<VerificationRunRow>('POST', `/providers/${encodeURIComponent(providerId)}/verification-runs`,
    { capability, mode })
  back(providerId, r.ok ? { kind: 'tested', run: r.data.run_id, result: r.data.result } : refused(r.status, r.code, r.detail))
}
