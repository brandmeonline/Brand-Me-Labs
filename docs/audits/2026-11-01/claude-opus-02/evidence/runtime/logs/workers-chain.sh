#!/usr/bin/env bash
# Audit-only: Pub/Sub emulator + canonical consumer-domain service + gateway, then journey2.py (which runs the
# canonical worker processes). Stops everything by PID. Not part of the repository.
set -uo pipefail
S=/tmp/claude-0/-home-user-Brand-Me-Labs/1bf61dcf-0f4d-53ea-917a-a94fd3490bcc/scratchpad
WT=$S/wt-main; OUT=$S/emu; export PY=$S/venv-py311/bin/python; export WT
log(){ echo "$(date -u +%H:%M:%S) $*"; }
log "HEAD $(git -C $WT rev-parse HEAD)"
export SPANNER_EMULATOR_HOST=127.0.0.1:9010 SPANNER_PROJECT_ID=test-project SPANNER_INSTANCE_ID=brandme-instance SPANNER_DATABASE_ID=brandme-db
export PYTHONPATH=$WT
cd $WT

# --- Pub/Sub emulator (repo-pinned binary) ---
export PUBSUB_EMULATOR_HOST=127.0.0.1:8085
$OUT/pubsub-emulator/platform/pubsub-emulator/bin/cloud-pubsub-emulator --host=127.0.0.1 --port=8085 > $OUT/pubsub-emulator.log 2>&1 & PS=$!
for i in $(seq 1 60); do (echo > /dev/tcp/127.0.0.1/8085) 2>/dev/null && break; sleep 1; done
log "pubsub pid=$PS port 8085 $( (echo > /dev/tcp/127.0.0.1/8085) 2>/dev/null && echo up || echo DOWN)"
SUF=audit$(date +%s | tail -c 5)
export TOPIC_PUBLIC=projects/test-project/topics/brandme-development-public-$SUF
export TOPIC_MEMBERS=projects/test-project/topics/brandme-development-member-private-$SUF
export TOPIC_RESTRICTED=projects/test-project/topics/brandme-development-restricted-$SUF
export LANE_SUB=projects/test-project/subscriptions/brandme-development-consumer-lane-$SUF
for t in $TOPIC_PUBLIC $TOPIC_MEMBERS $TOPIC_RESTRICTED; do
  printf "topic %s -> %s\n" "$t" "$(curl -s -o /dev/null -w '%{http_code}' -X PUT -H 'content-type: application/json' -d '{"messageRetentionDuration":"86400s"}' http://127.0.0.1:8085/v1/$t)"
done
printf "subscription -> %s\n" "$(curl -s -o /dev/null -w '%{http_code}' -X PUT -H 'content-type: application/json' -d "{\"topic\":\"$TOPIC_MEMBERS\",\"ackDeadlineSeconds\":10}" http://127.0.0.1:8085/v1/$LANE_SUB)"

# --- consumer-domain service ---
set -a; . $OUT/dev-keys/consumer-domains-service.env; set +a
ENVIRONMENT=development BRANDME_MODE=development CONSUMER_DOMAIN_ASSERTION_ISSUER=brandme-gateway PORT=8010 \
  $PY -m brandme_core.domains.persona.app > $OUT/consumer-domains-w.log 2>&1 & SVC=$!
for i in $(seq 1 30); do (echo > /dev/tcp/127.0.0.1/8010) 2>/dev/null && break; sleep 1; done
log "consumer-domains pid=$SVC 8010 $( (echo > /dev/tcp/127.0.0.1/8010) 2>/dev/null && echo up || echo DOWN)"

# --- gateway ---
set -a; . $OUT/dev-keys/consumer-domains-gateway.env; set +a
export CONSUMER_DOMAIN_ASSERTION_KEY="$(printf '%b' "$CONSUMER_DOMAIN_ASSERTION_KEY")"
( cd $WT/brandme-gateway && BRANDME_MODE=development PORT=3001 IDENTITY_PROVIDER=dev CONSUMER_DOMAIN_SERVICE_URL=http://127.0.0.1:8010 \
  BRAIN_SERVICE_URL=http://127.0.0.1:8000 CORS_ORIGINS=http://localhost:3000,http://localhost:3002 PUBLIC_ORIGINS=http://localhost:3000,http://localhost:3002 \
  exec ./node_modules/.bin/tsx src/index.ts ) > $OUT/gateway-w.log 2>&1 & GWP=$!
for i in $(seq 1 40); do (echo > /dev/tcp/127.0.0.1/3001) 2>/dev/null && break; sleep 1; done
log "gateway pid=$GWP 3001 $( (echo > /dev/tcp/127.0.0.1/3001) 2>/dev/null && echo up || echo DOWN)"

unset CONSUMER_DOMAIN_ASSERTION_KEY CONSUMER_DOMAIN_ASSERTION_KID CONSUMER_DOMAIN_ASSERTION_JWKS
python3 -I $OUT/journey2.py $OUT/workers-journey.json; RC=$?
log "journey2 exit=$RC"
kill -TERM $GWP $SVC $PS 2>/dev/null; sleep 2; kill -KILL $GWP $SVC $PS 2>/dev/null
log "stopped; 3001 $( (echo > /dev/tcp/127.0.0.1/3001) 2>/dev/null && echo open || echo closed) 8010 $( (echo > /dev/tcp/127.0.0.1/8010) 2>/dev/null && echo open || echo closed) 8085 $( (echo > /dev/tcp/127.0.0.1/8085) 2>/dev/null && echo open || echo closed)"
exit $RC
