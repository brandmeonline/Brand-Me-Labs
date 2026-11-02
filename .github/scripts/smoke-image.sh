#!/usr/bin/env bash
# Run without provider credentials; verify what is actually in the image.
set -euo pipefail
service="$1"
image="$2"
case "$service" in
  gateway)
    docker run --rm -e BRANDME_MODE=development --entrypoint node "$image" -e "require('./dist/index.js'); require.resolve('@brandme/contracts/openapi.json'); console.log('gateway runtime imports OK')"
    ;;
  chain)
    docker run --rm --entrypoint node "$image" dist/scripts/verify-artifacts.mjs
    docker run --rm --entrypoint node "$image" --input-type=module -e "await import('./dist/src/midnight/spanner-store.js'); await import('./dist/src/routes/operations.js'); await import('./dist/src/midnight/reconciliation-worker.js'); await import('./dist/src/midnight/projection.js'); console.log('chain operation runtime imports OK')"
    ;;
  agents)
    docker run --rm --entrypoint python "$image" -c "import pydantic, langchain, neo4j_graphrag, faiss; print('agent dependencies import OK')"
    docker run --rm "$image"
    docker run --rm -e BRANDME_MODE=production --entrypoint python "$image" -c "from typer.testing import CliRunner; from agentic.cli.main import app; from brandme_core.config import TrustPathViolation; r = CliRunner().invoke(app, ['scan', '--tag', 'test', '--scanner-id', 'test']); assert isinstance(r.exception, TrustPathViolation), r.exception; print('legacy simulated workflow refused in production')"
    ;;
  core)
    # Default build is the `runtime` stage: non-root, no default process.
    test "$(docker run --rm --entrypoint id "$image" -u)" = 10001
    set +e; usage=$(docker run --rm "$image" 2>&1); rc=$?; set -e
    # Explicit failure branch: under set -e a failing command that is not last in an && list is ignored.
    test "$rc" -eq 64 && grep -q 'python -m brandme_core.read_api' <<<"$usage" \
      || { echo "runtime default command: rc=$rc (want 64)" >&2; printf '%s\n' "$usage" >&2; exit 1; }
    echo 'runtime default command prints usage and exits 64'
    docker run --rm --entrypoint python "$image" -m pip check
    docker run --rm --entrypoint python "$image" -m brandme_core.events.worker --help
    docker run --rm --entrypoint python "$image" -m brandme_core.events.retention --help
    docker run --rm --entrypoint python "$image" -m brandme_core.read_api --help
    docker run --rm --entrypoint python "$image" -m brandme_core.privacy_exports --help
    docker run --rm --entrypoint python "$image" -m brandme_core.domains.persona.app --help
    docker run --rm --entrypoint python "$image" brandme-data/spanner/migrations/runner.py --help
    docker run --rm --read-only --network none --entrypoint python "$image" -c "import sys; sys.path.insert(0, 'brandme-data/spanner/migrations'); import runner; v = [m.version for m in runner.load_migrations()]; assert v and 13 in v and 14 in v, v; print('packaged migrations', v)"
    # Strict modes refuse incomplete configuration before any network call. stdout must be exactly the refusal
    # record; stderr may carry dependency warnings (google.api_core warns about Python 3.11's end of life from
    # 2026-10-24) but never a traceback.
    err=$(mktemp)
    for module in brandme_core.read_api brandme_core.privacy_exports brandme_core.events.worker brandme_core.events.retention brandme_core.domains.persona.app; do
      set +e; out=$(docker run --rm --read-only --network none -e BRANDME_MODE=sandbox -e ENVIRONMENT=sandbox --entrypoint python "$image" -m "$module" --check 2>"$err"); rc=$?; set -e
      test "$rc" -eq 2 && test "$out" = '{"status":"startup_refused"}' && ! grep -q 'Traceback' "$err" \
        || { echo "$module --check: rc=$rc stdout=$out" >&2; cat "$err" >&2; exit 1; }
    done
    rm -f "$err"
    echo 'sandbox --check refuses missing configuration (exit 2)'
    # The packaged trust-path inventory audits the consumer-domain process: a configured sandbox process passes the
    # boot guard (a throwaway public key generated here), and the simulated try-on provider is still refused.
    docker run --rm --read-only --network none --entrypoint python "$image" -c "
import json
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from brandme_core.boot import BootRefused, guard
jwk = {**json.loads(ECAlgorithm.to_jwk(ec.generate_private_key(ec.SECP256R1()).public_key())), 'kid': 'smoke'}
env = {'BRANDME_MODE': 'sandbox', 'ENVIRONMENT': 'sandbox', 'CONSUMER_DOMAIN_ASSERTION_ISSUER': 'brandme-gateway',
       'CONSUMER_DOMAIN_ASSERTION_JWKS': json.dumps({'keys': [jwk]})}
assert guard('consumer_domains', env=env).value == 'sandbox'
try:
    guard('consumer_domains', env={**env, 'BRANDME_TRYON_PROVIDER': 'simulated'})
except BootRefused:
    pass
else:
    raise SystemExit('simulated try-on provider allowed in sandbox')
print('consumer_domains boot guard: configured sandbox allowed, simulated try-on refused')"
    docker run --rm --entrypoint python "$image" -c "from brandme_core.privacy_exports.app import create_app; from brandme_core.privacy_exports.storage import PrivateStore; print('selected rights export API and worker imports OK')"
    docker run --rm --entrypoint python "$image" -c "from brandme_core.read_api.app import create_app; from brandme_core.read_api.config import ReadConfig; print('authenticated read API runtime imports OK')"
    # Read-only root + /tmp tmpfs mirrors the chart's securityContext.
    docker run --rm -i --read-only --tmpfs /tmp --entrypoint python "$image" - <<'PY'
from fastapi.testclient import TestClient
from brandme_core.read_api.app import create_app
from brandme_core.read_api.config import ReadConfig

class UnavailableDatabase:
    def snapshot(self, **kwargs):
        raise RuntimeError('private provider error must not escape')

config = ReadConfig('development', 'test', 'test', 'test', 'preprod', 'ab' * 32,
                    'rights-test-credential-32-characters', 'privacy-test-credential-32-characters')
with TestClient(create_app(UnavailableDatabase(), config)) as client:
    assert client.get('/privacy/inventory').status_code == 401
    response = client.get('/privacy/inventory', headers={
        'Authorization': 'Bearer ' + config.privacy_token,
        'X-Subject-Ref': '11111111-1111-4111-8111-111111111111',
    })
    assert response.status_code == 503 and response.json() == {'error': 'dependency_unavailable'}
    assert response.headers['cache-control'] == 'no-store'
print('packaged read API HTTP authentication and redaction OK')
from brandme_core.privacy_exports.app import create_app as create_export_app
from brandme_core.privacy_exports.config import ExportConfig
export_config = ExportConfig('development', 'test', 'test', 'test', 'preprod', 'ab' * 32,
                             'brandme-development-exports-test', 'export-test-credential-32-characters')
with TestClient(create_export_app(UnavailableDatabase(), export_config, None)) as client:
    assert client.get('/capability').status_code == 401
    response = client.get('/capability', headers={
        'Authorization': 'Bearer ' + export_config.token,
        'X-Subject-Ref': '11111111-1111-4111-8111-111111111111',
    })
    assert response.status_code == 503 and response.json() == {'error': 'dependency_unavailable'}
    assert response.headers['cache-control'] == 'private, no-store'
print('packaged export API HTTP authentication and redaction OK')
from brandme_core.domains.persona.app import create_app as create_domain_app
with TestClient(create_domain_app(UnavailableDatabase(), resolve_principal=lambda request: None)) as client:
    assert client.get('/health').json() == {'status': 'ok', 'media': 'not_configured'}
    for path in ('/me/persona', '/wardrobe/items'):
        assert client.get(path).status_code == 401, path
print('packaged consumer-domain routers mount and refuse calls without a gateway assertion')
PY
    docker run --rm -e BRANDME_MODE=development --entrypoint python "$image" -c "from uuid import uuid4; from brandme_core.domains.rights.projection import apply_observation; from brandme_core.domains.privacy.privacy import MyDataService; from brandme_core.events import EventEnvelope; j = str(uuid4()); EventEnvelope(event_type='privacy.deletion.requested', schema_version='1', aggregate_type='deletion_job', aggregate_id=j, aggregate_version=1, environment='development', actor_ref='service:privacy', correlation_id=j, privacy_class='restricted', payload={'job_id': j, 'scope': 'account'}).validate(); print('core rights/privacy imports and packaged event schema OK')"
    ;;
  console)
    docker run --rm -i --entrypoint node "$image" - <<'NODE'
const { createRequire } = require('node:module');
const { resolve } = require('node:path');
const appRequire = createRequire(resolve('brandme-console/server.js'));
const nextRequire = createRequire(appRequire.resolve('next/package.json'));
const sharp = nextRequire('sharp');
Promise.all(['avif', 'webp'].map(format =>
  sharp({ create: { width: 2, height: 2, channels: 3, background: { r: 1, g: 2, b: 3 } } })
    .toFormat(format).toBuffer()
)).then(buffers => {
  if (buffers.some(b => !b.length)) throw new Error('empty codec output');
  console.log('Next.js', nextRequire('next/package.json').version, 'sharp', sharp.versions.sharp, 'native image codecs OK');
}).catch(error => { console.error(error); process.exit(1); });
NODE
    cid=$(docker run -d -e HOSTNAME=0.0.0.0 -p 127.0.0.1:33002:3002 "$image")
    trap 'docker rm -f "$cid" >/dev/null' EXIT
    for attempt in $(seq 1 30); do
      if curl -fsS http://127.0.0.1:33002/ >/dev/null; then
        echo 'console standalone HTTP response OK'
        exit 0
      fi
      sleep 1
    done
    docker logs "$cid"
    exit 1
    ;;
  *) echo "Unknown service: $service" >&2; exit 2 ;;
esac
