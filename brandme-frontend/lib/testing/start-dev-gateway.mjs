import {spawn} from 'node:child_process'
import {randomBytes} from 'node:crypto'
import {fileURLToPath} from 'node:url'
import {createInterface} from 'node:readline'
import {createRequire} from 'node:module'
const require=createRequire(new URL('../../../brandme-gateway/package.json',import.meta.url))
const env={...process.env,BRANDME_MODE:'development',IDENTITY_PROVIDER:'dev',SPANNER_EMULATOR_HOST:'127.0.0.1:9010',
  BRANDME_DEV_ASSERTION_KEY:randomBytes(32).toString('hex'),BRAIN_SERVICE_URL:'http://127.0.0.1:8011',
  PUBLIC_ORIGINS:'http://127.0.0.1:3000,http://localhost:3000',SESSION_TTL_HOURS:'1'}
if(process.env.BRANDME_MODE!=='development'||process.env.NODE_ENV==='production')throw new Error('Opt in with BRANDME_MODE=development')
const python=spawn(process.env.BRANDME_PYTHON||'python3',[fileURLToPath(new URL('./dev-domains.py',import.meta.url))],{env,stdio:['ignore','pipe','inherit']})
const children=[python]
const lines=createInterface({input:python.stdout})
let started=false
const fail=()=>{children.forEach(child=>child.kill('SIGTERM'));process.exit(1)}
python.on('exit',fail)
lines.on('line',line=>{
  if(started)return
  let info;try{info=JSON.parse(line)}catch{return}
  if(!/^cd[a-f0-9]{20}$/.test(info.database))return fail()
  started=true
  const gateway=spawn(process.execPath,['--import',require.resolve('tsx'),fileURLToPath(new URL('./dev-gateway.mjs',import.meta.url))],
    {env:{...env,SPANNER_PROJECT_ID:info.project,SPANNER_INSTANCE_ID:info.instance,SPANNER_DATABASE_ID:info.database},stdio:'inherit'})
  children.push(gateway);gateway.on('exit',fail)
})
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{python.removeListener('exit',fail);children.forEach(child=>child.kill('SIGTERM'));process.exit(0)})
