/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /rewards-disputes — member reward disputes (lane: opus-consumer-domains).
 * Server Component inside the console shell (contract v1). Balances are never
 * edited here: a resolution is "no change" or a reasoned correction entry.
 */

import { ConsolePageHeader } from '@/components/console-page-header'
import { formatTime, opsFetch, type Page } from '../moderation/_lib/ops-gateway'
import styles from '../moderation/_lib/ops.module.css'
import { ActionBanner, OpsState } from '../moderation/_lib/states'
import { resolveDispute } from './actions'

export const dynamic = 'force-dynamic'

interface Dispute {
  member_id: string
  dispute_id: string
  entry_id: string | null
  category: string
  message: string
  state: 'open' | 'resolved_correction' | 'resolved_no_change' | 'withdrawn'
  resolution_note: string | null
  correction_entry_id: string | null
  created_at: string
  resolved_at: string | null
}

const STATES = ['open', 'resolved_correction', 'resolved_no_change'] as const
const STATE_LABEL: Record<string, string> = { open: 'Open', resolved_correction: 'Corrected', resolved_no_change: 'No change' }

export default async function RewardDisputesPage({ searchParams }: { searchParams: { state?: string; done?: string; failed?: string } }) {
  const state = STATES.find((s) => s === searchParams.state) ?? 'open'
  const result = await opsFetch<Page<Dispute>>(`/rewards/disputes?state=${state}`)

  return (
    <>
      <ConsolePageHeader
        eyebrow="Rewards"
        title="Reward disputes"
        description="Members asking about missing, wrong or reversed points. Points are app credits, never cash; balances change only through ledger entries."
      />
      <ActionBanner done={searchParams.done} failed={searchParams.failed} />
      <nav aria-label="Dispute state" className="console-section">
        <ul className={styles.tabs}>
          {STATES.map((s) => (
            <li key={s}>
              <a href={`/rewards-disputes?state=${s}`} aria-current={s === state ? 'page' : undefined}>
                {STATE_LABEL[s]}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      {result.kind !== 'ok' ? (
        <OpsState result={result} area="Reward disputes" />
      ) : result.data.items.length === 0 ? (
        <section className="console-section" aria-labelledby="empty-heading">
          <h2 id="empty-heading">No {STATE_LABEL[state].toLowerCase()} disputes.</h2>
          <p>{state === 'open' ? 'Nothing is waiting for a decision.' : 'Nothing has been resolved this way yet.'}</p>
        </section>
      ) : (
        <section className="console-section" aria-labelledby="queue-heading">
          <h2 id="queue-heading">
            {result.data.items.length} {STATE_LABEL[state].toLowerCase()} dispute{result.data.items.length === 1 ? '' : 's'}
          </h2>
          <p>Oldest first. Open the member ledger to check the journal before deciding. You cannot handle your own disputes.</p>
          <div className="console-table-region" role="region" aria-label="Disputes" tabIndex={0}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Opened</th>
                  <th scope="col">Category</th>
                  <th scope="col">Member message</th>
                  <th scope="col">Ledger</th>
                  <th scope="col">{state === 'open' ? 'Decision' : 'Outcome'}</th>
                </tr>
              </thead>
              <tbody>
                {result.data.items.map((d) => (
                  <tr key={d.dispute_id}>
                    <td>{formatTime(d.created_at)}</td>
                    <td>{d.category.replace('_', ' ')}</td>
                    <td>{d.message}</td>
                    <td>
                      <a href={`/rewards-disputes/members/${d.member_id}`}>Member ledger</a>
                      {d.entry_id && (
                        <>
                          <br />
                          Entry <code>{d.entry_id.slice(0, 8)}</code>
                        </>
                      )}
                    </td>
                    <td>
                      {d.state === 'open' ? (
                        <form action={resolveDispute} className={styles.form}>
                          <input type="hidden" name="dispute_id" value={d.dispute_id} />
                          <fieldset>
                            <legend>Outcome</legend>
                            <label>
                              <input type="radio" name="outcome" value="no_change" required /> No change
                            </label>
                            <label>
                              <input type="radio" name="outcome" value="correction" /> Correction entry
                            </label>
                          </fieldset>
                          <label htmlFor={`p-${d.dispute_id}`}>Points (correction only; negative to debit)</label>
                          <input id={`p-${d.dispute_id}`} name="signed_points" type="number" step={1} min={-10000} max={10000} inputMode="numeric" />
                          <label htmlFor={`n-${d.dispute_id}`}>Note shown to the member</label>
                          <textarea id={`n-${d.dispute_id}`} name="note" required maxLength={1000} rows={2} />
                          <label htmlFor={`e-${d.dispute_id}`}>Evidence reference</label>
                          <input id={`e-${d.dispute_id}`} name="evidence_ref" required maxLength={120} />
                          <button type="submit">Resolve</button>
                        </form>
                      ) : (
                        <>
                          {STATE_LABEL[d.state] ?? d.state} · {formatTime(d.resolved_at)}
                          <br />
                          {d.resolution_note}
                          {d.correction_entry_id && (
                            <>
                              <br />
                              Correction <code>{d.correction_entry_id.slice(0, 8)}</code>
                            </>
                          )}
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
