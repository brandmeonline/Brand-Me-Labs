"""Fetch pinned dev-only MediaPipe files. No key, CDN runtime call or private photo."""
from pathlib import Path
import base64, hashlib, io, json, tarfile, urllib.request
root = Path(__file__).resolve().parents[2]
out = root / 'brandme-frontend/public/demo/vision'
version = '0.10.35'
def download(url):
    with urllib.request.urlopen(url, timeout=60) as r: return r.read()
bundle = download(f'https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-{version}.tgz')
assert base64.b64encode(hashlib.sha512(bundle).digest()).decode() == 'HOvadwVRE6JC+45nyYhmnywnr5h/J8KZvOeUNVOG9q/0875pZgItznFB9bRTvLc264YSJqiZ1NsIpCStJw/egg=='
files = {}
with tarfile.open(fileobj=io.BytesIO(bundle)) as archive:
    for name in ['vision_bundle.cjs', 'wasm/vision_wasm_internal.js', 'wasm/vision_wasm_internal.wasm', 'wasm/vision_wasm_nosimd_internal.js', 'wasm/vision_wasm_nosimd_internal.wasm']:
        content = archive.extractfile('package/' + name).read()
        target = out / version / name.replace('.cjs', '.js')
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
        files[target.relative_to(out).as_posix()] = {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
model = download('https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task')
assert hashlib.sha256(model).hexdigest() == '59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a'
(out / 'pose-lite-v1.task').write_bytes(model)
files['pose-lite-v1.task'] = {'sha256': hashlib.sha256(model).hexdigest(), 'bytes': len(model)}
(out / 'manifest.json').write_text(json.dumps({'schemaVersion': 1, 'developmentOnly': True, 'runtime': version, 'modelUrl': '/demo/vision/pose-lite-v1.task', 'wasmRoot': f'/demo/vision/{version}/wasm', 'files': files, 'rights': 'Runtime package declares Apache-2.0. Model redistribution review pending; dev download only, no source redistribution.', 'source': 'https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker'}, indent=2)+'\n')
print('Prepared pinned local vision runtime/model; dev-only, no credential. Files:',len(files))
