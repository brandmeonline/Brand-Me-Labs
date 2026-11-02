"""Audit-only structural validator. Usage: python -I validate_pack.py PACK CLONE."""
import datetime, hashlib, json, pathlib, re, subprocess, sys
from urllib.parse import unquote
out=pathlib.Path(sys.argv[1]).resolve();repo=pathlib.Path(sys.argv[2]).resolve()
errors=[];warnings=[];data={};sources={};checked=0
for p in out.rglob('*.json'):
    try:data[p.relative_to(out).as_posix()]=json.loads(p.read_text(encoding='utf-8-sig'))
    except Exception as e:errors.append(dict(file=str(p.relative_to(out)),type='json',error=type(e).__name__))
def md_links(s):
    for m in re.finditer(r'\]\(',s):
        i=m.end();start=i;depth=1
        while i<len(s) and depth:
            if s[i]=='(' and (i==0 or s[i-1]!='\\'):depth+=1
            elif s[i]==')' and (i==0 or s[i-1]!='\\'):depth-=1
            i+=1
        if depth==0:yield s[start:i-1].strip().strip('<>')
def inspect(link,origin):
    global checked
    if not link or link.startswith(('#','mailto:','data:')):return
    checked+=1
    if link.startswith(('https://','http://')):
        m=re.match(r'https://github\.com/brandmeonline/Brand-Me-Labs/blob/([0-9a-f]{40})/([^#]+)(?:#L(\d+)(?:-L(\d+))?)?$',link)
        if not m:return
        sha,path,line,end=m.groups();key=sha+':'+unquote(path)
        if key not in sources:
            r=subprocess.run(['git','-C',str(repo),'show',key],capture_output=True)
            sources[key]=len(r.stdout.splitlines()) if r.returncode==0 else None
        n=sources[key]
        if n is None:errors.append(dict(file=origin.name,type='missing_git_source',link=link))
        elif line and (int(line)<1 or int(line)>n or end and int(end)>n):errors.append(dict(file=origin.name,type='source_line_out_of_bounds',link=link,lines=n))
    else:
        path=unquote(link.split('#')[0].split('?')[0])
        if not (origin.parent/path).exists():errors.append(dict(file=origin.relative_to(out).as_posix(),type='missing_relative_link',link=link))
for p in out.rglob('*.md'):
    prose=re.sub(r'(?ms)^```[^\n]*\n.*?^```[^\n]*', '', p.read_text(encoding='utf-8-sig'))
    for link in md_links(prose):inspect(link,p)
for p in out.rglob('*.html'):
    for link in re.findall(r'(?:href|src)=["\']([^"\']+)',p.read_text(encoding='utf-8')):inspect(link,p)
def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,list):
        for v in value:yield from strings(v)
    elif isinstance(value,dict):
        for v in value.values():yield from strings(v)
for filename,content in data.items():
    if filename.endswith('validation.json'):continue
    for link in strings(content):
        if link.startswith('https://github.com/brandmeonline/Brand-Me-Labs/blob/') and not any(c.isspace() for c in link):inspect(link,out/filename)
known=set();counts={}
for name in ['branches','capabilities','components','integrations','journeys','findings']:
    ids=[r['id'] for r in data.get('evidence/'+name+'.json',[])]
    counts[name]=len(ids);known.update(ids)
    if len(ids)!=len(set(ids)):errors.append(dict(type='duplicate_ids',inventory=name))
for p in out.glob('*.md'):
    for ident in set(re.findall(r'\b(?:F-(?:ARCH|SEC|BR|UX)-\d{3}|CAP-\d{3}|BR-\d{3}|J-\d{3}|INT-\d{3})\b',p.read_text(encoding='utf-8'))):
        if ident not in known:errors.append(dict(type='unknown_id',file=p.name,id=ident))
for f in data.get('evidence/findings.json',[]):
    for field in ['id','category','severity','severity_rationale','confidence','evidence','preconditions','expected_behavior','observed_behavior','user_business_impact','reproduction_validation','recommended_fix','effort_range','acceptance_test']:
        if not f.get(field):errors.append(dict(type='missing_finding_field',id=f['id'],field=field))
    for ident in f['affected_capabilities']+f['affected_journeys']:
        if ident not in known:errors.append(dict(type='unknown_finding_reference',id=f['id'],reference=ident))
    for e in f['evidence']:
        url=e if isinstance(e,str) else e.get('url','')
        if url.startswith('http'):inspect(url,out/'evidence/findings.json')
for m in data.get('visuals/screenshot-manifest.json',[]):
    p=out/'visuals'/m['filename']
    if not p.exists():errors.append(dict(type='missing_screenshot',file=m['filename']))
    elif m.get('image_sha256') and hashlib.sha256(p.read_bytes()).hexdigest()!=m['image_sha256']:errors.append(dict(type='screenshot_hash',file=m['filename']))
requirements=data.get('evidence/requirement-traceability.json',{}).get('rows',[])
if requirements:
    ids=[r['requirement_id'] for r in requirements]
    catalog={r['id'] for r in data['evidence/requirements-inventory.json']['requirements']}
    if len(ids)!=len(set(ids)) or set(ids)!=catalog:errors.append(dict(type='requirement_traceability_id_mismatch'))
    counts['requirements_mapped']=len(ids)
    for r in requirements:
        for ident in r['capability_ids']:
            if ident not in known:errors.append(dict(type='unknown_requirement_capability',id=r['requirement_id'],reference=ident))
pattern=re.compile(r'gh[pousr]_[A-Za-z0-9]{24,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
for p in out.rglob('*'):
    if p.is_file() and p.suffix in {'.json','.md','.txt','.html','.py','.ps1'}:
        for i,line in enumerate(p.read_text(encoding='utf-8-sig',errors='replace').splitlines(),1):
            if pattern.search(line) and p.name!='validate_pack.py':warnings.append(dict(type='credential_pattern_review',file=p.relative_to(out).as_posix(),line=i))
result=dict(time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='pass' if not errors else 'fail',json_files=len(data),links_checked=checked,
 immutable_source_files_checked=len(sources),inventory_counts=counts,errors=errors,warnings=warnings,
 scope='Artifact structural/source-reference validation only. No application code execution. Network links not all live-probed.')
(out/'evidence/final-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2));sys.exit(1 if errors else 0)
