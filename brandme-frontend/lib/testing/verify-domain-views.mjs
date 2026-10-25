/** UI contract tests using explicit HTTP test doubles. Not live-service acceptance evidence. */
import assert from 'node:assert/strict'
import {createHash} from 'node:crypto'
import {createRequire} from 'node:module'
import {mkdir,writeFile} from 'node:fs/promises'
import path from 'node:path'
const require=createRequire(new URL('../../package.json',import.meta.url))
const {chromium}=require('playwright')
const AxeBuilder=require('@axe-core/playwright').default
const base=process.env.BRANDME_CONSUMER_URL||'http://127.0.0.1:3000'
const output=process.env.BRANDME_EVIDENCE_DIR
if(!output||!['localhost','127.0.0.1'].includes(new URL(base).hostname))throw new Error('Local UI test runner required')
await mkdir(output,{recursive:true})
const id='12345678-1234-4234-8234-123456789012'
const category={key:'rights.operations',title:'Your ownership operations',supplied_by:'system',visible_to:['member'],retention:'Until you delete them',on_edit:'Review an operation',on_delete:'erase',retention_basis:null}
const bytes=JSON.stringify({schema:'brandme.selected-rights-export/v1',categories:{'rights.operations':[]},coverage:{full_account:false,selected_categories_only:true}})
const hash=createHash('sha256').update(bytes).digest('hex')
const job={job_id:id,state:'ready',categories:[category.key],coverage:{domains:['rights'],full_account:false,selected_categories_only:true},environment:'development',network:'undeployed',requested_at:'2026-10-23T00:00:00Z',expires_at:'2027-01-01T00:00:00Z',completed_at:'2026-10-23T00:00:01Z',package_sha256:hash,package_bytes:Buffer.byteLength(bytes),failure_code:null,download_available:true}
const providerText=text=>({type:'untrusted_text',origin:'test-provider',text})
const item={provider_id:'test_provider',merchant_id:'test-merchant',source_product_id:'linen-jacket',source_variant_ref:'jacket-m',variant_id:null,title:providerText('<img src=x onerror=alert(1)> Linen jacket'),description:providerText('Explicit UI test double'),category:'outerwear',size_label:'M',availability:'in_stock',observed_price:{amount_minor:'9612',currency:'USD'},price_freshness:'fresh',checked_at:'2026-10-23T00:00:00Z',simulation:true,disclosure:'Simulated provider for UI testing only.'}
const browser=await chromium.launch({headless:true})
try{
  for(const width of [390,1440]){
    const context=await browser.newContext({viewport:{width,height:900},timezoneId:'UTC'})
    try{
      let corrupt=false,marked=false,holdDownload=false,releaseDownload,reserveAttempts=0
      const requests=[]
      await context.route('**/api/v1/**',async route=>{
        const req=route.request(),url=new URL(req.url()),p=decodeURIComponent(url.pathname.replace('/api/v1',''))
        const reply=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
        if(req.method()!=='GET')requests.push({path:p,key:req.headers()['idempotency-key'],body:req.postDataJSON()})
        if(p==='/session')return reply({csrf_token:'test-double-csrf'})
        if(p==='/rewards')return reply({account:{available:reserveAttempts>1?50:100,reserved:reserveAttempts>1?50:0,lifetime_earned:100,recovery_due:0},points_are:'Points are not cash.',entries:{items:[]},badges:[],next_milestone:null,recovery_policy:'Explicit UI test double.'})
        if(p==='/benefits')return reply({items:[{benefit_id:id,title:'Test tailoring benefit',description:'UI test double only.',cost_points:50,available:reserveAttempts<2}]})
        if(p==='/rewards/reservations')return reply({items:reserveAttempts>1?[{reservation_id:id,state:'reserved',release_reason:null}]:[]})
        if(p===`/benefits/${id}/reservations`){reserveAttempts++;return reserveAttempts===1?reply({code:'outcome_unknown',title:'The result is not confirmed. Refresh the record before trying again.'},503):reply({reservation_id:id,state:'reserved'})}
        if(p==='/catalog/search')return reply({items:[item],unavailable_providers:[{provider_id:'offline_provider',reason_code:'unavailable',handoff:'none'}],note:'Authorized catalog observations.'})
        if(p==='/catalog/products/test_provider:linen-jacket')return reply({provider_id:item.provider_id,source_product_id:item.source_product_id,simulation:true,disclosure:item.disclosure,variants:[item]})
        if(p==='/notifications/read'){marked=true;return reply({updated:1})}
        if(p==='/notifications')return reply({items:[{notification_id:id,type:'decision_closed',subject_ref:`decision:${id}`,created_at:'2026-10-23T00:00:00Z',read_at:marked?'2026-10-23T00:01:00Z':null},{notification_id:'untrusted-reference',type:'update',subject_ref:'javascript:alert(1)',created_at:'2026-10-23T00:00:00Z',read_at:null}],next_cursor:null})
        if(p==='/me/data')return reply({environment:'development',categories:[category],coverage:{domains:['rights'],full_account:false},capabilities:{export:'selected_categories',deletion:'unavailable'}})
        if(p==='/me/exports/capability')return reply({status:'available',environment:'development',network:'undeployed',categories:[category.key],full_account:false,selected_categories_only:true})
        if(p==='/me/exports')return reply(job)
        if(p===`/me/exports/${id}`)return reply(job)
        if(p===`/me/exports/${id}/download`){if(holdDownload)await new Promise(resolve=>{releaseDownload=resolve});return route.fulfill({status:200,contentType:'application/json',body:corrupt?'{}':bytes})}
        if(p===`/me/deletion/${id}`)return reply({job_id:id,environment:'development',scope:'category',state:'completed_with_exceptions',categories:[category.key],requested_at:'2026-10-23T00:00:00Z',completed_at:'2026-10-23T00:01:00Z',outcomes:{[category.key]:{status:'retained',rows_affected:'0',derived_purged:null}}})
        return reply({code:'unavailable',title:'UI test does not provide this service'},503)
      })
      const page=await context.newPage(),errors=[]
      page.on('pageerror',error=>errors.push(error.message))
      async function audit(name,expectedTitle='Brand.Me — Be More U'){
        // A rendered client view can precede Next's streamed metadata during navigation.
        // Require the inherited title before auditing; a missing/wrong title must still fail.
        await page.waitForFunction(title=>document.title===title,expectedTitle,{timeout:10000})
        for(const theme of ['light','dark']){
          await page.emulateMedia({colorScheme:theme})
          await page.waitForFunction(theme=>document.documentElement.dataset.bmTheme===theme,theme)
          const a=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()
          assert.deepEqual(a.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)})),[],`${name}/${width}/${theme}`)
          assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${name}: horizontal overflow`)
          // Functional focus checks run before this capture. Normalize scroll/focus for stable page baselines.
          await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur();window.scrollTo(0,0)})
          await page.evaluate(()=>document.fonts.ready)
          await page.screenshot({path:path.join(output,`${name}-${width}-${theme}.png`),fullPage:true,animations:'disabled'})
        }
      }
      await page.goto(`${base}/discover`)
      await page.getByRole('textbox',{name:'What are you looking for?'}).fill('linen')
      await page.getByRole('button',{name:'Search authorized catalogs'}).click()
      const product=page.getByRole('link',{name:item.title.text,exact:true})
      await product.waitFor()
      assert.equal(await page.locator('img[src="x"]').count(),0,'Provider text must not become HTML')
      await page.getByText('USD 96.12',{exact:true}).waitFor()
      await audit('catalog')
      await product.click()
      await page.getByText('Observed price, not a checkout quote.',{exact:true}).waitFor()
      assert.equal(await page.getByRole('button',{name:/buy|approve|purchase/i}).count(),0)
      await audit('product')
      await page.goto(`${base}/inbox`)
      await page.getByRole('button',{name:'Mark as read',exact:true}).first().click()
      await page.getByText('Marked as read.',{exact:true}).waitFor()
      assert.equal(await page.getByRole('link',{name:'Open update',exact:true}).count(),1,'Unknown subject references must not produce links')
      await audit('inbox')
      await page.goto(`${base}/rewards`)
      await page.getByRole('button',{name:'Review benefit',exact:true}).click()
      await page.getByRole('button',{name:'Confirm reservation',exact:true}).click()
      await page.getByRole('dialog').getByText('The result is not confirmed. Refresh the record before trying again.',{exact:true}).waitFor()
      await page.getByRole('button',{name:'Close Reserve this benefit',exact:true}).click()
      await page.getByRole('dialog').waitFor({state:'hidden'})
      await page.getByRole('button',{name:'Review benefit',exact:true}).click()
      await page.getByRole('button',{name:'Confirm reservation',exact:true}).click()
      await page.getByText('Benefit reserved. Fulfillment is shown separately.',{exact:true}).waitFor()
      const attempts=requests.filter(r=>r.path===`/benefits/${id}/reservations`)
      assert.equal(attempts.length,2);assert.equal(attempts[0].key,attempts[1].key,'An unconfirmed reservation keeps its idempotency key across dialog reopen')
      await page.getByText('reserved',{exact:true}).waitFor()
      await page.waitForFunction(()=>document.activeElement?.textContent?.trim()==='Reservation status')
      await audit('rewards')
      await page.goto(`${base}/me/data`)
      await page.getByRole('checkbox',{name:'Include Your ownership operations'}).check()
      assert.equal(await page.getByRole('button',{name:/delete|erase|request deletion/i}).count(),0)
      await audit('my-data')
      await page.getByRole('button',{name:'Request export of 1 selected categories'}).click()
      await page.waitForURL(`**/me/data/exports/${id}`)
      assert.deepEqual(requests.find(r=>r.path==='/me/exports').body,{categories:[category.key]})
      assert.match(requests.find(r=>r.path==='/me/exports').key,/^[a-f0-9-]{36}$/)
      await page.getByRole('button',{name:'Download verified JSON export'}).waitFor()
      await audit('export')
      const downloaded=page.waitForEvent('download')
      await page.getByRole('button',{name:'Download verified JSON export'}).click()
      assert.equal((await downloaded).suggestedFilename(),`brandme-selected-data-${id}.json`)
      corrupt=true
      await page.getByRole('button',{name:'Download verified JSON export'}).click()
      await page.getByText('The export could not be verified or downloaded. Refresh its status before trying again.',{exact:true}).waitFor()
      corrupt=false;holdDownload=true
      const requested=page.waitForRequest(req=>req.url().endsWith('/download'))
      await page.getByRole('button',{name:'Download verified JSON export'}).click();await requested
      for(let attempt=0;!releaseDownload&&attempt<100;attempt++)await new Promise(resolve=>setTimeout(resolve,50))
      assert.equal(typeof releaseDownload,'function','The download test double must receive the request')
      await page.evaluate(()=>window.dispatchEvent(new Event('brandme:account-change')))
      releaseDownload()
      await page.getByText('Your account changed. Request the download again.',{exact:true}).waitFor()
      await page.goto(`${base}/me/data/deletion/${id}`)
      await page.getByText('rights.operations: retained · 0 records affected',{exact:true}).waitFor()
      await audit('deletion')
      assert.deepEqual(errors,[])
      console.log(`PASS UI test doubles at ${width}px: catalog text, inbox references, reservation retry/focus, scoped exports, verified download, account switch, retained deletion outcomes and axe`)
    }catch(error){
      for(const [index,page]of context.pages().entries())await page.screenshot({path:path.join(output,`failure-fixture-${width}-${index}.png`),fullPage:true}).catch(()=>{})
      await writeFile(path.join(output,`failure-fixture-${width}.json`),JSON.stringify({error:error.message,urls:context.pages().map(page=>page.url()),titles:await Promise.all(context.pages().map(page=>page.title().catch(()=>null)))},null,2))
      throw error
    }finally{await context.close()}
  }
}finally{await browser.close()}
