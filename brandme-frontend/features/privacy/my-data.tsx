'use client'

import Link from 'next/link'
import { useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useResource } from '@/lib/client/use-resource'
import {
  command,
  downloadDataExport,
  explainError,
  GatewayError,
} from '@/lib/client/gateway'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import { ResourceState } from '@/components/ui/resource-state'

type Category = {
  key: string
  title: string
  supplied_by: string
  visible_to: string[]
  retention: string
  on_edit: string
  on_delete: string
  retention_basis: string | null
}
type Inventory = {
  environment: string
  categories: Category[]
  coverage: { domains: string[]; full_account: boolean }
  capabilities: { export: string; deletion: string }
}
type ExportCapability = {
  status: 'available'
  environment: string
  network: string
  categories: string[]
  full_account: false
  selected_categories_only: true
}
type ExportJob = {
  job_id: string
  state: string
  categories: string[]
  coverage: {
    domains: string[]
    full_account: false
    selected_categories_only: true
  }
  environment: string
  network: string
  requested_at: string
  expires_at: string
  completed_at: string | null
  package_sha256: string | null
  package_bytes: number | null
  failure_code: string | null
  download_available: boolean
}
type DeletionReceipt = {
  job_id: string
  environment: string
  scope: string
  state: string
  categories: string[]
  requested_at: string
  completed_at: string | null
  outcomes: Record<
    string,
    {
      status: string
      rows_affected: string | null
      derived_purged: string | null
    }
  > | null
}
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
const plain = (value: string) => value.replaceAll('_', ' ')

export function MyData() {
  const inventory = useResource<Inventory>('/me/data')
  const capability = useResource<ExportCapability>(
    inventory.data?.capabilities.export === 'selected_categories'
      ? '/me/exports/capability'
      : null,
  )
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState('')
  const [receipt, setReceipt] = useState('')
  const pending = useRef<{ key: string; categories: string[] } | null>(null)
  const router = useRouter()
  const cap = capability.data
  const allowed =
    cap?.status === 'available' &&
    cap.full_account === false &&
    cap.selected_categories_only === true &&
    cap.environment === inventory.data?.environment
      ? new Set(
          cap.categories.filter((key) =>
            inventory.data?.categories.some((c) => c.key === key),
          ),
        )
      : new Set<string>()
  const exportable = selected.filter((key) => allowed.has(key)).sort()
  async function requestExport() {
    if (!exportable.length || busy) return
    setBusy(true)
    setMessage('')
    try {
      if (
        !pending.current ||
        JSON.stringify(pending.current.categories) !==
          JSON.stringify(exportable)
      )
        pending.current = { key: crypto.randomUUID(), categories: exportable }
      const job = await command<ExportJob>(
        '/me/exports',
        { categories: pending.current.categories },
        { key: pending.current.key },
      )
      router.push(`/me/data/exports/${job.job_id}`)
    } catch (error) {
      setMessage(explainError(error))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="bm-flow-stack">
      <ResourceState {...inventory} retry={inventory.reload} />
      {inventory.data && (
        <>
          <p className="bm-notice">
            {inventory.data.coverage.full_account
              ? 'Account data inventory'
              : `Partial inventory: ${inventory.data.coverage.domains.join(', ')}.`}{' '}
            Environment: {inventory.data.environment}. Only the categories
            reported below are covered.
          </p>
          <fieldset disabled={busy}>
            <legend>Select the data to include in your export</legend>
            <div className="bm-flow-stack">
              {inventory.data.categories.map((category) => (
                <article className="bm-flow-card" key={category.key}>
                  <h2>{category.title}</h2>
                  <dl className="bm-facts">
                    <dt>Supplied by</dt>
                    <dd>{plain(category.supplied_by)}</dd>
                    <dt>Visible to</dt>
                    <dd>{category.visible_to.join(', ')}</dd>
                    <dt>Retention</dt>
                    <dd>{category.retention}</dd>
                    <dt>Editing</dt>
                    <dd>{category.on_edit}</dd>
                    <dt>When deleted</dt>
                    <dd>
                      {plain(category.on_delete)}
                      {category.retention_basis
                        ? `. ${category.retention_basis}`
                        : ''}
                    </dd>
                  </dl>
                  {allowed.has(category.key) && (
                    <label className="bm-checkbox-label">
                      <input
                        type="checkbox"
                        checked={selected.includes(category.key)}
                        onChange={(event) =>
                          setSelected((current) =>
                            event.target.checked
                              ? [...current, category.key]
                              : current.filter((key) => key !== category.key),
                          )
                        }
                      />
                      Include {category.title}
                    </label>
                  )}
                </article>
              ))}
            </div>
          </fieldset>
          <section className="bm-flow-card">
            <h2>Export selected data</h2>
            {inventory.data.capabilities.export === 'selected_categories' ? (
              <>
                <ResourceState {...capability} retry={capability.reload} />
                <p>
                  This export covers selected supported categories. It does not
                  include your full account or private wallet ownership secrets.
                  The server requires a recent sign-in.
                </p>
                <Button
                  pending={busy}
                  disabled={!exportable.length}
                  onClick={requestExport}
                >
                  Request export of {exportable.length} selected categories
                </Button>
              </>
            ) : (
              <p>
                The connected service has not made export available for this
                inventory.
              </p>
            )}
            <p role="status">{message}</p>
          </section>
          <section className="bm-flow-card">
            <h2>Deletion and retention</h2>
            <p>
              A deletion request is not available through the connected
              inventory. The category descriptions above show retention and
              public-ledger exceptions; no deletion has been requested by this
              page.
            </p>
            <p>
              You can inspect a deletion receipt using a job reference you
              already received.
            </p>
            <form
              onSubmit={(event) => {
                event.preventDefault()
                if (uuid.test(receipt))
                  router.push(`/me/data/deletion/${receipt.toLowerCase()}`)
              }}
            >
              <Input
                label="Deletion job reference"
                value={receipt}
                onChange={(event) => setReceipt(event.target.value.trim())}
                required
              />
              <Button
                variant="secondary"
                type="submit"
                disabled={!uuid.test(receipt)}
              >
                View deletion receipt
              </Button>
            </form>
          </section>
        </>
      )}
      <Link href="/me/connections">Manage account connection</Link>
    </div>
  )
}

export function DataExport({ id }: { id: string }) {
  const r = useResource<ExportJob>(uuid.test(id) ? `/me/exports/${id}` : null)
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState('')
  async function download() {
    if (!r.data?.download_available || !r.data.package_sha256 || busy) return
    const expected = r.data.package_sha256
    setBusy(true)
    setMessage('')
    try {
      const file = await downloadDataExport(id, expected)
      const url = URL.createObjectURL(file)
      const link = document.createElement('a')
      link.href = url
      link.download = `brandme-selected-data-${id}.json`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setMessage('Your verified export download has started.')
    } catch (error) {
      setMessage(
        error instanceof GatewayError
          ? explainError(error)
          : 'The export could not be verified or downloaded. Refresh its status before trying again.',
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="bm-flow-stack">
      {!uuid.test(id) ? (
        <p role="alert">This export reference is invalid.</p>
      ) : (
        <ResourceState {...r} retry={r.reload} />
      )}
      {r.data && (
        <section className="bm-flow-card">
          <h2>Selected-category export: {plain(r.data.state)}</h2>
          <p>
            {r.data.environment} · {r.data.network} ·{' '}
            {r.data.coverage.domains.join(', ')}
          </p>
          <p>
            Includes: {r.data.categories.join(', ')}. This is a partial export;
            private ownership secrets are excluded.
          </p>
          <p>
            Expires:{' '}
            <time dateTime={r.data.expires_at}>
              {new Date(r.data.expires_at).toLocaleString()}
            </time>
          </p>
          {r.data.failure_code && (
            <p role="alert">{plain(r.data.failure_code)}</p>
          )}
          <div className="bm-actions">
            <Button variant="secondary" onClick={r.reload}>
              Refresh export status
            </Button>
            {r.data.state === 'ready' &&
              r.data.download_available &&
              r.data.package_sha256 && (
                <Button pending={busy} onClick={download}>
                  Download verified JSON export
                </Button>
              )}
          </div>
          <p role="status">{message}</p>
        </section>
      )}
      <Link href="/me/data">Back to My Data</Link>
    </div>
  )
}

export function DeletionStatus({ id }: { id: string }) {
  const r = useResource<DeletionReceipt>(
    uuid.test(id) ? `/me/deletion/${id}` : null,
  )
  return (
    <div className="bm-flow-stack">
      {!uuid.test(id) ? (
        <p role="alert">This deletion reference is invalid.</p>
      ) : (
        <ResourceState {...r} retry={r.reload} />
      )}
      {r.data && (
        <section className="bm-flow-card">
          <h2>Deletion request: {plain(r.data.state)}</h2>
          <p>
            {r.data.environment} · {r.data.scope} scope
          </p>
          {r.data.outcomes ? (
            <ul>
              {Object.entries(r.data.outcomes).map(([category, outcome]) => (
                <li key={category}>
                  {category}: {plain(outcome.status)}
                  {outcome.rows_affected !== null
                    ? ` · ${outcome.rows_affected} records affected`
                    : ''}
                  {outcome.derived_purged !== null
                    ? ` · ${outcome.derived_purged} derived records purged`
                    : ''}
                </li>
              ))}
            </ul>
          ) : (
            <p>No completed outcomes have been reported yet.</p>
          )}
          <p>
            A completed job can include retained records and non-erasable public
            commitments. Each category’s outcome determines what happened.
          </p>
          <Button variant="secondary" onClick={r.reload}>
            Refresh deletion status
          </Button>
        </section>
      )}
      <Link href="/me/data">Back to My Data</Link>
    </div>
  )
}
