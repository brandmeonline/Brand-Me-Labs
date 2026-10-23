'use client'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { Input, Select, Switch } from '@/components/ui/field'
import { Slider } from '@/components/ui/slider'
import { Button } from '@/components/ui/button'
import { command, explainError } from '@/lib/client/gateway'
import { useExperiencePreferences } from '@/lib/client/experience-preferences'

const KEY = 'brandme:guest:v1'
const LOOKS = [
  {name:'Quiet structure',color:'#918b75',shape:'tailored',expression:25,colorAxis:20,fit:25},
  {name:'Color in motion',color:'#9c514b',shape:'sport',expression:80,colorAxis:85,fit:65},
  {name:'Soft minimalism',color:'#b6ac9b',shape:'fluid',expression:20,colorAxis:15,fit:80},
  {name:'After hours',color:'#62527f',shape:'fluid',expression:75,colorAxis:50,fit:50},
  {name:'City utility',color:'#536951',shape:'sport',expression:35,colorAxis:35,fit:70},
  {name:'Artful detail',color:'#af7f3e',shape:'tailored',expression:85,colorAxis:65,fit:40},
] as const
export interface GuestDraft { id:string; step:number; intent:string; looks:number[]; room:string; expression:number|null; color:number|null; fit_language:number|null; learning:boolean; saved:boolean }
export function readGuest(): GuestDraft|null {
  try { const v=JSON.parse(localStorage.getItem(KEY)||'null'); return v && /^[A-Za-z0-9_-]{16,64}$/.test(v.id) && Number.isInteger(v.step) && v.step>=0 && v.step<=3 && ['walnut_atelier','limestone_gallery','garden_studio','simple_view'].includes(v.room) && ['expression','color','fit_language'].every(k=>v[k]===null || Number.isInteger(v[k])&&v[k]>=0&&v[k]<=100) ? v : null } catch {return null}
}
export async function migrateGuest() {
  const d=readGuest(); if(!d) return null
  const result=await command('/me/guest-migration',{guest_namespace_id:d.id,persona:{declared:Object.fromEntries(['expression','color','fit_language'].map(k=>[k,{value:d[k as 'expression'],locked:d[k as 'expression']!==null}])),onboarding_intent:d.intent,learning_enabled:d.learning},saved_look:d.saved,
    sections:{closet_theme:{room_template_id:d.room==='simple_view'?'walnut_atelier':d.room}}},{key:`guest-${d.id}`})
  // Remove only after the server confirms migration. The stable namespace/key makes a repeated sign-in safe.
  localStorage.removeItem(KEY);return result
}
export function clearGuest() { localStorage.removeItem(KEY) }
function Study({ look }: {look:typeof LOOKS[number]}) { return <svg viewBox="0 0 240 140" role="img" aria-label={`${look.name}, original fictional outfit illustration`}>
  <path d={look.shape==='fluid'?'M65 15 90 15 100 43 117 115 40 115 56 43Z':'M58 15 94 15 119 40 106 54 98 44 98 100 53 100 53 44 45 54 30 40Z'} fill={look.color} stroke="currentColor" strokeWidth="1.5"/>
  {look.shape==='tailored'&&<path d="M65 15 76 44 88 15M76 44V100" fill="none" stroke="currentColor"/>}
  <path d="M138 20 190 20 184 120 163 120 163 65 157 120 136 120Z" fill="#414a42"/>
  <path d="M54 125h31l10 9H45Z M132 128h26l8 7h-36Z" fill="#6b5140"/>
</svg> }
export function Onboarding() {
  const [d,setD]=useState<GuestDraft|null>(null), [storage,setStorage]=useState(true),[busy,setBusy]=useState(false),[message,setMessage]=useState('')
  const {update}=useExperiencePreferences()
  useEffect(()=>{setD(readGuest()??{id:crypto.randomUUID(),step:0,intent:'everyday',looks:[],room:'walnut_atelier',expression:null,color:null,fit_language:null,learning:false,saved:false})},[])
  function change(p:Partial<GuestDraft>){if(!d)return;const next={...d,...p};setD(next);try{localStorage.setItem(KEY,JSON.stringify(next))}catch{setStorage(false)}}
  if(!d)return <p role="status">Preparing your first look…</p>
  const draft=d
  return <div className="bm-flow-stack"><p className="bm-progress">Step {d.step+1} of 4 · {storage?'Saved on this device':'Device storage unavailable; keep this tab open'}</p>
    <p className="bm-support">No wallet, camera or contacts needed. Nothing is shared.</p>
    {d.step===0&&<section className="bm-flow-card"><h2 className="bm-section-title">What are you dressing for?</h2><Select label="Your intention" value={d.intent} onChange={e=>change({intent:e.target.value})}>
      <option value="everyday">Everyday</option><option value="work">Work</option><option value="going_out">Going out</option><option value="occasion">An occasion</option></Select><Button onClick={()=>change({step:1})}>Continue</Button></section>}
    {d.step===1&&<section><h2 className="bm-section-title">What catches your eye?</h2><p>Choose up to three. These original illustrations show fictional outfit directions, not products or fit predictions.</p>
      <div className="bm-choice-grid">{LOOKS.map((look,i)=><button key={look.name} className="bm-choice" aria-pressed={d.looks.includes(i)} onClick={()=>{
        const looks=d.looks.includes(i)?d.looks.filter(x=>x!==i):d.looks.length<3?[...d.looks,i]:d.looks
        const mean=(k:'expression'|'colorAxis'|'fit')=>looks.length?Math.round(looks.reduce((n,x)=>n+LOOKS[x][k],0)/looks.length):null
        change({looks,expression:mean('expression'),color:mean('colorAxis'),fit_language:mean('fit')})
      }}><Study look={look}/><strong>{look.name}</strong><span>{d.looks.includes(i)?'Selected':'Choose this direction'}</span></button>)}</div>
      <div className="bm-actions"><Button onClick={()=>change({step:2})}>Continue</Button><Button variant="secondary" onClick={()=>change({step:2,looks:[],expression:null,color:null,fit_language:null})}>None of these</Button></div></section>}
    {d.step===2&&<section><h2 className="bm-section-title">Choose your room</h2><p>You can change this anytime. Room rendering is supplied by My Closet.</p><div className="bm-choice-grid">{[
      ['walnut_atelier','Walnut Atelier','Warm wood and soft light'],['limestone_gallery','Limestone Gallery','Pale stone and open space'],['garden_studio','Garden Studio','Green accents and natural light'],['simple_view','Simple View','An accessible list, without 3D']
    ].map(([key,name,desc])=><button className="bm-choice" key={key} aria-pressed={d.room===key} onClick={()=>{change({room:key});update({simpleView:key==='simple_view'})}}><strong>{name}</strong><span>{desc}</span></button>)}</div><Button onClick={()=>change({step:3})}>Reveal my direction</Button></section>}
    {d.step===3&&<section className="bm-flow-stack"><h2 className="bm-section-title">A starting point. Yours to shape.</h2>
      <div className="bm-flow-card"><Study look={LOOKS[d.looks[0]??0]}/><p>Original fictional 2D outfit study. {d.looks.length?'Based on the directions you selected.':'A neutral illustration; no preferences have been inferred.'}</p>
        <ul><li>Your intention: {d.intent.replaceAll('_',' ')}.</li><li>{d.looks.length?`You selected ${d.looks.length} visual directions.`:'Your unknown preferences stay unknown.'}</li><li>Your closet choice remains reversible.</li></ul></div>
      <Slider label="Expression" leftLabel="Understated" rightLabel="Expressive" value={d.expression} onValueChange={expression=>change({expression})}/>
      <Slider label="Color" leftLabel="Neutral" rightLabel="Colorful" value={d.color} onValueChange={color=>change({color})}/>
      <Slider label="Silhouette" leftLabel="Tailored" rightLabel="Relaxed" value={d.fit_language} onValueChange={fit_language=>change({fit_language})}/>
      <Switch label="Learn from my activity" description="Optional. Your explicit choices remain in control." checked={d.learning} onCheckedChange={learning=>change({learning})}/>
      <div className="bm-actions"><Button onClick={()=>{change({saved:true});setMessage('Saved on this device. Sign in when you want to keep it across devices.')}}>That feels like me</Button>
        <Link className="bm-button bm-button-secondary" href="/me/connections">Save to my account</Link><Link href="/add">Add something I own</Link></div>
      <Button variant="secondary" pending={busy} onClick={async()=>{setBusy(true);try{await migrateGuest();setMessage('Your guest choices were saved to your signed-in account.')}catch(e){setMessage(explainError(e))}finally{setBusy(false)}}}>I’m signed in — save my choices</Button>
    </section>}
    <p role="status">{message}</p><div className="bm-actions">{draft.step>0&&<Button variant="secondary" onClick={()=>change({step:draft.step-1})}>Back</Button>}{draft.step<3&&<Button variant="secondary" onClick={()=>change({step:draft.step+1})}>Skip for now</Button>}<Link href="/today">Explore first</Link></div>
  </div>
}
