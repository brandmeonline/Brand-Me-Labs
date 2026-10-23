'use client'
import { useEffect, useRef, useState } from 'react'
import { useResource } from '@/lib/client/use-resource'
import { command, explainError } from '@/lib/client/gateway'
import { Button } from '@/components/ui/button'
import { Input, Switch } from '@/components/ui/field'
import { Slider } from '@/components/ui/slider'
import { Dialog } from '@/components/ui/dialog'
import { ResourceState } from '@/components/ui/resource-state'
import { AXES, type Axis, type Persona, type Recommendations } from './types'
import { RecommendationList } from './recommendations'

export function LookingGlass() {
  const resource = useResource<Persona>('/me/persona')
  const [snapshot, setSnapshot] = useState<{ memberId: string; snapshot_id: string }|null>(null)
  return <><ResourceState {...resource} retry={resource.reload}/>{resource.data &&
    <Editor key={`${resource.data.profile.member_id}:${resource.data.profile.version}`} initial={resource.data} reload={resource.reload}
      snapshot={snapshot?.memberId === resource.data.profile.member_id ? snapshot : null}
      saveSnapshot={value => setSnapshot({ ...value, memberId: resource.data!.profile.member_id })}/>}</>
}
function Editor({ initial, reload, snapshot, saveSnapshot }: { initial: Persona; reload: () => void; snapshot: {snapshot_id:string}|null; saveSnapshot:(value:{snapshot_id:string})=>void }) {
  const [axes, setAxes] = useState(initial.axes)
  const [learning, setLearning] = useState(initial.profile.learning_enabled)
  const [constraints, setConstraints] = useState(initial.constraints)
  const [all, setAll] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [preview, setPreview] = useState<Recommendations|null>(null)
  const [reset, setReset] = useState(false)
  const revision = useRef(0)
  const evidence = useResource<{items: { evidence_id: string; source_type: string; suppressed?: boolean }[]}>('/me/persona/evidence')
  const changes = axes.filter(a => { const old = initial.axes.find(o => o.axis === a.axis); return old?.declared !== a.declared || old?.locked !== a.locked })
    .map(a => ({ axis: a.axis, value: a.declared, locked: a.locked }))
  const settings = Object.fromEntries(axes.filter(a => {
    const old = initial.axes.find(o => o.axis === a.axis)
    return old?.hidden !== a.hidden || old?.inference_allowed !== a.inference_allowed || old?.adapt_enabled !== a.adapt_enabled
  }).map(a => [a.axis, { hidden: a.hidden, inference_allowed: a.inference_allowed, adapt_enabled: a.adapt_enabled }]))
  const dirty = changes.length > 0 || Object.keys(settings).length > 0 || learning !== initial.profile.learning_enabled || JSON.stringify(constraints) !== JSON.stringify(initial.constraints)
  const draft = JSON.stringify({ changes, constraints })
  useEffect(() => {
    const id = String(++revision.current)
    if (!dirty) { setPreview(null); return }
    const timer = setTimeout(() => {
      command<{ client_revision: string; recommendations: Recommendations }>('/me/persona/preview', { ...JSON.parse(draft), client_revision: id })
        .then(result => { if (id === String(revision.current) && result.client_revision === id) setPreview(result.recommendations) })
        .catch(() => { if (id === String(revision.current)) setPreview(null) })
    }, 300)
    return () => { clearTimeout(timer); ++revision.current }
  }, [draft, dirty])
  function update(axis: string, patch: Partial<Axis>) { setAxes(list => list.map(a => a.axis === axis ? { ...a, ...patch } : a)) }
  async function run(action: () => Promise<unknown>, success: string, refresh = true) {
    setBusy(true); setError(null); setMessage('')
    try { await action(); setMessage(success); if (refresh) reload() }
    catch (e) { setError(e) } finally { setBusy(false) }
  }
  async function apply() {
    await run(async () => {
      await command('/me/persona', { changes, axis_settings: settings, learning_enabled: learning, constraints,
        client_revision: crypto.randomUUID() }, { method: 'PATCH', version: initial.profile.version })
    }, 'Your preferences have been saved.')
  }
  return <div className="bm-flow-stack">
    <p className="bm-notice">Your choices stay editable. Changes remain a draft until you apply them. Saved revision {initial.profile.version}.</p>
    <div role="status">{message}</div>{Boolean(error) && <p role="alert">{explainError(error)} <button className="bm-text-link" onClick={reload}>Reload saved version</button></p>}
    <div className="bm-persona-layout"><section aria-label="Style preferences" className="bm-flow-stack">
      {(all ? AXES : AXES.slice(0,3)).map(([key,label,left,right]) => {
        const a = axes.find(x => x.axis === key); if (!a) return null
        return <article key={key} className="bm-flow-card">
          <Slider label={label} leftLabel={left} rightLabel={right} value={a.declared} disabled={busy}
            onValueChange={value => update(key,{declared:value,locked:value !== null})}/>
          <details><summary>How {label.toLowerCase()} is used</summary>
            <dl className="bm-facts"><dt>You chose</dt><dd>{a.declared ?? 'Not set'}</dd><dt>Brand.Me inferred</dt><dd>{a.inferred ?? 'Unknown'}</dd>
              <dt>Saved ranking value</dt><dd>{a.effective ?? 'Neutral fallback, not a preference'}</dd><dt>Source</dt><dd>{a.effective_source.replaceAll('_',' ')}</dd>
              <dt>Evidence</dt><dd>{a.inferred_evidence_count} observations</dd></dl>
            <Switch label={`Lock ${label.toLowerCase()}`} checked={a.locked} disabled={busy || a.declared === null} onCheckedChange={locked => update(key,{locked})}/>
            <Switch label={`Allow inference for ${label.toLowerCase()}`} checked={a.inference_allowed} disabled={busy} onCheckedChange={inference_allowed => update(key,{inference_allowed})}/>
            <Switch label={`Let ${label.toLowerCase()} adapt`} description="Server limits and review still apply." checked={a.adapt_enabled} disabled={busy || a.locked} onCheckedChange={adapt_enabled => update(key,{adapt_enabled})}/>
            <Switch label={`Hide ${label.toLowerCase()} from my profile`} checked={a.hidden} disabled={busy} onCheckedChange={hidden => update(key,{hidden})}/>
          </details>
        </article>
      })}
      <Button variant="secondary" onClick={() => setAll(!all)}>{all ? 'Show three preferences' : 'All 12 preferences'}</Button>
    </section><aside className="bm-flow-stack" aria-label="Recommendation preview">
      <h2 className="bm-section-title">What changes for you</h2>
      {preview ? <RecommendationList data={preview}/> : <p>{dirty ? 'A recommendation preview will appear when the ranking service is available.' : 'Adjust a preference to compare recommendations before saving.'}</p>}
      <p className="bm-support">Reasons come from the ranking service. A preview never saves your profile.</p>
    </aside></div>
    <section className="bm-flow-card"><h2 className="bm-section-title">Your boundaries</h2>
      <Switch label="Learn from my activity" checked={learning} onCheckedChange={setLearning}/>
      <Switch label="Prefer things I own" checked={constraints.prefer_owned} onCheckedChange={prefer_owned => setConstraints(c=>({...c,prefer_owned}))}/>
      <Switch label="Use social activity for recommendations" checked={constraints.social_signals_enabled} onCheckedChange={social_signals_enabled => setConstraints(c=>({...c,social_signals_enabled}))}/>
      <Input label="Budget ceiling in minor units" description="For USD, 15000 means $150.00. Leave blank for no ceiling." inputMode="numeric" pattern="[0-9]*" value={constraints.budget_ceiling_minor ?? ''}
        onChange={e => { if (/^[0-9]*$/.test(e.target.value)) setConstraints(c=>({...c,budget_ceiling_minor:e.target.value || null,budget_currency:c.budget_currency || 'USD'})) }}/>
      <Input label="Budget currency" maxLength={3} value={constraints.budget_currency ?? 'USD'} onChange={e=>setConstraints(c=>({...c,budget_currency:e.target.value.toUpperCase()}))}/>
      <Input label="Excluded brands" description="Separate names with commas." value={constraints.excluded_brands.join(', ')} onChange={e=>setConstraints(c=>({...c,excluded_brands:e.target.value.split(',').map(v=>v.trim())}))}/>
      <Input label="Excluded materials" value={constraints.excluded_materials.join(', ')} onChange={e=>setConstraints(c=>({...c,excluded_materials:e.target.value.split(',').map(v=>v.trim())}))}/>
    </section>
    <div className="bm-actions"><Button pending={busy} disabled={!dirty} onClick={apply}>Apply changes</Button>
      <Button variant="secondary" disabled={busy || !dirty} onClick={()=>{setAxes(initial.axes);setConstraints(initial.constraints);setLearning(initial.profile.learning_enabled)}}>Discard draft</Button>
      <Button variant="secondary" disabled={busy} onClick={()=>run(async()=>saveSnapshot(await command('/me/persona/snapshots',{name:'Before my next change'},{key:crypto.randomUUID()})),'Snapshot saved.',false)}>Save snapshot</Button>
      {snapshot && <Button variant="secondary" disabled={busy} onClick={()=>run(()=>command(`/me/persona/snapshots/${snapshot.snapshot_id}/restore`,{},{version:initial.profile.version}),'Snapshot restored.')}>Restore saved snapshot</Button>}
    </div>
    <section className="bm-flow-card"><h2 className="bm-section-title">Evidence you control</h2><ResourceState {...evidence} retry={evidence.reload}/>
      {evidence.data?.items.length === 0 && <p>No observations are being used.</p>}
      {evidence.data?.items.map(item=><div className="bm-flow-row" key={item.evidence_id}><span>{item.source_type.replaceAll('_',' ')}</span>
        <Button variant="secondary" disabled={busy || item.suppressed} onClick={()=>run(async()=>{await command(`/me/persona/evidence/${item.evidence_id}/suppress`,{},{key:crypto.randomUUID()});evidence.reload()},'Evidence excluded.')}>Exclude this evidence</Button></div>)}
    </section>
    {initial.context_overrides.map(context=><div className="bm-flow-row" key={context.override_id}><span>{context.label} · {context.active ? 'Active' : 'Inactive'}</span><Button variant="secondary" disabled={busy} onClick={()=>run(()=>command(`/me/persona/contexts/${context.override_id}`,{enabled:!context.enabled},{method:'PATCH',version:initial.profile.version}),'Context updated.')}>{context.enabled ? 'Disable context' : 'Enable context'}</Button></div>)}
    {initial.adaptation_proposals.map(p=><div className="bm-flow-row" key={p.axis}><span>{p.axis}: proposed {p.proposed}, currently {p.current}</span><Button variant="secondary" disabled={busy} onClick={()=>run(()=>command(`/me/persona/adaptations/${p.axis}/accept`,{},{version:initial.profile.version}),'Adaptation reviewed.')}>Accept proposed change</Button></div>)}
    <Dialog title="Reset learned preferences" description="Clear inferences while keeping your declared preferences. The server records the reset; rewards and ownership are unchanged." open={reset} onOpenChange={setReset} trigger={<Button variant="secondary">Reset inferences</Button>}>
      <Button pending={busy} onClick={()=>run(()=>command('/me/persona/reset',{scope:'inference',confirm:true},{version:initial.profile.version,key:crypto.randomUUID()}),'Inferences reset.')}>Confirm reset</Button>
    </Dialog>
  </div>
}
