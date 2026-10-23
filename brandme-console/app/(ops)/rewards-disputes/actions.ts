'use server'

/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Reward-dispute server actions. An operator never edits a balance: a
 * resolution is either "no change" or a reasoned ledger correction, and a
 * reversal is a new linked entry. The gateway and domain authorize every call.
 */

import { redirect } from 'next/navigation'
import { opsFetch } from '../moderation/_lib/ops-gateway'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function back(path: string, key: 'done' | 'failed', message: string): never {
  redirect(`${path}${path.includes('?') ? '&' : '?'}${key}=${encodeURIComponent(message)}`)
}

function why(out: Awaited<ReturnType<typeof opsFetch>>): string {
  return out.kind === 'error' || out.kind === 'denied' || out.kind === 'unconnected' ? out.detail : 'Sign in again.'
}

export async function resolveDispute(formData: FormData): Promise<void> {
  const disputeId = String(formData.get('dispute_id') ?? '')
  const outcome = String(formData.get('outcome') ?? '')
  const note = String(formData.get('note') ?? '').trim()
  const evidence = String(formData.get('evidence_ref') ?? '').trim()
  const raw = String(formData.get('signed_points') ?? '').trim()
  const points = raw === '' ? 0 : Number(raw)
  if (!UUID_RE.test(disputeId) || !['correction', 'no_change'].includes(outcome) || !note || note.length > 1000 || !evidence || evidence.length > 120) {
    back('/rewards-disputes', 'failed', 'Choose an outcome and give a note and an evidence reference.')
  }
  if (outcome === 'correction' && (!Number.isInteger(points) || points === 0 || Math.abs(points) > 10000)) {
    back('/rewards-disputes', 'failed', 'A correction needs a non-zero whole number of points within ±10000.')
  }
  const body = outcome === 'correction' ? { outcome, signed_points: points, note, evidence_ref: evidence } : { outcome, note, evidence_ref: evidence }
  const out = await opsFetch(`/rewards/disputes/${disputeId}/resolve`, { method: 'POST', body })
  if (out.kind !== 'ok') back('/rewards-disputes', 'failed', why(out))
  back('/rewards-disputes', 'done', 'Dispute resolved. The member can see the outcome and any correction entry.')
}

export async function reverseEntry(formData: FormData): Promise<void> {
  const memberRef = String(formData.get('member_ref') ?? '')
  const entryId = String(formData.get('entry_id') ?? '')
  const reason = String(formData.get('reason') ?? '').trim()
  const evidence = String(formData.get('evidence_ref') ?? '').trim()
  const page = `/rewards-disputes/members/${UUID_RE.test(memberRef) ? memberRef : ''}`
  if (!UUID_RE.test(memberRef) || !UUID_RE.test(entryId) || !reason || reason.length > 500 || !evidence || evidence.length > 120) {
    back(page, 'failed', 'A reversal needs a verified reason and an evidence reference.')
  }
  const out = await opsFetch(`/rewards/members/${memberRef}/entries/${entryId}/reverse`, { method: 'POST', body: { reason, evidence_ref: evidence } })
  if (out.kind !== 'ok') back(page, 'failed', why(out))
  back(page, 'done', 'Reversal recorded as a linked entry. Spent points, if any, became recovery due.')
}
