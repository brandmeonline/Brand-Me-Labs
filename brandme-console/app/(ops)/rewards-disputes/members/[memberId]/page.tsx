/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /rewards-disputes/members/[memberId] — audit view of one member's ledger:
 * reducer consistency check and the journal, with a linked-reversal action
 * for a *verified* disqualifying event. Self-review is refused by the domain.
 */

import { formatTime, opsFetch } from '../../../moderation/_lib/ops-gateway'
import styles from '../../../moderation/_lib/ops.module.css'
import { ActionBanner, OpsState } from '../../../moderation/_lib/states'
import { reverseEntry } from '../../actions'
import { ConsolePageHeader } from '../../../_shell/console-page-header'

export const dynamic = 'force-dynamic'

const RULE_LABEL: Record<string, string> = {
  meaningful_style_setup: 'Style setup',
  first_owned_item: 'First owned item',
  friend_decision_response: 'Friend decision response',
  styling_proposal_accepted: 'Proposal accepted',
  catalog_correction_accepted: 'Catalog correction',
  verified_repair: 'Verified repair',
}
const ACCOUNT_ORDER = ['available', 'reserved', 'recovery_due', 'lifetime_earned', 'gross_earned', 'reversed', 'spent']

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

interface Entry {
  entry_id: string
  kind: string
  state: string
  rule_id: string | null
  points: number
  available_change: number
  reserved_change: number
  recovery_due_change: number
  reason: string | null
  reverses_entry_id: string | null
  evidence_refs: string[]
  created_at: string
}

interface Ledger {
  consistency: { ok: boolean; account: Record<string, number | string>; journal: number[] }
  entries: Entry[]
}

export default async function MemberLedgerPage({ params, searchParams }: {
  params: { memberId: string }
  searchParams: { done?: string; failed?: string }
}) {
  const valid = UUID_RE.test(params.memberId)
  const result = valid ? await opsFetch<Ledger>(`/rewards/members/${params.memberId}/ledger`) : null
  const reversed = new Set(result?.kind === 'ok' ? result.data.entries.map((e) => e.reverses_entry_id).filter(Boolean) : [])

  return (
    <>
      <ConsolePageHeader eyebrow="Reward disputes" title="Member ledger" description="Every balance is the sum of this journal. Nothing here edits a balance directly." />
      <p>
        <a href="/rewards-disputes">Back to disputes</a>
      </p>
      <ActionBanner done={searchParams.done} failed={searchParams.failed} />
      {!valid || result === null ? (
        <section className="console-notice" aria-labelledby="bad-member">
          <h2 id="bad-member">That member reference is not valid.</h2>
          <p>Open a ledger from the dispute queue.</p>
        </section>
      ) : result.kind !== 'ok' ? (
        <OpsState result={result} area="The member ledger" />
      ) : (
        <>
          <section className="console-section" aria-labelledby="account-heading">
            <h2 id="account-heading">Account</h2>
            <p>
              {result.data.consistency.ok
                ? 'The account matches its journal.'
                : 'The account does not match its journal. Do not act; escalate to engineering with this page.'}
            </p>
            <dl className={styles.facts}>
              {ACCOUNT_ORDER.filter((k) => k in result.data.consistency.account).map((k) => (
                <div key={k}>
                  <dt>{k.replace('_', ' ')}</dt>
                  <dd>{result.data.consistency.account[k]}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="console-section" aria-labelledby="journal-heading">
            <h2 id="journal-heading">Journal ({result.data.entries.length})</h2>
            <div className="console-table-region" role="region" aria-label="Ledger entries" tabIndex={0}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">When</th>
                    <th scope="col">Kind</th>
                    <th scope="col">Rule / reason</th>
                    <th scope="col">Points</th>
                    <th scope="col">Available</th>
                    <th scope="col">Recovery due</th>
                    <th scope="col">Evidence</th>
                    <th scope="col">Reverse</th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.entries.map((e) => (
                    <tr key={e.entry_id}>
                      <td>{formatTime(e.created_at)}</td>
                      <td>
                        {e.kind}
                        {e.state !== 'posted' ? ` (${e.state})` : ''}
                      </td>
                      <td>{e.rule_id ? RULE_LABEL[e.rule_id] ?? e.rule_id : e.reason ?? '—'}</td>
                      <td className={styles.num}>{e.points}</td>
                      <td className={styles.num}>{e.available_change}</td>
                      <td className={styles.num}>{e.recovery_due_change}</td>
                      <td className={styles.ref}>{e.evidence_refs.join(', ') || '—'}</td>
                      <td>
                        {(e.kind === 'credit' || e.kind === 'correction') && e.state === 'posted' && e.points > 0 && !reversed.has(e.entry_id) ? (
                          <form action={reverseEntry} className={styles.form}>
                            <input type="hidden" name="member_ref" value={params.memberId} />
                            <input type="hidden" name="entry_id" value={e.entry_id} />
                            <label htmlFor={`r-${e.entry_id}`}>Verified reason</label>
                            <input id={`r-${e.entry_id}`} name="reason" required maxLength={500} />
                            <label htmlFor={`v-${e.entry_id}`}>Evidence reference</label>
                            <input id={`v-${e.entry_id}`} name="evidence_ref" required maxLength={120} />
                            <button type="submit">Reverse</button>
                          </form>
                        ) : reversed.has(e.entry_id) ? (
                          'Reversed'
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  )
}
