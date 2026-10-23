// /providers/[id]/health — capability states and the evidence behind them (lane: opus-commerce-agents).
import Link from 'next/link'
import { PageHeader } from '../../_data/page-header'
import { capabilityLabel, loadFromGateway, type ProviderHealth } from '../../_data/gateway'
import { LoadState } from '../../_data/states'

export const dynamic = 'force-dynamic'

export default async function ProviderHealthPage({ params }: { params: { id: string } }) {
  const id = encodeURIComponent(params.id)
  const result = await loadFromGateway<ProviderHealth>(`/providers/${id}/health`)
  return (
    <>
      <PageHeader
        eyebrow="Provider health"
        title={result.state === 'ok' ? `Health: ${result.data.provider_id}` : 'Provider health'}
        description="Verified means evidence from a real sandbox or production operation, or a conformance run. A simulation never counts."
        actions={<Link href={`/providers/${id}`}>Provider record</Link>}
      />
      {result.state !== 'ok' ? (
        <LoadState result={result} backHref="/providers" />
      ) : (
        <>
          <section className="console-section" aria-labelledby="runnable-heading">
            <h2 id="runnable-heading">Operations that can run now</h2>
            {result.data.executable.length ? (
              <ul>
                {result.data.executable.map((c) => (
                  <li key={c}>
                    <code>{c}</code>
                    {result.data.simulation && ' (simulation)'}
                  </li>
                ))}
              </ul>
            ) : (
              <p>None. Members see a handoff or an unavailable state instead.</p>
            )}
          </section>
          <section className="console-section" aria-labelledby="evidence-heading">
            <h2 id="evidence-heading">Evidence by capability</h2>
            <div className="console-table-region" role="region" aria-labelledby="evidence-heading" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Capability</th>
                    <th scope="col">Status</th>
                    <th scope="col">Evidence</th>
                    <th scope="col">Last checked</th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.capabilities.map((c) => (
                    <tr key={c.name}>
                      <th scope="row">
                        <code>{c.name}</code>
                      </th>
                      <td>{capabilityLabel(c, result.data.simulation)}</td>
                      <td>{c.evidence_kind ? <code>{c.evidence_kind}</code> : 'None'}</td>
                      <td>{c.last_checked_at ?? 'Never'}</td>
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
