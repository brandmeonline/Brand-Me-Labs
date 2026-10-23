import assert from 'node:assert/strict'
import { test } from 'node:test'
import { gatewayBase, proxyGateway } from '../server/gateway-proxy.ts'
import { downloadDataExport, invalidateAccountRequests } from '../client/gateway.ts'
import { createHash } from 'node:crypto'
const env={NODE_ENV:'development',BRANDME_MODE:'development',BRANDME_GATEWAY_URL:'http://127.0.0.1:3001'}
const req=(path,method='GET',headers={},body)=>new Request(`http://localhost:3000/api/v1/${path}`,{method,headers,...(body?{body:JSON.stringify(body)}:{})})
const headers={origin:'http://localhost:3000','content-type':'application/json','x-csrf-token':'test-csrf'}
test('export download verifies exact bytes and rejects a corrupt package',async t=>{
  const id='12345678-1234-4234-8234-123456789012',body='{"categories":{}}',hash=createHash('sha256').update(body).digest('hex')
  const fetch=t.mock.method(globalThis,'fetch',async(url,options)=>{assert.equal(url,`/api/v1/me/exports/${id}/download`);assert.equal(options.cache,'no-store');assert.equal(options.credentials,'same-origin');return new Response(body)})
  assert.equal(await (await downloadDataExport(id,hash)).text(),body)
  fetch.mock.mockImplementation(async()=>new Response('{}'))
  await assert.rejects(downloadDataExport(id,hash),/verification failed/)
})
test('an account change discards an in-flight export before any file is returned',async t=>{
  const body='{"categories":{}}',hash=createHash('sha256').update(body).digest('hex'),deferred=Promise.withResolvers()
  t.mock.method(globalThis,'fetch',()=>deferred.promise)
  const result=downloadDataExport('12345678-1234-4234-8234-123456789012',hash)
  invalidateAccountRequests();deferred.resolve(new Response(body))
  await assert.rejects(result,error=>error.code==='account_changed')
})
test('unconfigured services fail without inventing data',async()=>{let calls=0;const r=await proxyGateway(req('me'),['me'],{},async()=>{calls++;return Response.json({})});assert.equal(r.status,503);assert.equal(calls,0)})
test('upstream URL rejects credentials, unapproved protocols and nonlocal insecure hosts',()=>{for(const url of ['http://example.com','https://user:password@example.com','https://example.com/arbitrary','file:///etc/passwd'])assert.throws(()=>gatewayBase({...env,BRANDME_GATEWAY_URL:url}))})
test('unsafe requests require same-origin and CSRF before touching the gateway',async()=>{for(const h of [{},{...headers,origin:'https://foreign.example'},{...headers,'sec-fetch-site':'cross-site'},{origin:headers.origin,'content-type':'application/json'}]){let calls=0;const r=await proxyGateway(req('me','PATCH',h,{}),['me'],env,async()=>{calls++;return Response.json({})});assert.equal(r.status,403);assert.equal(calls,0)}})
test('operator routes and path traversal are not forwarded',async()=>{for(const parts of [['ops','rewards'],['commerce','ops','queue'],['me','..'],['me','%2e%2e'],['me','a/b'],['http:']])assert.equal((await proxyGateway(req('me'),parts,env)).status,404)})
test('catalog composite IDs are encoded within the one published product route',async()=>{
  for(const id of ['local_atelier:linen-jacket','local_atelier%3Alinen-jacket']){
    const parts=['catalog','products',id]
    const r=await proxyGateway(req(parts.join('/')),parts,env,async(url)=>{assert.equal(new URL(url).pathname,'/api/v1/catalog/products/local_atelier%3Alinen-jacket');return Response.json({variants:[]})})
    assert.equal(r.status,200)
  }
  for(const p of [['me','other:identity'],['catalog','products','https://host'],['catalog','products','local:../private'],['catalog','products','local_atelier%253Alinen-jacket'],['catalog','products','local%3A..%2Fprivate'],['catalog','products','%invalid']])assert.equal((await proxyGateway(req('me'),p,env)).status,404)
})
test('only session cookie and explicit headers reach the fixed gateway',async()=>{let called=false;const r=await proxyGateway(req('me','PATCH',{...headers,cookie:'tracking=private; bm_session=fake; unrelated=private',authorization:'Bearer never-forward','if-match':'"12"','idempotency-key':'test-operation-123'},{}),['me'],env,async(url,init)=>{called=true;assert.equal(String(url),'http://127.0.0.1:3001/api/v1/me');assert.equal(init.headers.get('cookie'),'bm_session=fake');assert.equal(init.headers.get('authorization'),null);assert.equal(init.headers.get('if-match'),'"12"');assert.equal(init.redirect,'manual');return Response.json({version:'13'},{headers:{etag:'"13"'}})});assert(called);assert.equal(r.headers.get('cache-control'),'private, no-store');assert.equal(r.headers.get('etag'),'"13"')})
test('development identity is unavailable from production builds and strict environments',async()=>{for(const e of [{...env,NODE_ENV:'production'},{...env,BRANDME_MODE:'sandbox'},{...env,BRANDME_MODE:'production'}])assert.equal((await proxyGateway(req('session/dev','POST',headers,{}),['session','dev'],e)).status,404)})
test('session cookies remain HTTP-only, host-scoped and only come from session routes',async()=>{const run=(path,cookie)=>proxyGateway(req(path),path.split('/'),env,async()=>Response.json({},{headers:{'set-cookie':cookie}}));assert.match((await run('session','bm_session=fake; Path=/; HttpOnly; SameSite=Lax')).headers.get('set-cookie'),/HttpOnly/);assert.equal((await run('me','bm_session=fake; HttpOnly')).headers.get('set-cookie'),null);assert.equal((await run('session','bm_session=fake; Domain=other.test; HttpOnly')).headers.get('set-cookie'),null)})
test('redirects and HTML errors do not expose upstream pages',async()=>{for(const response of [Response.redirect('https://foreign.example'),new Response('<script>bad</script>',{headers:{'content-type':'text/html'}})]){const r=await proxyGateway(req('me'),['me'],env,async()=>response);assert.equal(r.status,502);assert.doesNotMatch(await r.text(),/script|foreign/)}})
test('mutation timeout is explicitly unknown and never retried',async()=>{let calls=0;const r=await proxyGateway(req('me','PATCH',headers,{}),['me'],env,async()=>{calls++;throw new Error('private endpoint details')});assert.equal(calls,1);assert.equal((await r.json()).code,'outcome_unknown')})
test('oversize bodies are rejected before upstream execution',async()=>{let calls=0;const r=await proxyGateway(req('me','PATCH',headers,{value:'a'.repeat(262145)}),['me'],env,async()=>{calls++;return Response.json({})});assert.equal(r.status,413);assert.equal(calls,0)})
