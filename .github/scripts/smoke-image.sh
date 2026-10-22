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
    ;;
  agents)
    docker run --rm --entrypoint python "$image" -c "import pydantic, langchain, neo4j_graphrag, faiss, sentence_transformers; print('agent dependencies import OK')"
    docker run --rm "$image"
    docker run --rm -e BRANDME_MODE=production --entrypoint python "$image" -c "from typer.testing import CliRunner; from agentic.cli.main import app; from brandme_core.config import TrustPathViolation; r = CliRunner().invoke(app, ['scan', '--tag', 'test', '--scanner-id', 'test']); assert isinstance(r.exception, TrustPathViolation), r.exception; print('legacy simulated workflow refused in production')"
    ;;
  core)
    docker run --rm --entrypoint python "$image" -m pip check
    ;;
  console)
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
