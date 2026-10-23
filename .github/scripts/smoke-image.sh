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
    docker run --rm --entrypoint python "$image" -c "import pydantic, langchain, neo4j_graphrag, faiss, sentence_transformers; print('agent dependencies import OK')"
    docker run --rm "$image"
    docker run --rm -e BRANDME_MODE=production --entrypoint python "$image" -c "from typer.testing import CliRunner; from agentic.cli.main import app; from brandme_core.config import TrustPathViolation; r = CliRunner().invoke(app, ['scan', '--tag', 'test', '--scanner-id', 'test']); assert isinstance(r.exception, TrustPathViolation), r.exception; print('legacy simulated workflow refused in production')"
    ;;
  core)
    docker run --rm --entrypoint python "$image" -m pip check
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
