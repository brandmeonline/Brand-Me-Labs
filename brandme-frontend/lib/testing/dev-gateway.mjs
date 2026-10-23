/** Local development composition only. Imports pinned, unchanged lane sources. */
import {createRequire} from 'node:module'
import {createHmac,randomUUID} from 'node:crypto'
import {pathToFileURL} from 'node:url'
import path from 'node:path'

const reference=process.env.BRANDME_DOMAIN_REFERENCE
const secret=process.env.BRANDME_DEV_ASSERTION_KEY
if(process.env.BRANDME_MODE!=='development'||process.env.NODE_ENV==='production'||
  !/^127\.0\.0\.1:9010$/.test(process.env.SPANNER_EMULATOR_HOST||'')||!reference||!secret||secret.length<64)
  throw new Error('This composition requires local development, the loopback emulator and a runtime assertion key.')
const root=path.join(reference,'brandme-gateway')
const require=createRequire(path.join(root,'package.json'))
const express=require('express')
const source=relative=>import(pathToFileURL(path.join(root,'src',relative)).href)
const [{loadConfig},{IdentityStore},{apiV1},{requestContext,problemHandler},{principalMiddleware},
  {personaRouter},{wardrobeRouter},{outfitsRouter},{socialRouter},{decisionsRouter},{rewardsRouter}]=await Promise.all([
  source('config/index.ts'),source('middleware/identity/store.ts'),source('routes/v1/index.ts'),
  source('middleware/problem.ts'),source('middleware/session.ts'),source('routes/v1/persona.ts'),
  source('routes/v1/wardrobe.ts'),source('routes/v1/outfits.ts'),source('routes/v1/social.ts'),source('routes/v1/decisions.ts'),source('routes/v1/rewards.ts')])
const cfg=loadConfig(process.env)
const store=new IdentityStore({projectId:cfg.spannerProjectId,instanceId:cfg.spannerInstanceId,databaseId:cfg.spannerDatabaseId,mode:cfg.mode})
const client={async request(spec){
  const url=new URL(`http://127.0.0.1:8011${spec.path}`)
  for(const [key,value]of Object.entries(spec.query||{}))url.searchParams.set(key,String(value))
  const claims=Buffer.from(JSON.stringify({member_id:spec.principal?.memberId??null,scopes:spec.principal?.scopes??[],
    method:spec.method,path:url.pathname,issued_at:Math.floor(Date.now()/1000),nonce:randomUUID()})).toString('base64url')
  const signature=createHmac('sha256',secret).update(claims).digest('hex')
  const headers={'Content-Type':'application/json','X-Brandme-Dev-Assertion':`${claims}.${signature}`,'X-Request-Id':spec.requestId}
  if(spec.ifMatch)headers['If-Match']=spec.ifMatch
  if(spec.idempotencyKey)headers['Idempotency-Key']=spec.idempotencyKey
  const response=await fetch(url,{method:spec.method,headers,body:spec.body===undefined?undefined:JSON.stringify(spec.body),signal:AbortSignal.timeout(12000)})
  return {status:response.status,body:response.status===204?null:await response.json(),headers:{etag:response.headers.get('etag')}}
}}
const app=express()
app.disable('x-powered-by')
app.get('/health',async(_req,res)=>{try{await store.ping();res.json({status:'ok',database:'spanner',environment:'development'})}catch{res.status(503).json({status:'unreachable'})}})
app.use('/api/v1',requestContext(cfg.mode),express.json({limit:'256kb'}),principalMiddleware({cfg,store}),(_req,res,next)=>{
  const principal=res.locals.principal
  // Explicit simulated first-party session policy for this local harness; never used by production.
  if(principal?.via==='session'&&principal.identityProvider==='dev'&&principal.environment==='development')
    principal.scopes=['profile:read','profile:write','wardrobe:read','wardrobe:write','outfits:read','outfits:write','social:read','social:write','rewards:read','privacy:manage']
  next()
},personaRouter(client),wardrobeRouter(client),outfitsRouter(client),socialRouter(client),decisionsRouter(client),rewardsRouter(client),apiV1({cfg,store}))
app.use(problemHandler)
app.listen(3001,'127.0.0.1',()=>console.log('Development gateway ready on loopback; identity is simulated, domain persistence uses Spanner.'))
