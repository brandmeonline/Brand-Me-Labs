// /providers/[id]/setup — setup checklist, read-only in this release (lane: opus-commerce-agents).
import Link from 'next/link'
import { PageHeader } from '../../_data/shell'
import { loadFromGateway, type ProviderSetup } from '../../_data/gateway'
import { LoadState } from '../../_data/states'

export const dynamic = 'force-dynamic'

const LABELS: Record<string, string> = {
  access_level: 'Authorized access level',
  operator_account: 'Operator account',
  credential: 'Credential in Secret Manager',
  data_use_rights: 'Data-use rights (images, prices, tracking, derived 3D/AI)',
  verification_evidence: 'Verification evidence from a real operation or conformance run',
}
const STATE: Record<string, string> = { done: 'Done', todo: 'Not done', not_needed: 'Not needed' }

export default async function ProviderSetupPage({ params }: { params: Promise<{ id: string }> }) {
  const id = encodeURIComponent((await params).id)
  const result = await loadFromGateway<ProviderSetup>(`/providers/${id}/setup`)
  return (
    <>
      <PageHeader
        eyebrow="Provider setup"
        title={result.state === 'ok' ? `Setup: ${result.data.provider_id}` : 'Provider setup'}
        description="Each item comes from the server's provider record. Nothing on this page can mark a step done."
        actions={<Link href={`/providers/${id}`}>Provider record</Link>}
      />
      {result.state !== 'ok' ? (
        <LoadState result={result} backHref="/providers" />
      ) : (
        <>
          <section className="console-section" aria-labelledby="checklist-heading">
            <h2 id="checklist-heading">Checklist</h2>
            <ol>
              {result.data.items.map((item) => (
                <li key={item.key}>
                  <strong>{LABELS[item.key] ?? item.key}</strong>: {STATE[item.state] ?? item.state}
                  {typeof item.value === 'string' && (
                    <>
                      {' '}
                      (<code>{item.value}</code>)
                    </>
                  )}
                </li>
              ))}
            </ol>
          </section>
          {!result.data.editable && (
            <section className="console-notice" aria-labelledby="readonly-heading">
              <h2 id="readonly-heading">Read-only in this release</h2>
              <p>{result.data.note}</p>
            </section>
          )}
        </>
      )}
    </>
  )
}
