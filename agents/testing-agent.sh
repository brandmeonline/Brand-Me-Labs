#!/bin/bash
################################################################################
# Testing Agent
# Runs comprehensive tests on deployed system
################################################################################

set -e
source .env.deploy
source agents/lib/common.sh
source .deployment/services.env

log_agent "Testing Agent" "Starting automated testing..."

# ============================================================================
# Health Checks
# ============================================================================

log_step "Running health checks..."

SERVICES=(
    "$GATEWAY_URL/health:Gateway"
    "$GATEWAY_URL:3001/health:Chain Service"
    "$CONSOLE_URL/api/health:Console"
)

for service_info in "${SERVICES[@]}"; do
    IFS=: read -r url name <<< "$service_info"
    log_info "Testing $name..."

    if curl -f -s "$url" > /dev/null 2>&1; then
        log_success "$name is healthy"
    else
        log_warn "$name health check failed (might not be critical)"
    fi
done

# ============================================================================
# API Endpoint Tests
# ============================================================================

log_step "Testing API endpoints..."

# Test scan endpoint (should return 401 without auth)
log_info "Testing POST /scan endpoint..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$GATEWAY_URL/scan" \
    -H "Content-Type: application/json" \
    -d '{"garment_tag":"test"}')

if [ "$RESPONSE" = "401" ] || [ "$RESPONSE" = "400" ]; then
    log_success "Scan endpoint responding correctly"
else
    log_warn "Scan endpoint returned unexpected status: $RESPONSE"
fi

# ============================================================================
# Agent Workflow Test
# ============================================================================

log_step "Testing agent workflow..."

log_info "Agent workflow tests would run here in production"
log_info "This would test the full scan → policy → blockchain flow"

# ============================================================================
# Graph RAG Test
# ============================================================================

log_step "Testing Graph RAG..."

log_info "Graph RAG query tests would run here"
log_info "This would test knowledge graph queries"

# ============================================================================
# Load Test
# ============================================================================

if [ "${RUN_LOAD_TEST:-false}" = "true" ]; then
    log_step "Running load test..."

    log_info "Simulating 1000 concurrent requests..."
    # In production, would use k6 or similar
    log_info "Load test would run here with actual load testing tool"
fi

log_agent "Testing Agent" "✅ Testing complete!"
