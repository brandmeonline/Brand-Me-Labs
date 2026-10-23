export interface GuestDraft { id:string; step:number; intent:string; looks:number[]; room:string; expression:number|null; color:number|null; fit_language:number|null; learning:boolean; saved:boolean }
export function validateGuest(value:unknown):GuestDraft|null{
  if(!value||typeof value!=='object')return null
  const v=value as GuestDraft
  if(typeof v.id!=='string'||!/^[-A-Za-z0-9_]{16,64}$/.test(v.id)||!Number.isInteger(v.step)||v.step<0||v.step>3||
    !['everyday','work','going_out','occasion'].includes(v.intent)||!['walnut_atelier','limestone_gallery','garden_studio','simple_view'].includes(v.room)||
    !Array.isArray(v.looks)||v.looks.length>3||new Set(v.looks).size!==v.looks.length||!v.looks.every(i=>Number.isInteger(i)&&i>=0&&i<6)||
    typeof v.learning!=='boolean'||typeof v.saved!=='boolean'||
    ![v.expression,v.color,v.fit_language].every(n=>n===null||Number.isInteger(n)&&n>=0&&n<=100))return null
  return {id:v.id,step:v.step,intent:v.intent,looks:v.looks,room:v.room,expression:v.expression,color:v.color,fit_language:v.fit_language,learning:v.learning,saved:v.saved}
}
export function guestPayload(d:GuestDraft){return {guest_namespace_id:d.id,
  persona:{declared:Object.fromEntries((['expression','color','fit_language'] as const).map(k=>[k,{value:d[k],locked:d[k]!==null}])),onboarding_intent:d.intent,learning_enabled:d.learning},saved_look:d.saved,
  sections:{closet_theme:{room_template_id:d.room==='simple_view'?'walnut_atelier':d.room}}}}
