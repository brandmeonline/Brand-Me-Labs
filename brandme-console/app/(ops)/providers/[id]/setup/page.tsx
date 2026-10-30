/// <reference types="react/canary" />
// ^ React 18's types accept function form actions only with the canary augmentation; Next 15's app
//   router renders with its own React canary, where server-action forms are supported.
//
// /providers/[id]/setup — the six-section provider setup page (lane: opus-commerce-agents).
// Every state shown comes from the domain through the gateway. Saving never enables a capability;
// a capability is enabled only by Activate, which the domain refuses without every prerequisite
// and a fresh passing connection test. Credential inputs take a Secret Manager resource name only.
import Link from 'next/link'
import type { ReactNode } from 'react'
import { PageHeader } from '../../_data/shell'
import { activateCapability, assignTier, runConnectionTest, saveSetup } from '../../_data/actions'
import {
  capabilityLabel, loadFromGateway, type PartnerTier, type ProviderSetup, type SetupItem, type SetupSection, type TierIncludes,
} from '../../_data/gateway'
import { readOutcome, type Outcome } from '../../_data/outcome'
import { LoadState } from '../../_data/states'

export const dynamic = 'force-dynamic'

const STATE: Record<SetupItem['state'], string> = {
  done: 'Done',
  todo: 'To do',
  not_needed: 'Not needed',
  blocked: 'Blocked',
}
const ACCESS: Record<string, string> = {
  unconfigured: 'Not configured',
  link_only: 'Link-out only',
  approved_publisher: 'Approved publisher',
  contracted_commerce: 'Contracted commerce',
}
const RIGHTS: Record<string, string> = {
  display_images: 'Display product images',
  cache_images: 'Cache product images',
  transform_images: 'Transform images (resize, background removal)',
  retain_prices: 'Retain observed prices',
  affiliate_tracking: 'Use affiliate tracking',
  derive_3d_or_ai: 'Create derived 3D or AI representations',
}
const REFERENCES: { name: string; label: string; help: string }[] = [
  {
    name: 'approval_evidence_ref',
    label: 'Approval evidence reference',
    help: 'The reference of the provider’s written approval (for example the program acceptance record). Not a password.',
  },
  { name: 'catalog_ref', label: 'Enabled catalog reference', help: 'The catalog reference the approved account was granted.' },
  {
    name: 'endpoint_descriptor_ref',
    label: 'Endpoint and field-schema descriptor reference',
    help: 'Where the confirmed endpoints and field schema for the approved account are recorded.',
  },
]
const REFUSAL: Record<number, string> = {
  0: 'The console could not reach the gateway. Nothing is known to have changed.',
  400: 'The domain refused this input. Nothing was saved.',
  401: 'Sign in as an operator to make changes. Nothing was saved.',
  403: 'Your account does not have the provider:admin role. Nothing was changed.',
  404: 'That provider is not registered in this environment.',
  409: 'Refused: the recorded evidence does not support this change yet.',
  422: 'The gateway refused this input before it reached the domain. Nothing was saved.',
  501: 'This step is not built in this release.',
  503: 'The provider service is unavailable. Nothing is known to have changed.',
}

function OutcomeNotice({ outcome }: { outcome: Outcome }) {
  if (outcome.kind === 'refused') {
    const headline =
      outcome.code === 'revision_conflict'
        ? 'Someone changed this setup after you loaded it. Review the current state and try again.'
        : (REFUSAL[outcome.status] ?? `The gateway answered ${outcome.status}.`)
    return (
      <section id="outcome" className="console-notice" role="alert" aria-labelledby="outcome-heading" tabIndex={-1}>
        <h2 id="outcome-heading">{headline}</h2>
        <p>
          <code>{outcome.code}</code>
          {outcome.status ? ` (HTTP ${outcome.status})` : ''}
          {outcome.detail ? `: ${outcome.detail}` : ''}
        </p>
      </section>
    )
  }
  const text =
    outcome.kind === 'tested'
      ? `Connection test recorded: ${outcome.result}. See the results table below.`
      : outcome.kind === 'saved'
        ? 'Setup saved. Saving does not enable any capability.'
        : outcome.kind === 'tier_assigned'
          ? 'Partner tier recorded. A tier never enables a capability; 3D and AR still need a passing test and activation.'
          : 'Capability activated with the recorded passing test as evidence.'
  return (
    <section id="outcome" className="console-notice" role="status" aria-labelledby="outcome-heading" tabIndex={-1}>
      <h2 id="outcome-heading">{text}</h2>
    </section>
  )
}

function Checklist({ section }: { section: SetupSection }) {
  if (!section.items.length) return <p>Nothing in this section for this provider.</p>
  return (
    <ul>
      {section.items.map((item) => (
        <li key={item.key}>
          <strong>{item.label}</strong> — <span>{STATE[item.state] ?? item.state}</span>
          {item.detail && <div>{item.detail}</div>}
          {(item.evidence_ref || item.recorded_at) && (
            <div>
              {item.evidence_ref && (
                <>
                  Evidence <code>{item.evidence_ref}</code>
                </>
              )}
              {item.evidence_ref && item.recorded_at && ' · '}
              {item.recorded_at && <>Recorded {item.recorded_at}</>}
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}

function SectionBlock({ section, children }: { section: SetupSection; children?: ReactNode }) {
  const headingId = `section-${section.key}`
  return (
    <section className="console-section" aria-labelledby={headingId}>
      <h2 id={headingId}>{section.title}</h2>
      {section.description && <p>{section.description}</p>}
      <Checklist section={section} />
      {children}
    </section>
  )
}

const TIER_SOURCE: Record<PartnerTier['source'], string> = {
  assigned: 'assigned by an operator',
  unassigned: 'no tier assigned, so 3D and AR stay off',
  assigned_unknown: 'the assigned tier is not in the current pricing table, so 3D and AR stay off',
  unconfigured: 'no pricing table is configured in this environment, so 3D and AR stay off',
}

function Includes({ includes }: { includes: TierIncludes }) {
  const limit = (n: number | null) => (n === null ? 'no limit' : String(n))
  return (
    <ul>
      <li>Shelf: {limit(includes.shelf_variants)} active listings</li>
      <li>Customization up to: {includes.customization}</li>
      <li>Analytics: {includes.analytics}</li>
      <li>Member connection: {includes.member_connection.replaceAll('_', ' ')}</li>
    </ul>
  )
}

function TierBlock({ s, t, assign }: { s: ProviderSetup; t: PartnerTier; assign: (form: FormData) => Promise<void> }) {
  const options = s.tier_options ?? []
  return (
    <section className="console-section" aria-labelledby="section-tier">
      <h2 id="section-tier">Partner tier</h2>
      <p>
        {t.tier_id ? <code>{t.tier_id}</code> : 'No tier'} — {TIER_SOURCE[t.source]}. <strong>{t.price_label}.</strong>
      </p>
      {t.label && <p>{t.label}</p>}
      <Includes includes={t.includes} />
      {options.length > 0 && (
        <form action={assign} aria-label="Assign partner tier">
          <input type="hidden" name="version" value={s.version} />
          <label htmlFor="f-tier_id">Assign a tier</label>
          <br />
          <select id="f-tier_id" name="tier_id" defaultValue={t.source === 'assigned' && t.tier_id ? t.tier_id : ''}>
            <option value="">No tier (clear the assignment)</option>
            {options.map((o) => (
              <option key={o.tier_id} value={o.tier_id}>
                {o.display_name}
              </option>
            ))}
          </select>{' '}
          <button type="submit">Record tier (does not enable anything)</button>
        </form>
      )}
    </section>
  )
}

function TextInput({ name, label, help }: { name: string; label: string; help: string }) {
  return (
    <p>
      <label htmlFor={`f-${name}`}>{label}</label>
      <br />
      <input
        id={`f-${name}`}
        name={name}
        type="text"
        autoComplete="off"
        spellCheck={false}
        maxLength={256}
        aria-describedby={`h-${name}`}
      />
      <br />
      <small id={`h-${name}`}>{help} Leave empty to keep the current value.</small>
    </p>
  )
}

export default async function ProviderSetupPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const rawId = (await params).id
  const id = encodeURIComponent(rawId)
  const outcome = readOutcome(await searchParams)
  const result = await loadFromGateway<ProviderSetup>(`/providers/${id}/setup`)
  if (result.state !== 'ok') {
    return (
      <>
        <PageHeader eyebrow="Provider setup" title="Provider setup" actions={<Link href={`/providers/${id}`}>Provider record</Link>} />
        {outcome && <OutcomeNotice outcome={outcome} />}
        <LoadState result={result} backHref="/providers" />
      </>
    )
  }
  const s = result.data
  const section = (key: SetupSection['key']) => s.sections.find((x) => x.key === key)
  const editable = new Set(s.editable_fields)
  const caps = new Map(s.capabilities.map((c) => [c.name, c]))
  const tests = new Map((section('tests')?.items ?? []).map((i) => [i.key.replace(/^test:/, ''), i]))
  const save = saveSetup.bind(null, rawId)
  const runTest = runConnectionTest.bind(null, rawId)
  const activate = activateCapability.bind(null, rawId)
  const assign = assignTier.bind(null, rawId)
  const enables = section('enables')
  const prerequisites = section('prerequisites')
  const credentials = section('credentials')
  const dataUse = section('data_use')
  const activation = section('activation')

  return (
    <>
      <PageHeader
        eyebrow="Provider setup"
        title={`Setup: ${s.display_name}`}
        description="Each row comes from the server's provider record. Saving records setup only; nothing is enabled until a capability passes a connection test and is activated."
        actions={
          <>
            <Link href={`/providers/${id}`}>Provider record</Link> <Link href={`/providers/${id}/health`}>Health</Link>
          </>
        }
      />
      {s.simulation && (
        <section className="console-notice" aria-labelledby="sim-heading">
          <h2 id="sim-heading">Simulation provider — no real orders or payments</h2>
          <p>{s.disclosure}</p>
          <p>Its connection tests exercise fictional data. They are recorded as sandbox evidence and never as verified.</p>
        </section>
      )}
      {outcome && <OutcomeNotice outcome={outcome} />}

      {enables && <SectionBlock section={enables} />}

      {s.tier && <TierBlock s={s} t={s.tier} assign={assign} />}

      {editable.size > 0 ? (
        <form action={save} aria-label="Save provider setup">
          <input type="hidden" name="version" value={s.version} />
          {prerequisites && (
            <SectionBlock section={prerequisites}>
              {editable.has('access_level') && (
                <p>
                  <label htmlFor="f-access_level">Authorized access level</label>
                  <br />
                  <select id="f-access_level" name="access_level" defaultValue="" aria-describedby="h-access_level">
                    <option value="">Keep current ({ACCESS[s.access_level] ?? s.access_level})</option>
                    {s.access_levels.map((l) => (
                      <option key={l} value={l}>
                        {ACCESS[l] ?? l}
                      </option>
                    ))}
                  </select>
                  <br />
                  <small id="h-access_level">
                    Anything beyond link-out needs recorded approval evidence first. Choosing a level does not enable any capability.
                  </small>
                </p>
              )}
              {editable.has('program_application_opened') && (
                <p>
                  <label htmlFor="f-program_application_opened">Program application submitted by an operator</label>
                  <br />
                  <select id="f-program_application_opened" name="program_application_opened" defaultValue="">
                    <option value="">Keep current</option>
                    <option value="yes">Yes — applied manually through the official program page</option>
                    <option value="no">No</option>
                  </select>
                </p>
              )}
              {REFERENCES.filter((r) => editable.has(r.name)).map((r) => (
                <TextInput key={r.name} {...r} />
              ))}
            </SectionBlock>
          )}
          {credentials && (
            <SectionBlock section={credentials}>
              <p>
                Credential:{' '}
                {s.credential_configured ? (
                  <>
                    configured (fingerprint <code>{s.credential_fingerprint}</code>
                    {s.credential_rotated_at ? `, rotated ${s.credential_rotated_at}` : ''}). The reference itself is never shown again.
                  </>
                ) : (
                  'none configured.'
                )}
              </p>
              {editable.has('account_ref') && (
                <TextInput name="account_ref" label="Provider account reference" help="The approved account’s reference, not a login or password." />
              )}
              {editable.has('credential_secret_ref') && (
                <p>
                  <label htmlFor="f-credential_secret_ref">Secret Manager resource name</label>
                  <br />
                  <input
                    id="f-credential_secret_ref"
                    name="credential_secret_ref"
                    type="text"
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={512}
                    placeholder="projects/<project>/secrets/<name>/versions/<number>"
                    aria-describedby="h-credential_secret_ref"
                  />
                  <br />
                  <small id="h-credential_secret_ref">
                    Store the credential in Secret Manager first, then enter only its resource name. Never paste the secret itself:
                    values that look like keys, private keys or long random text are refused. Leave empty to keep the current
                    credential; entering a new version records a rotation.
                  </small>
                </p>
              )}
            </SectionBlock>
          )}
          {dataUse && (
            <SectionBlock section={dataUse}>
              {editable.has('data_use') && (
                <fieldset aria-describedby="h-data_use">
                  <legend>Rights granted by the agreement</legend>
                  <small id="h-data_use">
                    Mark every right, or leave all of them unchanged. Feed access does not grant these by itself.
                  </small>
                  {s.data_use_rights.map((r) => (
                    <p key={r}>
                      <input type="hidden" name="data_use_right" value={r} />
                      <label htmlFor={`f-use-${r}`}>{RIGHTS[r] ?? r}</label>{' '}
                      <select id={`f-use-${r}`} name={`data_use:${r}`} defaultValue="">
                        <option value="">Keep current</option>
                        <option value="yes">Permitted</option>
                        <option value="no">Not permitted</option>
                      </select>
                    </p>
                  ))}
                </fieldset>
              )}
            </SectionBlock>
          )}
          <p>
            <button type="submit">Save setup (does not enable anything)</button>
          </p>
        </form>
      ) : (
        <>
          {prerequisites && <SectionBlock section={prerequisites} />}
          {credentials && <SectionBlock section={credentials} />}
          {dataUse && <SectionBlock section={dataUse} />}
          <p>Nothing on this provider is entered by an operator; its setup is fixed by the adapter.</p>
        </>
      )}

      <section className="console-section" aria-labelledby="section-tests">
        <h2 id="section-tests">{section('tests')?.title ?? 'Connection tests'}</h2>
        <p>
          A test exercises one exact capability. Only a passing test with operation or conformance evidence can support
          activation, and only for {s.freshness_hours} hours. Reaching a host or checking a link verifies nothing more.
        </p>
        {!s.connection_test_available && <p>This adapter has no connection test, so its capabilities cannot be activated here.</p>}
        {s.testable_capabilities.length === 0 ? (
          <p>This provider offers no capability to test.</p>
        ) : (
          <div className="console-table-region" role="region" aria-labelledby="section-tests" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th scope="col">Capability</th>
                  <th scope="col">Current status</th>
                  <th scope="col">Latest test</th>
                  <th scope="col">Run</th>
                </tr>
              </thead>
              <tbody>
                {s.testable_capabilities.map((name) => {
                  const cap = caps.get(name)
                  const latest = tests.get(name)
                  return (
                    <tr key={name}>
                      <th scope="row">
                        <code>{name}</code>
                      </th>
                      <td>{cap ? capabilityLabel(cap, s.simulation) : 'Unknown'}</td>
                      <td>
                        {latest ? STATE[latest.state] : 'Not run'}
                        {latest?.detail && <div>{latest.detail}</div>}
                      </td>
                      <td>
                        <form action={runTest}>
                          <input type="hidden" name="capability" value={name} />
                          <input type="hidden" name="mode" value="read_only_test" />
                          <button type="submit" aria-label={`Run read-only test for ${name}`}>
                            Run read-only test
                          </button>
                        </form>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {activation && (
        <section className="console-section" aria-labelledby="section-activation">
          <h2 id="section-activation">{activation.title}</h2>
          <p>
            Activation is the only step that enables a capability. The domain refuses it unless every prerequisite is done and
            the latest test for that capability passed within {s.freshness_hours} hours.
          </p>
          {activation.items.length === 0 ? (
            <p>Nothing to activate.</p>
          ) : (
            <ul>
              {activation.items.map((item) => {
                const name = item.key.replace(/^activate:/, '')
                return (
                  <li key={item.key}>
                    <strong>{item.label}</strong> — <span>{STATE[item.state] ?? item.state}</span>
                    {item.detail && <div>{item.detail}</div>}
                    {item.state === 'todo' && (
                      <form action={activate}>
                        <input type="hidden" name="capability" value={name} />
                        <input type="hidden" name="version" value={s.version} />
                        <button type="submit" aria-label={`Activate ${name}`}>
                          Activate
                        </button>
                      </form>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      )}

      <section className="console-section" aria-labelledby="runs-heading">
        <h2 id="runs-heading">Connection test results</h2>
        {s.recent_runs.length === 0 ? (
          <p>No connection test has been run for this provider in this environment.</p>
        ) : (
          <div className="console-table-region" role="region" aria-labelledby="runs-heading" tabIndex={0}>
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
                {s.recent_runs.map((r) => (
                  <tr key={r.run_id} aria-current={outcome?.kind === 'tested' && outcome.run === r.run_id ? 'true' : undefined}>
                    <th scope="row">{r.ran_at}</th>
                    <td>
                      {r.environment}
                      {s.simulation && ' (simulation)'}
                    </td>
                    <td>
                      <code>{r.capability}</code>
                      {r.mode && <div>{r.mode.replace(/_/g, ' ')}</div>}
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
                      <code>{r.evidence_kind}</code> · <code>{r.evidence_ref}</code>
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
  )
}
