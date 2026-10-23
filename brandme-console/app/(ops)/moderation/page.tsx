/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /moderation — member reports queue (lane: opus-consumer-domains).
 * Server Component inside the console shell (contract v1): one h1 via
 * ConsolePageHeader, no extra main/rail. Every read and action is authorized
 * by the gateway and domain with the operator's own session.
 */

import { ConsolePageHeader } from '@/components/console-page-header'
import { resolveReport } from './actions'
import { formatTime, opsFetch, type Page } from './_lib/ops-gateway'
import styles from './_lib/ops.module.css'
import { ActionBanner, OpsState } from './_lib/states'

export const dynamic = 'force-dynamic'

interface Report {
  report_id: string
  target_type: 'decision_response' | 'share' | 'outfit_proposal' | 'member'
  target_ref: string
  reason: string
  note: string | null
  state: 'open' | 'actioned' | 'dismissed'
  action: string | null
  resolution_note: string | null
  resolved_by: string | null
  created_at: string
  resolved_at: string | null
}

const STATES = ['open', 'actioned', 'dismissed'] as const
const TARGET_LABEL: Record<Report['target_type'], string> = {
  decision_response: 'Decision response',
  share: 'Share',
  outfit_proposal: 'Outfit proposal',
  member: 'Member conduct',
}

export default async function ModerationPage({ searchParams }: { searchParams: { state?: string; done?: string; failed?: string } }) {
  const state = STATES.find((s) => s === searchParams.state) ?? 'open'
  const result = await opsFetch<Page<Report>>(`/moderation/reports?state=${state}`)

  return (
    <>
      <ConsolePageHeader
        eyebrow="Trust & safety"
        title="Moderation"
        description="Reports members filed about content they saw. Reporters are never shown to the reported member."
      />
      <ActionBanner done={searchParams.done} failed={searchParams.failed} />
      <nav aria-label="Report state" className="console-section">
        <ul className={styles.tabs}>
          {STATES.map((s) => (
            <li key={s}>
              <a href={`/moderation?state=${s}`} aria-current={s === state ? 'page' : undefined}>
                {s[0].toUpperCase() + s.slice(1)}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      {result.kind !== 'ok' ? (
        <OpsState result={result} area="Moderation" />
      ) : result.data.items.length === 0 ? (
        <section className="console-section" aria-labelledby="empty-heading">
          <h2 id="empty-heading">No {state} reports.</h2>
          <p>{state === 'open' ? 'Nothing is waiting for a decision.' : 'Nothing has been resolved this way yet.'}</p>
        </section>
      ) : (
        <section className="console-section" aria-labelledby="queue-heading">
          <h2 id="queue-heading">{result.data.items.length} {state} report{result.data.items.length === 1 ? '' : 's'}</h2>
          <p>Oldest first. Removing content redacts a response note, revokes a share or declines a proposal; member conduct can only be escalated.</p>
          <div className="console-table-region" role="region" aria-label="Reports" tabIndex={0}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Filed</th>
                  <th scope="col">Content</th>
                  <th scope="col">Reason</th>
                  <th scope="col">Reporter note</th>
                  <th scope="col">{state === 'open' ? 'Decision' : 'Outcome'}</th>
                </tr>
              </thead>
              <tbody>
                {result.data.items.map((r) => (
                  <tr key={r.report_id}>
                    <td>{formatTime(r.created_at)}</td>
                    <td>
                      {TARGET_LABEL[r.target_type]}
                      <br />
                      <code className={styles.ref}>{r.target_ref}</code>
                    </td>
                    <td>{r.reason.replace('_', ' ')}</td>
                    <td>{r.note ?? '—'}</td>
                    <td>
                      {r.state === 'open' ? (
                        <form action={resolveReport} className={styles.form}>
                          <input type="hidden" name="report_id" value={r.report_id} />
                          <label htmlFor={`d-${r.report_id}`}>Decision</label>
                          <select id={`d-${r.report_id}`} name="decision" required defaultValue="">
                            <option value="" disabled>
                              Choose…
                            </option>
                            <option value="dismiss">Dismiss</option>
                            {r.target_type !== 'member' && <option value="remove_content">Remove content</option>}
                            <option value="escalate">Escalate</option>
                          </select>
                          <label htmlFor={`n-${r.report_id}`}>Note (kept with the record)</label>
                          <textarea id={`n-${r.report_id}`} name="note" required maxLength={1000} rows={2} />
                          <button type="submit">Resolve</button>
                        </form>
                      ) : (
                        <>
                          {r.action ?? r.state} · {formatTime(r.resolved_at)}
                          <br />
                          {r.resolution_note}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  )
}
