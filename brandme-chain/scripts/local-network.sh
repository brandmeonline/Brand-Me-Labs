#!/usr/bin/env bash
# Local Midnight network for `pnpm test:midnight:network`.
#   scripts/local-network.sh up     # node + indexer (compose) + proof server 8.1.0 on 127.0.0.1:6300
#   scripts/local-network.sh env    # prints MN_NODE_PORT / MN_INDEXER_PORT for `export $(...)`
#   scripts/local-network.sh down
# The proof server downloads public SRS parameters from srs.midnight.network
# (it verifies their hashes). Behind a TLS-intercepting proxy set
# PROOF_SERVER_CA_BUNDLE=/path/ca.pem and HTTPS_PROXY.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
compose=(docker compose -p brandme-midnight -f "$here/tests/network/compose.yml")
img="midnightntwrk/proof-server:8.1.0@sha256:801bbc0340e9e96f16735f77b523f23c7459e3359842f7c79c2c53f4e994d531"
case "${1:-}" in
  up)
    "${compose[@]}" up -d node indexer
    args=(-d --name brandme-proof-server --network host)
    if [[ -n "${PROOF_SERVER_CA_BUNDLE:-}" ]]; then
      args+=(-e "HTTPS_PROXY=${HTTPS_PROXY:-}" -e SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt -v "$PROOF_SERVER_CA_BUNDLE:/etc/ssl/certs/ca-certificates.crt:ro")
    fi
    docker rm -f brandme-proof-server >/dev/null 2>&1 || true
    docker run "${args[@]}" "$img" midnight-proof-server -v >/dev/null
    for _ in $(seq 1 90); do curl -sf http://127.0.0.1:6300/health >/dev/null && break; sleep 2; done
    curl -sf http://127.0.0.1:6300/version && echo " proof server ready"
    ;;
  env)
    echo "MN_NODE_PORT=$("${compose[@]}" port node 9944 | cut -d: -f2) MN_INDEXER_PORT=$("${compose[@]}" port indexer 8088 | cut -d: -f2) MN_PROOF_PORT=6300"
    ;;
  down)
    docker rm -f brandme-proof-server >/dev/null 2>&1 || true
    "${compose[@]}" down -v
    ;;
  *) echo "usage: $0 up|env|down" >&2; exit 2 ;;
esac
