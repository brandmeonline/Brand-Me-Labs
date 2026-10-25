// /providers/[id] — one provider's sanitized record (lane: opus-commerce-agents).
import Link from 'next/link'
import { PageHeader } from '../_data/shell'
import { capabilityLabel, loadFromGateway, railLabel, STRIPE_TEST_NOTICE, type ProviderDetail } from '../_data/gateway'
import { LoadState } from '../_data/states'

export const dynamic = 'force-dynamic'

export default async function ProviderPage({ params }: { params: Promise<{ id: string }> }) {
  const id = encodeURIComponent((await params).id)
  const result = await loadFromGateway<ProviderDetail>(`/providers/${id}`)
  if (result.state !== 'ok') {
    return (
      <>
        <PageHeader eyebrow="Providers" title="Provider" />
        <LoadState result={result} backHref="/providers" />
      </>
    )
  }
  const p = result.data
  const protocols = Object.entries(p.protocols)
  return (
    <>
      <PageHeader
        eyebrow="Providers"
        title={p.display_name}
        description={p.disclosure}
        actions={
          <>
            <Link href={`/providers/${id}/setup`}>Setup</Link> <Link href={`/providers/${id}/health`}>Health</Link>
          </>
        }
      />
      {p.simulation && (
        <section className="console-notice" aria-labelledby="sim-heading">
          <h2 id="sim-heading">Simulation provider</h2>
          <p>Deterministic local adapter for demo and development. It never places a real order and is refused in sandbox and production.</p>
        </section>
      )}
      {p.payment_rail?.mode === 'sandbox' && (
        <section className="console-notice" aria-labelledby="rail-heading">
          <h2 id="rail-heading">Stripe test mode</h2>
          <p>{STRIPE_TEST_NOTICE}</p>
        </section>
      )}
      <section className="console-section" aria-labelledby="record-heading">
        <h2 id="record-heading">Record</h2>
        <dl>
          <dt>Provider ID</dt>
          <dd>
            <code>{p.provider_id}</code>
          </dd>
          <dt>Environment</dt>
          <dd>{p.environment}</dd>
          <dt>Access level</dt>
          <dd>{p.access_level}</dd>
          <dt>Credential</dt>
          <dd>{p.credential_configured ? 'Configured (reference held server-side)' : 'None configured'}</dd>
          <dt>Payment rail</dt>
          <dd>
            {p.payment_rail
              ? `${railLabel(p.payment_rail)}; webhooks ${p.payment_rail.webhooks_configured ? 'configured' : 'not configured'}`
              : 'None (the merchant handles payment outside Brand.Me)'}
          </dd>
          <dt>Protocols</dt>
          <dd>{protocols.length ? protocols.map(([k, v]) => `${k} ${v}`).join(', ') : 'None verified'}</dd>
          <dt>Allowed redirect hosts</dt>
          <dd>{p.allowed_redirect_hosts.length ? p.allowed_redirect_hosts.join(', ') : 'None'}</dd>
          <dt>Countries</dt>
          <dd>{p.country_codes.join(', ') || 'None'}</dd>
          <dt>Record version</dt>
          <dd>{p.version}</dd>
        </dl>
      </section>
      <section className="console-section" aria-labelledby="caps-heading">
        <h2 id="caps-heading">Capabilities</h2>
        <div className="console-table-region" role="region" aria-labelledby="caps-heading" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th scope="col">Capability</th>
                <th scope="col">Status</th>
                <th scope="col">Reason</th>
                <th scope="col">Last checked</th>
              </tr>
            </thead>
            <tbody>
              {p.capabilities.map((c) => (
                <tr key={c.name}>
                  <th scope="row">
                    <code>{c.name}</code>
                  </th>
                  <td>{capabilityLabel(c, p.simulation)}</td>
                  <td>
                    <code>{c.reason_code}</code>
                  </td>
                  <td>{c.last_checked_at ?? 'Never'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
