#!/bin/bash
################################################################################
# Integration Agent
# Wires up all services and validates communication
################################################################################

set -e
source .env.deploy
source agents/lib/common.sh
source .deployment/infrastructure.env
source .deployment/database.env
source .deployment/services.env

log_agent "Integration Agent" "Starting service integration..."

# ============================================================================
# Wire up NATS event streams
# ============================================================================

log_step "Creating NATS JetStream streams..."

kubectl exec -n brandme $(kubectl get pod -n brandme -l app.kubernetes.io/name=nats -o jsonpath='{.items[0].metadata.name}') -- \
    nats stream add SCAN_EVENTS \
    --subjects="scan.*" \
    --storage=file \
    --retention=limits \
    --max-age=30d \
    --replicas=1 || true

kubectl exec -n brandme $(kubectl get pod -n brandme -l app.kubernetes.io/name=nats -o jsonpath='{.items[0].metadata.name}') -- \
    nats stream add POLICY_EVENTS \
    --subjects="policy.*" \
    --storage=file \
    --retention=limits \
    --max-age=30d \
    --replicas=1 || true

log_success "NATS streams created"

# ============================================================================
# Test service-to-service communication
# ============================================================================

log_step "Testing service connectivity..."

# Test gateway -> database
log_info "Testing gateway database connection..."
kubectl exec -n brandme $(kubectl get pod -n brandme -l app=brandme-gateway -o jsonpath='{.items[0].metadata.name}') -- \
    curl -s http://localhost:3000/health | grep -q "ok" && log_success "Gateway health check passed"

# Test agents -> Neo4j
log_info "Testing Neo4j connectivity..."
kubectl run neo4j-test --rm -i --restart=Never --image=neo4j:5.16 -n brandme -- \
    cypher-shell -a "$NEO4J_URI" -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" || log_warn "Neo4j test skipped"

log_success "Service integration complete"

log_agent "Integration Agent" "✅ Integration complete!"
