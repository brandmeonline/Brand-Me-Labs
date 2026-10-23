// /providers — registered providers and their effective capabilities (lane: opus-commerce-agents).
import Link from 'next/link'
import { ConsolePageHeader } from '@/components/console-page-header'
import { EXECUTABLE, loadFromGateway, type ProviderRow } from './_data/gateway'
import { LoadState } from './_data/states'

export const dynamic = 'force-dynamic'

const ACCESS: Record<string, string> = {
  unconfigured: 'Not configured',
  link_only: 'Link-out only',
  approved_publisher: 'Approved publisher',
  contracted_commerce: 'Contracted commerce',
  simulation: 'Simulation',
}

export default async function ProvidersPage() {
  const result = await loadFromGateway<{ items: ProviderRow[] }>('/providers')
  return (
    <>
      <ConsolePageHeader
        eyebrow="Providers"
        title="Retail and data providers"
        description="What each provider is actually allowed and verified to do in this environment. A provider is never connected by a switch here."
      />
      {result.state !== 'ok' ? (
        <LoadState result={result} />
      ) : result.data.items.length === 0 ? (
        <section className="console-notice" aria-labelledby="empty-heading">
          <h2 id="empty-heading">No providers are registered in this environment.</h2>
          <p>Providers are registered by the server at startup, with their access level and evidence.</p>
        </section>
      ) : (
        <section className="console-section" aria-labelledby="providers-heading">
          <h2 id="providers-heading">Registered providers</h2>
          <div className="console-table-region" role="region" aria-labelledby="providers-heading" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th scope="col">Provider</th>
                  <th scope="col">Environment</th>
                  <th scope="col">Access</th>
                  <th scope="col">Mode</th>
                  <th scope="col">Can run</th>
                  <th scope="col">Pages</th>
                </tr>
              </thead>
              <tbody>
                {result.data.items.map((p) => {
                  const runnable = p.capabilities.filter((c) => EXECUTABLE.has(c.state)).length
                  return (
                    <tr key={p.provider_id}>
                      <th scope="row">
                        <Link href={`/providers/${encodeURIComponent(p.provider_id)}`}>{p.display_name}</Link>
                        <div>
                          <code>{p.provider_id}</code>
                        </div>
                      </th>
                      <td>{p.environment}</td>
                      <td>{ACCESS[p.access_level] ?? p.access_level}</td>
                      <td>{p.simulation ? <strong>Simulation — no real orders</strong> : 'Provider'}</td>
                      <td>
                        {runnable} of {p.capabilities.length} capabilities
                      </td>
                      <td>
                        <Link href={`/providers/${encodeURIComponent(p.provider_id)}/setup`}>Setup</Link>{' '}
                        · <Link href={`/providers/${encodeURIComponent(p.provider_id)}/health`}>Health</Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  )
}
