/** Real HTTP → gateway/session → domain → Spanner. No request interception or fixture server. */
import assert from 'node:assert/strict'
import {mkdir,writeFile} from 'node:fs/promises'
import {createRequire} from 'node:module'
import path from 'node:path'
import {randomUUID} from 'node:crypto'
const require=createRequire(new URL('../../package.json',import.meta.url))
const {chromium}=require('playwright')
const AxeBuilder=require('@axe-core/playwright').default
const base=process.env.BRANDME_CONSUMER_URL||'http://127.0.0.1:3000'
const output=process.env.BRANDME_EVIDENCE_DIR
if(process.env.BRANDME_MODE!=='development'||!output||new URL(base).hostname!=='127.0.0.1')throw new Error('Local development test only')
await mkdir(output,{recursive:true})
const browser=await chromium.launch({headless:true})
const contexts=[]
const checks=[]
async function json(response){assert(response.ok(),`HTTP ${response.status()} ${new URL(response.url()).pathname}`);return response.status()===204?null:response.json()}
async function get(context,url){return json(await context.request.get(`${base}/api/v1${url}`))}
async function command(context,url,body={},method='POST',headers={}){
  const session=await get(context,'/session')
  return json(await context.request.fetch(`${base}/api/v1${url}`,{method,data:body,headers:{Origin:base,'X-CSRF-Token':session.csrf_token,...headers}}))
}
async function eventually(fn){let last;for(let i=0;i<40;i++){try{return await fn()}catch(e){last=e}await new Promise(resolve=>setTimeout(resolve,250))}throw last}
async function signIn(name){
  const context=await browser.newContext({viewport:{width:390,height:844}});contexts.push(context)
  const page=await context.newPage();await page.goto(`${base}/me/connections`)
  await page.getByRole('textbox',{name:'Test identity'}).fill(name)
  const completed=page.waitForResponse(response=>response.url().endsWith('/api/v1/session/dev')&&response.request().method()==='POST')
  await page.getByRole('button',{name:'Connect development session'}).click()
  const response=await completed
  assert(response.ok(),`Development sign-in failed: HTTP ${response.status()}`)
  await page.getByRole('heading',{name:'Your account',exact:true}).waitFor()
  const me=await get(context,'/me')
  return {context,page,id:me.member.id}
}
try{
  const suffix=randomUUID().slice(0,8)
  const alice=await signIn(`ui_alice_${suffix}`),bob=await signIn(`ui_bob_${suffix}`)
  checks.push('Two independent development sessions resolve distinct persisted members')
  assert.notEqual(alice.id,bob.id)
  await alice.page.goto(`${base}/start`)
  await alice.page.getByRole('button',{name:'Continue',exact:true}).click()
  await alice.page.getByRole('button',{name:/Quiet structure/}).click()
  await alice.page.getByRole('button',{name:'Continue',exact:true}).click()
  await alice.page.getByRole('button',{name:'Reveal my direction'}).click()
  await alice.page.getByRole('button',{name:'That feels like me'}).click()
  const guest=await alice.page.evaluate(()=>JSON.parse(localStorage.getItem('brandme:guest:v1')))
  await alice.page.getByRole('button',{name:'I’m signed in — save my choices'}).click()
  await alice.page.getByText('Your guest choices were saved to your signed-in account.',{exact:true}).waitFor()
  assert.equal(await alice.page.evaluate(()=>localStorage.getItem('brandme:guest:v1')),null)
  const first=await get(alice.context,'/me/persona')
  assert.equal(first.profile.declared_axes.expression,25)
  const payload={guest_namespace_id:guest.id,persona:{declared:Object.fromEntries(['expression','color','fit_language'].map(k=>[k,{value:guest[k],locked:guest[k]!==null}])),onboarding_intent:guest.intent,learning_enabled:guest.learning},saved_look:guest.saved,sections:{closet_theme:{room_template_id:guest.room}}}
  await command(alice.context,'/me/guest-migration',payload,'POST',{'Idempotency-Key':`guest-${guest.id}`})
  assert.equal((await get(alice.context,'/me/persona')).profile.version,first.profile.version)
  checks.push('Guest migration persists explicit choices and replays without a second profile revision')
  await alice.page.goto(`${base}/me/style`)
  await alice.page.getByRole('button',{name:'All 12 preferences'}).click()
  assert.equal(await alice.page.getByRole('slider').count(),12)
  await alice.page.getByRole('spinbutton',{name:'Expression value',exact:true}).fill('70')
  await alice.page.getByRole('button',{name:'Apply changes',exact:true}).click()
  await eventually(async()=>assert.equal((await get(alice.context,'/me/persona')).profile.declared_axes.expression,70))
  await alice.page.reload()
  assert.equal(await alice.page.getByRole('spinbutton',{name:'Expression value',exact:true}).inputValue(),'70')
  assert.equal((await get(bob.context,'/me/persona')).profile.declared_axes.expression??null,null)
  checks.push('All twelve axes render; edited preference survives reload and remains isolated from another account')
  const intake=await command(alice.context,'/wardrobe/items',{source:'manual',title:'Development linen jacket',category:'outerwear'},'POST',{'Idempotency-Key':randomUUID()})
  assert.equal(intake.items[0].claim_level,'self_reported')
  assert.match(intake.items[0].id,/^[a-f0-9-]{36}$/)
  await alice.page.goto(`${base}/today`)
  const itemLink=alice.page.getByRole('link',{name:'Development linen jacket',exact:true})
  await itemLink.waitFor()
  assert.equal(await itemLink.getAttribute('href'),`/closet/items/${intake.items[0].id}`)
  checks.push('Today renders a wardrobe item persisted by the real intake endpoint, preserving its self-reported claim')
  const relationship=await command(alice.context,'/relationships',{target_member_id:bob.id})
  await command(bob.context,`/relationships/${relationship.relationship_id}/accept`)
  await alice.page.goto(`${base}/circle/decisions/new`)
  await alice.page.getByRole('combobox',{name:'Item from my wardrobe'}).selectOption(intake.items[0].id)
  await alice.page.getByRole('checkbox').check()
  await alice.page.getByRole('button',{name:'Start five-minute decision'}).click()
  await alice.page.waitForURL(/\/circle\/decisions\/[a-f0-9-]{36}$/)
  const decisionId=new URL(alice.page.url()).pathname.split('/').pop()
  const decision=await get(alice.context,`/decisions/${decisionId}`)
  assert.equal(Date.parse(decision.closes_at)-Date.parse(decision.opened_at),300000)
  await bob.page.goto(`${base}/circle/decisions/${decisionId}`)
  await bob.page.getByRole('button',{name:'Pass',exact:true}).click()
  await bob.page.getByText('Your response: pass',{exact:true}).waitFor()
  await alice.page.getByRole('button',{name:'Close early',exact:true}).click()
  await eventually(async()=>{const d=await get(alice.context,`/decisions/${decisionId}`);assert.equal(d.state,'closed');assert.equal(d.result.pass,1)})
  checks.push('Five-minute server deadline, independent recipient response and creator close persist through the gateway')
  await eventually(async()=>assert.equal((await get(alice.context,'/rewards')).account.available,125))
  await eventually(async()=>assert.equal((await get(bob.context,'/rewards')).account.available,10))
  await command(alice.context,'/me/guest-migration',payload,'POST',{'Idempotency-Key':`guest-${guest.id}`})
  assert.equal((await get(alice.context,'/rewards')).account.available,125)
  await alice.page.goto(`${base}/rewards`)
  await alice.page.getByRole('heading',{name:'Your badges',exact:true}).waitFor()
  checks.push('Actual outbox/inbox settlement awards setup and first-item points once; Pass earns the same response rule')
  const unreadBefore=(await get(alice.context,'/notifications?limit=24')).items.filter(n=>!n.read_at).length
  assert(unreadBefore>0,'Relationship and decision changes should produce in-app updates')
  await alice.page.goto(`${base}/inbox`)
  await alice.page.getByRole('button',{name:'Mark as read',exact:true}).first().click()
  await eventually(async()=>assert.equal((await get(alice.context,'/notifications?limit=24')).items.filter(n=>!n.read_at).length,unreadBefore-1))
  checks.push('Inbox displays real domain notifications and persists an explicit mark-as-read command')
  for(const route of ['/today','/me/style','/circle','/rewards','/me/connections','/inbox']){
    await alice.page.goto(base+route,{waitUntil:'networkidle'})
    const audit=await new AxeBuilder({page:alice.page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()
    assert.deepEqual(audit.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)})),[],route)
    assert(await alice.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Overflow: ${route}`)
    await alice.page.screenshot({path:path.join(output,`live-${route.slice(1).replaceAll('/','-')}.png`),fullPage:true})
  }
  await command(alice.context,'/blocks',{target_member_id:bob.id})
  assert.equal((await bob.context.request.get(`${base}/api/v1/decisions/${decisionId}`)).status(),404)
  checks.push('Block removes the other account’s access to the decision')
  await alice.page.goto(`${base}/me/connections`)
  await alice.page.getByRole('button',{name:'Sign out',exact:true}).click()
  await eventually(async()=>assert.equal((await alice.context.request.get(`${base}/api/v1/me`)).status(),401))
  checks.push('Sign-out revokes the real session')
  await writeFile(path.join(output,'live-results.json'),JSON.stringify({source:'real development HTTP and Spanner emulator',checks},null,2))
  checks.forEach(check=>console.log(`PASS ${check}`))
}catch(error){
  await writeFile(path.join(output,'live-results.json'),JSON.stringify({source:'real development HTTP and Spanner emulator',checks,failed:true,error:error.message},null,2))
  for(const [index,context] of contexts.entries())for(const [pageIndex,page] of context.pages().entries())await page.screenshot({path:path.join(output,`failure-${index}-${pageIndex}.png`),fullPage:true}).catch(()=>{})
  throw error
}finally{await Promise.all(contexts.map(context=>context.close()));await browser.close()}
