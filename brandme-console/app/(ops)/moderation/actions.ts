'use server'

/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Moderation server action. The gateway and domain authorize the operator;
 * this only validates the form and reports the outcome back to the page.
 */

import { redirect } from 'next/navigation'
import { opsFetch } from './_lib/ops-gateway'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const DECISIONS = ['dismiss', 'remove_content', 'escalate']

export async function resolveReport(formData: FormData): Promise<void> {
  const reportId = String(formData.get('report_id') ?? '')
  const decision = String(formData.get('decision') ?? '')
  const note = String(formData.get('note') ?? '').trim()
  if (!UUID_RE.test(reportId) || !DECISIONS.includes(decision) || note.length < 1 || note.length > 1000) {
    redirect(`/moderation?failed=${encodeURIComponent('Choose a decision and write a note (1-1000 characters).')}`)
  }
  const out = await opsFetch(`/moderation/reports/${reportId}/resolve`, { method: 'POST', body: { decision, note } })
  if (out.kind !== 'ok') {
    const why = out.kind === 'error' || out.kind === 'denied' || out.kind === 'unconnected' ? out.detail : 'Sign in again.'
    redirect(`/moderation?failed=${encodeURIComponent(why)}`)
  }
  redirect(`/moderation?done=${encodeURIComponent('Report resolved. The reporter has been notified.')}`)
}
