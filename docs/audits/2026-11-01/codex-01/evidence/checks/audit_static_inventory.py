"""Auditor-owned, non-executing syntax/asset inventory. Never imports repo modules."""
import ast, collections, datetime, hashlib, json, pathlib, struct, subprocess, sys

ROOT = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2]).resolve()
SHA = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'], text=True).strip()
files = subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z']).decode().split('\0')
files = [p for p in files if p]
rows, syntax, json_checks, assets = [], [], [], []
for rel in files:
    p = ROOT / rel
    data = p.read_bytes()
    row = {'path': rel, 'sha': SHA, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
           'module': rel.split('/')[0], 'extension': p.suffix.lower(), 'coverage': 'inventoried; semantic review recorded separately'}
    rows.append(row)
    if p.suffix == '.py':
        try:
            ast.parse(data, filename=rel)
            syntax.append({'path': rel, 'status':'parsed'})
        except (SyntaxError,UnicodeError) as e:
            syntax.append({'path':rel,'status':'parse_error','line':getattr(e,'lineno',None),'error_type':type(e).__name__, 'message':getattr(e,'msg',str(e))})
    if p.suffix == '.json':
        try:
            json.loads(data)
            json_checks.append({'path':rel,'status':'parsed'})
        except (ValueError,UnicodeError) as e:
            json_checks.append({'path':rel,'status':'parse_error','error_type':type(e).__name__})
    if p.suffix.lower() in {'.glb','.gltf','.usdz','.png','.jpg','.jpeg','.webp','.woff2','.onnx','.tflite'}:
        asset = {k:row[k] for k in ('path','bytes','sha256')}
        if p.suffix == '.glb':
            if len(data)>=12:
                magic,version,length = struct.unpack('<4sII',data[:12])
                asset.update(glb_header_valid=magic==b'glTF' and version==2 and length==len(data), glb_version=version, declared_bytes=length)
        asset['verification']='size/hash and GLB container header only; no rendering or licensing verification'
        assets.append(asset)

def save(name, data):
    (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
save('files.json', rows)
save('assets.json', assets)
result = {'id':'CHECK-STATIC-001','time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'sha':SHA,'cwd':str(ROOT),'python_version':sys.version.split()[0],
          'mode':'static parsing; auditor-owned script; repository code not imported/executed',
          'file_count':len(rows),'python':syntax,'json':json_checks,
          'application_test_counts':{'passed':0,'failed':0,'skipped':0,'not_run':'all runtime/build/browser/integration suites'},
          'limits':'Parsing verifies syntax/encoding only, not imports, types, authorization, business behavior, or deployment.'}
save('static-checks.json',result)
print(json.dumps({'sha':SHA,'files':len(rows),'python_files':len(syntax),'python_parse_errors':sum(x['status']!='parsed' for x in syntax),
                  'json_files':len(json_checks),'json_parse_errors':sum(x['status']!='parsed' for x in json_checks),
                  'assets':len(assets),'modules':dict(collections.Counter(x['module'] for x in rows))},indent=2))
