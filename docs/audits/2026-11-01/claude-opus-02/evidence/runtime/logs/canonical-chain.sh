#!/usr/bin/env bash
# Audit-only: start the canonical consumer-domain service and the gateway from the worktree, run journey.py, stop both.
set -uo pipefail
S=/tmp/claude-0/-home-user-Brand-Me-Labs/1bf61dcf-0f4d-53ea-917a-a94fd3490bcc/scratchpad
WT=$S/wt-main; OUT=$S/emu; PY=$S/venv-py311/bin/python
log(){ echo "$(date -u +%H:%M:%S) $*"; }
log "HEAD $(git -C $WT rev-parse HEAD)"

# --- shared Spanner/emulator settings (same database the smoke migrated) ---
export SPANNER_EMULATOR_HOST=127.0.0.1:9010 SPANNER_PROJECT_ID=test-project SPANNER_INSTANCE_ID=brandme-instance SPANNER_DATABASE_ID=brandme-db
export PYTHONPATH=$WT
cd $WT
log "migrations (idempotent):"; $PY brandme-data/spanner/migrations/runner.py up --create-database --wait 60 2>&1 | tail -3

# --- consumer-domain service (canonical entrypoint) ---
set -a; . $OUT/dev-keys/consumer-domains-service.env; set +a
export ENVIRONMENT=development BRANDME_MODE=development CONSUMER_DOMAIN_ASSERTION_ISSUER=brandme-gateway PORT=8010
log "preflight:"; $PY -m brandme_core.config preflight --service consumer_domains 2>&1 | tail -4
log "service --check:"; $PY -m brandme_core.domains.persona.app --check 2>&1 | tail -2
$PY -m brandme_core.domains.persona.app > $OUT/consumer-domains.log 2>&1 & SVC=$!
for i in $(seq 1 30); do (echo > /dev/tcp/127.0.0.1/8010) 2>/dev/null && break; sleep 1; done
log "consumer-domains pid=$SVC port 8010 $( (echo > /dev/tcp/127.0.0.1/8010) 2>/dev/null && echo up || echo DOWN)"
curl -s http://127.0.0.1:8010/health; echo

# --- gateway (direct tsx, no pnpm shim) ---
unset ENVIRONMENT CONSUMER_DOMAIN_ASSERTION_JWKS CONSUMER_DOMAIN_ASSERTION_ISSUER
set -a; . $OUT/dev-keys/consumer-domains-gateway.env; set +a
# docker-compose env_file expands \n inside double-quoted values; bash `source` does not. Expand it here.
export CONSUMER_DOMAIN_ASSERTION_KEY="$(printf '%b' "$CONSUMER_DOMAIN_ASSERTION_KEY")"
log "gateway key: $(printf '%s' "$CONSUMER_DOMAIN_ASSERTION_KEY" | wc -l) PEM lines, kid $CONSUMER_DOMAIN_ASSERTION_KID"
export BRANDME_MODE=development PORT=3001 IDENTITY_PROVIDER=dev CONSUMER_DOMAIN_SERVICE_URL=http://127.0.0.1:8010 BRAIN_SERVICE_URL=http://127.0.0.1:8000
export CORS_ORIGINS=http://localhost:3000,http://localhost:3002 PUBLIC_ORIGINS=http://localhost:3000,http://localhost:3002
( cd $WT/brandme-gateway && exec ./node_modules/.bin/tsx src/index.ts ) > $OUT/gateway-canonical.log 2>&1 & GWP=$!
for i in $(seq 1 40); do (echo > /dev/tcp/127.0.0.1/3001) 2>/dev/null && break; sleep 1; done
log "gateway pid=$GWP port 3001 $( (echo > /dev/tcp/127.0.0.1/3001) 2>/dev/null && echo up || echo DOWN)"
curl -s http://127.0.0.1:3001/healthz; echo

# --- journey ---
python3 -I $OUT/journey.py $OUT/canonical-journey.json; RC=$?
log "journey exit=$RC"

kill -TERM $GWP $SVC 2>/dev/null; sleep 2; kill -KILL $GWP $SVC 2>/dev/null
log "stopped; 3001 $( (echo > /dev/tcp/127.0.0.1/3001) 2>/dev/null && echo still-open || echo closed), 8010 $( (echo > /dev/tcp/127.0.0.1/8010) 2>/dev/null && echo still-open || echo closed)"
exit $RC
