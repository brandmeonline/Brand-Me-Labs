#!/bin/bash
# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Infrastructure Testing Script
# ==============================
#
# Tests all infrastructure components and dependencies

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Brand.Me Infrastructure Tests${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to run a test
run_test() {
    local test_name=$1
    local test_command=$2

    ((TOTAL_TESTS++))
    echo -n "Testing ${test_name}... "

    if eval "$test_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASSED_TESTS++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAILED_TESTS++))
        return 1
    fi
}

# Test PostgreSQL
echo -e "\n${YELLOW}PostgreSQL Tests${NC}"
run_test "PostgreSQL connection" "pg_isready -h localhost -p 5432"
run_test "PostgreSQL version" "psql -h localhost -U postgres -c 'SELECT version()'"

# Test Redis
echo -e "\n${YELLOW}Redis Tests${NC}"
run_test "Redis ping" "redis-cli -h localhost -p 6379 ping"
run_test "Redis set/get" "redis-cli -h localhost -p 6379 set test_key test_value && redis-cli -h localhost -p 6379 get test_key"

# Test NATS
echo -e "\n${YELLOW}NATS Tests${NC}"
run_test "NATS health" "curl -sf http://localhost:8222/healthz"
run_test "NATS JetStream enabled" "curl -sf http://localhost:8222/jsz | grep -q '\"config\"'"

# Test Services
echo -e "\n${YELLOW}Service Health Checks${NC}"
run_test "Gateway health" "curl -sf http://localhost:3000/health"
run_test "Brain health" "curl -sf http://localhost:8000/health"
run_test "Policy health" "curl -sf http://localhost:8001/health"
run_test "Identity health" "curl -sf http://localhost:8100/health"
run_test "Knowledge health" "curl -sf http://localhost:8101/health"
run_test "Compliance health" "curl -sf http://localhost:8102/health"
run_test "Chain health" "curl -sf http://localhost:3001/health"

# Test Observability Stack
echo -e "\n${YELLOW}Observability Tests${NC}"
run_test "Prometheus" "curl -sf http://localhost:9090/-/healthy"
run_test "Grafana" "curl -sf http://localhost:3030/api/health"
run_test "Loki" "curl -sf http://localhost:3100/ready"
run_test "OpenTelemetry Collector" "curl -sf http://localhost:13133"

# Test Container Health
echo -e "\n${YELLOW}Container Health${NC}"
if command -v docker &> /dev/null; then
    run_test "All containers running" "docker ps | grep -q brandme"
    run_test "No containers restarting" "! docker ps --filter 'status=restarting' | grep -q brandme"
fi

# Test Network Connectivity
echo -e "\n${YELLOW}Network Connectivity${NC}"
run_test "Gateway → Brain" "docker exec brandme-gateway curl -sf http://brain:8000/health"
run_test "Brain → Policy" "docker exec brandme-brain curl -sf http://policy:8001/health"
run_test "Brain → Database" "docker exec brandme-brain pg_isready -h postgres -p 5432"

# Test Metrics Endpoints
echo -e "\n${YELLOW}Metrics Endpoints${NC}"
run_test "Gateway metrics" "curl -sf http://localhost:3000/metrics"
run_test "Brain metrics" "curl -sf http://localhost:8000/metrics"
run_test "PostgreSQL exporter" "curl -sf http://localhost:9187/metrics"
run_test "Redis exporter" "curl -sf http://localhost:9121/metrics"

# Test Database Schemas
echo -e "\n${YELLOW}Database Schema Tests${NC}"
run_test "Users table exists" "psql -h localhost -U postgres -d brandme_dev -c '\d users'"
run_test "Garments table exists" "psql -h localhost -U postgres -d brandme_dev -c '\d garments'"
run_test "Scan events table exists" "psql -h localhost -U postgres -d brandme_dev -c '\d scan_event'"
run_test "Audit log table exists" "psql -h localhost -U postgres -d brandme_dev -c '\d audit_log'"

# Test Celery Workers
echo -e "\n${YELLOW}Orchestrator Tests${NC}"
run_test "Celery worker running" "docker exec brandme-orchestrator celery -A celery_app inspect active"
run_test "Celery beat running" "docker ps | grep -q brandme-orchestrator-beat"

# Print Results
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test Results${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Total Tests:  ${YELLOW}${TOTAL_TESTS}${NC}"
echo -e "Passed:       ${GREEN}${PASSED_TESTS}${NC}"
echo -e "Failed:       ${RED}${FAILED_TESTS}${NC}"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
