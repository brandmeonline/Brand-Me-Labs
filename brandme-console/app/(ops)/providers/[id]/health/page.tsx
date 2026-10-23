// /providers/[id]/health — capability states and the evidence behind them (lane: opus-commerce-agents).
import Link from 'next/link'
import { PageHeader } from '../../_data/shell'
import { capabilityLabel, loadFromGateway, type ProviderHealth, type VerificationRuns } from '../../_data/gateway'
import { LoadState } from '../../_data/states'

export const dynamic = 'force-dynamic'

export default async function ProviderHealthPage({ params }: { params: Promise<{ id: string }> }) {
  const id = encodeURIComponent((await params).id)
  const [result, runs] = await Promise.all([
    loadFromGateway<ProviderHealth>(`/providers/${id}/health`),
    loadFromGateway<VerificationRuns>(`/providers/${id}/verification-runs?limit=10`),
  ])
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
          <section className="console-section" aria-labelledby="recent-runs-heading">
            <h2 id="recent-runs-heading">Recent connection tests</h2>
            {runs.state !== 'ok' ? (
              <p>Connection test history could not be loaded here; see the setup page.</p>
            ) : runs.data.items.length === 0 ? (
              <p>
                No connection test has been run. <Link href={`/providers/${id}/setup`}>Run one from the setup page.</Link>
              </p>
            ) : (
              <div className="console-table-region" role="region" aria-labelledby="recent-runs-heading" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Time (UTC)</th>
                      <th scope="col">Environment</th>
                      <th scope="col">Capability</th>
                      <th scope="col">Result</th>
                      <th scope="col">Sanitized evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.data.items.map((r) => (
                      <tr key={r.run_id}>
                        <th scope="row">{r.ran_at}</th>
                        <td>
                          {r.environment}
                          {runs.data.simulation && ' (simulation)'}
                        </td>
                        <td>
                          <code>{r.capability}</code>
                        </td>
                        <td>
                          {r.result}
                          {r.reason_code && (
                            <div>
                              <code>{r.reason_code}</code>
                            </div>
                          )}
                        </td>
                        <td>
                          <code>{r.evidence_kind}</code>
                          <div>{r.sanitized_summary}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </>
  )
}
