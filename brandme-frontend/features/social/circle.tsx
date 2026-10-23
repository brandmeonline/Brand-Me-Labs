'use client'
import Link from 'next/link'
import type {components} from '@brandme/contracts'
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useResource } from '@/lib/client/use-resource'
import { command, explainError } from '@/lib/client/gateway'
import { Button } from '@/components/ui/button'
import { Input, Select } from '@/components/ui/field'
import { ResourceState } from '@/components/ui/resource-state'

type Relationship={member_id:string;relationship_id:string;state:string}
type Decision={decision_id:string;creator_id:string;prompt:string;state:string;subject_id:string;subject_type:string;server_time:string;closes_at:string|null;remaining_seconds:number;response_count:number;responses_hidden_until_you_answer:boolean;my_response:{choice:string}|null;responses:{respondent_id:string;choice:string;note:string|null}[];audience?:string[];result?:{yes:number;pass:number;alternative:number;label:string;zero_replies:boolean}}
export function Circle(){
  const [role,setRole]=useState('invited'),[target,setTarget]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('')
  const decisions=useResource<{items:Decision[]}>(`/decisions?role=${role}`)
  const friends=useResource<{items:Relationship[]}>('/relationships')
  async function act(path:string,body:unknown={},method:'POST'|'DELETE'='POST'){setBusy(true);try{await command(path,body,{method});friends.reload();decisions.reload();setMessage('Your circle has been updated.')}catch(e){setMessage(explainError(e))}finally{setBusy(false)}}
  return <div className="bm-flow-stack"><Link href="/circle/decisions/new" className="bm-button">Ask my circle</Link>
    <Select label="Decisions to show" value={role} onChange={e=>setRole(e.target.value)}><option value="invited">Waiting for my opinion</option><option value="mine">My requests</option></Select>
    <ResourceState {...decisions} retry={decisions.reload}/>{decisions.data?.items.length===0&&<p>No decisions here yet. An honest opinion can be a Yes or a Pass.</p>}
    {decisions.data?.items.map(d=><article key={d.decision_id} className="bm-flow-card"><h2><Link href={`/circle/decisions/${d.decision_id}`}>{d.prompt}</Link></h2><p>{d.state} · {d.response_count} responses</p></article>)}
    <section className="bm-flow-card"><h2 className="bm-section-title">People you choose</h2><ResourceState {...friends} retry={friends.reload}/>
      {friends.data?.items.map(f=><div className="bm-flow-row" key={f.relationship_id}><span>Member {f.member_id.slice(0,8)} · {f.state}</span>
        <div className="bm-actions">{f.state==='requested_in'&&<Button disabled={busy} onClick={()=>act(`/relationships/${f.relationship_id}/accept`)}>Accept request</Button>}
          <Button variant="secondary" disabled={busy} onClick={()=>act('/blocks',{target_member_id:f.member_id})}>Block member</Button>
          <Button variant="secondary" disabled={busy} onClick={()=>act(`/relationships/${f.member_id}`,{},'DELETE')}>Remove connection</Button></div></div>)}
      <form onSubmit={e=>{e.preventDefault();void act('/relationships',{target_member_id:target})}}><Input label="Member reference" description="Use a member reference they shared with you. Contacts are not imported." value={target} onChange={e=>setTarget(e.target.value)} required/>
        <Button type="submit" pending={busy}>Request connection</Button></form>
    </section><p role="status">{message}</p></div>
}
export function DecisionComposer(){
  const friends=useResource<{items:Relationship[]}>('/relationships'),wardrobe=useResource<{items:components['schemas']['WardrobeItem'][]}>('/wardrobe/items')
  const [selected,setSelected]=useState<string[]>([]),[item,setItem]=useState(''),[prompt,setPrompt]=useState('Does this work for me?'),[busy,setBusy]=useState(false),[message,setMessage]=useState('')
  const key=useRef<string|null>(null),router=useRouter()
  const eligible=friends.data?.items.filter(f=>f.state==='accepted')??[]
  return <form className="bm-flow-stack" onSubmit={async e=>{e.preventDefault();setBusy(true);try{
    key.current??=crypto.randomUUID();const d=await command<Decision>('/decisions',{subject_type:'wardrobe_item',subject_id:item,prompt,recipient_ids:selected,duration_seconds:300,discussion_mode:'blind_until_response'},{key:key.current});router.push(`/circle/decisions/${d.decision_id}`)
  }catch(err){setMessage(explainError(err))}finally{setBusy(false)}}}>
    <p>The five-minute window starts when the server accepts your request. Only selected friends can respond. No external notifications are sent by this page.</p>
    <ResourceState {...wardrobe} retry={wardrobe.reload}/><Select required label="Item from my wardrobe" value={item} onChange={e=>{setItem(e.target.value);key.current=null}}><option value="">Choose an item</option>{wardrobe.data?.items.map(i=><option key={i.id} value={i.id}>{i.title} · {i.collection}</option>)}</Select>
    <Input label="Your question" value={prompt} maxLength={240} required onChange={e=>{setPrompt(e.target.value);key.current=null}}/>
    <fieldset><legend>Ask up to 12 friends</legend><ResourceState {...friends} retry={friends.reload}/>{eligible.length===0&&<p>No eligible friends yet. Connect with someone in your Circle first.</p>}
      {eligible.map(f=><label className="bm-checkbox-label" key={f.member_id}><input type="checkbox" checked={selected.includes(f.member_id)} disabled={busy||!selected.includes(f.member_id)&&selected.length>=12} onChange={e=>{setSelected(s=>e.target.checked?[...s,f.member_id]:s.filter(id=>id!==f.member_id));key.current=null}}/>Member {f.member_id.slice(0,8)}</label>)}</fieldset>
    <p role="status">{message}</p><Button type="submit" pending={busy} disabled={!item||!selected.length}>Start five-minute decision</Button>
  </form>
}
export function DecisionView({id}:{id:string}){
  const r=useResource<Decision>(`/decisions/${encodeURIComponent(id)}`)
  const [seconds,setSeconds]=useState<number|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[note,setNote]=useState(''),[alternative,setAlternative]=useState('')
  useEffect(()=>{if(!r.data)return;const d=r.data;const received=performance.now();const remaining=d.state==='open'&&d.closes_at?Math.max(0,Date.parse(d.closes_at)-Date.parse(d.server_time)):0
    const tick=()=>setSeconds(Math.max(0,Math.ceil((remaining-(performance.now()-received))/1000)));tick();const timer=setInterval(tick,1000)
    const refresh=()=>{if(document.visibilityState==='visible')r.reload()};document.addEventListener('visibilitychange',refresh)
    return()=>{clearInterval(timer);document.removeEventListener('visibilitychange',refresh)}
  },[r.data,r.reload])
  // Recheck authoritative access and deadline; blocked/revoked records disappear.
  useEffect(()=>{const timer=setInterval(()=>{if(document.visibilityState==='visible')r.reload()},30000);return()=>clearInterval(timer)},[r.reload])
  async function action(path:string,body:unknown={}){setBusy(true);try{await command(path,body);setMessage('Response recorded by the server.');r.reload()}catch(e){setMessage(explainError(e));r.reload()}finally{setBusy(false)}}
  const d=r.data,closed=!d||d.state!=='open'||seconds===0
  return <div className="bm-flow-stack"><ResourceState {...r} retry={r.reload}/>{d&&<>
    <h2 className="bm-section-title">{d.prompt}</h2><p className="bm-timer" role="timer" aria-live="off" aria-label="Time remaining">{seconds===null?'Checking time…':`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`}</p>
    <p>{closed?'This decision is closed. The server decides which responses arrived in time.':'The countdown uses the server deadline. Yes and Pass have equal reward eligibility.'}</p>
    <p><Link href={d.subject_type==='wardrobe_item'?`/closet/items/${d.subject_id}`:d.subject_type==='outfit_version'?`/style/outfits/${d.subject_id}`:`/products/${d.subject_id}`}>View the item or outfit</Link></p>
    {d.audience?<div className="bm-actions"><p>Your request has {d.response_count} responses.</p><Button variant="secondary" disabled={closed||busy} onClick={()=>action(`/decisions/${id}/close`)}>Close early</Button></div>:<>
      <Input label="Optional note" value={note} maxLength={500} onChange={e=>setNote(e.target.value)}/>
      <div className="bm-actions">{(['yes','pass'] as const).map(choice=><Button key={choice} variant="secondary" disabled={closed||busy} onClick={()=>action(`/decisions/${id}/responses`,{choice,note:note||undefined})}>{choice==='yes'?'Yes':'Pass'}</Button>)}</div>
      <Input label="Alternative product reference" value={alternative} onChange={e=>setAlternative(e.target.value)}/><Button variant="secondary" disabled={closed||busy||!alternative} onClick={()=>action(`/decisions/${id}/responses`,{choice:'alternative',alternative_ref:alternative,note:note||undefined})}>Suggest an alternative</Button>
      {d.my_response&&<p>Your response: {d.my_response.choice}</p>}</>}
    {d.responses_hidden_until_you_answer?<p>Other responses stay hidden until you answer.</p>:<ul>{d.responses.map(v=><li key={v.respondent_id}>{v.choice}{v.note?` — ${v.note}`:''}</li>)}</ul>}
    {d.result&&<p>{d.result.zero_replies?'No replies this time. You can save the item or start a new request.':`${d.result.label}: ${d.result.yes} Yes, ${d.result.pass} Pass, ${d.result.alternative} alternatives.`}</p>}
  </>}<p role="status">{message}</p></div>
}
