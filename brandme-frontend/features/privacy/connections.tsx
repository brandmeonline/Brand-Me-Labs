'use client'
import { useState } from 'react'
import type { components } from '@brandme/contracts'
import { useResource, accountChanged } from '@/lib/client/use-resource'
import { command, explainError } from '@/lib/client/gateway'
import { Button } from '@/components/ui/button'
import { Input, Switch } from '@/components/ui/field'
import { ResourceState } from '@/components/ui/resource-state'
import { clearGuest, migrateGuest } from '@/features/persona/onboarding'
export function Connections({ allowDev }: { allowDev:boolean }) {
  const me=useResource<components['schemas']['Me']>('/me')
  const [identity,setIdentity]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[erase,setErase]=useState(true)
  async function signIn(){setBusy(true);try{await command('/session/dev',{test_identity:identity});accountChanged();setMessage('Development session connected. This is a fictional test identity.')}catch(e){setMessage(explainError(e))}finally{setBusy(false)}}
  return <div className="bm-flow-stack"><ResourceState {...me} retry={me.reload}/>
    {me.data&&<section className="bm-flow-card"><h2 className="bm-section-title">Your account</h2><p>{me.data.member.display_name??'Member'} · {me.data.environment} environment</p>
      <p>{me.data.session.identity_provider==='dev'?'Development identity · simulated sign-in. Domain records are real development data.':'Signed in through your identity provider.'}</p>
      <p className="bm-support">Member reference: {me.data.member.id}</p>
      <Button pending={busy} onClick={async()=>{setBusy(true);try{const result=await migrateGuest();setMessage(result?'Guest choices saved to this account.':'There are no guest choices to migrate.')}catch(e){setMessage(explainError(e))}finally{setBusy(false)}}}>Bring my guest choices</Button>
      <Switch label="Clear guest data on this device when signing out" checked={erase} onCheckedChange={setErase}/>
      <Button variant="secondary" pending={busy} onClick={async()=>{setBusy(true);try{await command('/session',{},{method:'DELETE'});if(erase)clearGuest();accountChanged();setMessage('Signed out.')}catch(e){setMessage(explainError(e))}finally{setBusy(false)}}}>Sign out</Button>
      <h3>Service availability</h3><ul>{me.data.capabilities.map(c=><li key={c.name}>{c.name}: {c.state}{c.simulation_label?` — ${c.simulation_label}`:''}</li>)}</ul>
    </section>}
    {allowDev&&<form className="bm-flow-card" onSubmit={e=>{e.preventDefault();void signIn()}}><h2 className="bm-section-title">Development sign-in</h2>
      <p>Use a fictional test identity. This creates or resumes a development account; it is not a production authentication method.</p>
      <Input label="Test identity" required pattern="[a-z0-9_-]{1,40}" maxLength={40} autoComplete="off" value={identity} onChange={e=>setIdentity(e.target.value)}/>
      <Button type="submit" pending={busy}>Connect development session</Button></form>}
    {!allowDev&&!me.data&&<p>Account sign-in is not configured for this deployment. You can continue exploring as a guest.</p>}
    <p role="status">{message}</p><section className="bm-flow-card"><h2 className="bm-section-title">Retailers and agents</h2><p>Connections appear only after a provider is configured and your scopes are approved. No retailer credentials are stored in this browser.</p></section>
  </div>
}
