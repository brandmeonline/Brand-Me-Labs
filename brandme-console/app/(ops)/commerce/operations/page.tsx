// /commerce/operations — purchases that need attention (lane: opus-commerce-agents).
// Read-only. No commerce worker or scheduler exists in this build: reconcile runs only
// when a verified provider event arrives for an order Brand.Me does not know yet (for
// that provider's unknown outcomes), or when it is called directly. This page never
// retries or re-submits a purchase, and it shows no member identifiers.
import { PageHeader } from '../../providers/_data/shell'
import { age, loadFromGateway, type OperationsQueue, type QueueOperation } from '../../providers/_data/gateway'
import { LoadState } from '../../providers/_data/states'

export const dynamic = 'force-dynamic'

function OperationTable({ id, title, empty, rows }: { id: string; title: string; empty: string; rows: QueueOperation[] }) {
  return (
    <section className="console-section" aria-labelledby={id}>
      <h2 id={id}>
        {title} ({rows.length})
      </h2>
      {rows.length === 0 ? (
        <p>{empty}</p>
      ) : (
        <div className="console-table-region" role="region" aria-labelledby={id} tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th scope="col">Operation</th>
                <th scope="col">Provider</th>
                <th scope="col">Reason</th>
                <th scope="col">Attempts</th>
                <th scope="col">Waiting</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.operation_id}>
                  <th scope="row">
                    <code>{o.operation_id}</code>
                  </th>
                  <td>
                    <code>{o.provider_id}</code>
                  </td>
                  <td>{o.reason_code ? <code>{o.reason_code}</code> : 'None recorded'}</td>
                  <td>{o.attempts}</td>
                  <td>
                    <time dateTime={o.updated_at}>{age(o.age_seconds)}</time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default async function CommerceOperationsPage() {
  const result = await loadFromGateway<OperationsQueue>('/commerce/ops/queue')
  return (
    <>
      <PageHeader
        eyebrow="Commerce"
        title="Purchases that need attention"
        description="An unknown outcome is resolved by asking the retailer about the same idempotency key. That check runs when a verified event from the retailer arrives. No worker or schedule runs it otherwise in this build, and nothing here re-sends a purchase."
      />
      {result.state !== 'ok' ? (
        <LoadState result={result} />
      ) : (
        <>
          <p>
            Environment <strong>{result.data.environment}</strong>, read at{' '}
            <time dateTime={result.data.observed_at}>{result.data.observed_at}</time>.
          </p>
          <OperationTable
            id="unknown-heading"
            title="Retailer outcome unknown"
            empty="No purchases are waiting on a retailer answer."
            rows={result.data.outcome_unknown}
          />
          <OperationTable
            id="stale-heading"
            title="Submission interrupted"
            empty="No submissions have stalled. A stalled submission stays here until reconciliation is run for it; nothing runs that on a schedule."
            rows={result.data.stale_submitting}
          />
          <section className="console-section" aria-labelledby="webhooks-heading">
            <h2 id="webhooks-heading">Provider events awaiting reconciliation ({result.data.webhooks_pending.length})</h2>
            {result.data.webhooks_pending.length === 0 ? (
              <p>Every verified provider event has been applied.</p>
            ) : (
              <ul>
                {result.data.webhooks_pending.map((w, i) => (
                  <li key={`${w.provider_id}-${i}`}>
                    <code>{w.provider_id}</code> <code>{w.event_type}</code>, waiting {age(w.age_seconds)}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </>
  )
}
