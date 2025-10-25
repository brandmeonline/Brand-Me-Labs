#!/bin/bash
################################################################################
# Brand.Me One-Click Production Deployment
# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# USAGE: ./deploy-brandme.sh
#
# This orchestrator coordinates all sub-agents for complete deployment.
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging
LOG_FILE="deployment-$(date +%Y%m%d-%H%M%S).log"

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

################################################################################
# Pre-flight Checks
################################################################################

preflight_checks() {
    log "🔍 Running pre-flight checks..."

    # Check if .env.deploy exists
    if [ ! -f ".env.deploy" ]; then
        error ".env.deploy not found!"
        echo ""
        echo "Please create .env.deploy with your API keys:"
        echo "  cp .env.deploy.example .env.deploy"
        echo "  nano .env.deploy"
        echo ""
        exit 1
    fi

    # Load environment
    source .env.deploy

    # Check required variables
    required_vars=(
        "ANTHROPIC_API_KEY"
        "OPENAI_API_KEY"
        "BLOCKFROST_API_KEY"
        "GCP_PROJECT_ID"
        "GCP_REGION"
        "GCP_CREDENTIALS_PATH"
    )

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            error "Missing required variable: $var"
            exit 1
        fi
    done

    # Check if GCP credentials file exists
    if [ ! -f "$GCP_CREDENTIALS_PATH" ]; then
        error "GCP credentials file not found: $GCP_CREDENTIALS_PATH"
        exit 1
    fi

    # Check required tools
    command -v gcloud >/dev/null 2>&1 || { error "gcloud CLI not installed. Install from: https://cloud.google.com/sdk/docs/install"; exit 1; }
    command -v kubectl >/dev/null 2>&1 || { error "kubectl not installed. Install from: https://kubernetes.io/docs/tasks/tools/"; exit 1; }
    command -v helm >/dev/null 2>&1 || { error "helm not installed. Install from: https://helm.sh/docs/intro/install/"; exit 1; }
    command -v docker >/dev/null 2>&1 || { error "docker not installed. Install from: https://docs.docker.com/get-docker/"; exit 1; }

    log "✅ Pre-flight checks passed!"
}

################################################################################
# Display Deployment Plan
################################################################################

show_deployment_plan() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Brand.Me Production Deployment Plan               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "📍 GCP Project: $GCP_PROJECT_ID"
    echo "📍 Region: $GCP_REGION"
    echo "📍 Domain: ${DOMAIN_NAME:-[IP-based, no custom domain]}"
    echo ""
    echo "🏗️  Infrastructure:"
    echo "   - GKE Cluster (3 nodes, n1-standard-2)"
    echo "   - Cloud SQL PostgreSQL 15"
    echo "   - Neo4j (deployed on GKE)"
    echo "   - NATS JetStream"
    echo "   - Load Balancer + Ingress"
    echo ""
    echo "🚀 Services to Deploy:"
    echo "   1. brandme-gateway (API Gateway)"
    echo "   2. brandme-chain (Blockchain Integration)"
    echo "   3. brandme-core (Brain, Policy, Orchestrator)"
    echo "   4. brandme-agents (Identity, Knowledge, Compliance)"
    echo "   5. brandme-console (Frontend)"
    echo "   6. brandme-agentic (AI Agents)"
    echo ""
    echo "💰 Estimated Monthly Cost: ~\$295"
    echo "   - GCP Infrastructure: ~\$225"
    echo "   - API Usage: ~\$70"
    echo ""
    echo "⏱️  Estimated Time: ~90 minutes"
    echo ""
    read -p "Continue with deployment? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        warn "Deployment cancelled by user"
        exit 0
    fi
}

################################################################################
# Execute Deployment Agents
################################################################################

run_agent() {
    local agent_name=$1
    local agent_script=$2

    log "🤖 Starting $agent_name..."

    if [ ! -f "$agent_script" ]; then
        error "Agent script not found: $agent_script"
        return 1
    fi

    chmod +x "$agent_script"

    if bash "$agent_script"; then
        log "✅ $agent_name completed successfully"
        return 0
    else
        error "❌ $agent_name failed"
        return 1
    fi
}

################################################################################
# Main Deployment Flow
################################################################################

main() {
    clear
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║            🚀 Brand.Me One-Click Deployment 🚀              ║"
    echo "║                                                              ║"
    echo "║         Deploy Complete AI-Native Platform in 90 mins       ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    # Pre-flight
    preflight_checks
    show_deployment_plan

    # Start deployment
    START_TIME=$(date +%s)
    log "🚀 Starting deployment at $(date)"

    # Phase 1: Infrastructure (20 mins)
    run_agent "Infrastructure Agent" "agents/infrastructure-agent.sh" || exit 1

    # Phase 2: Database Setup (10 mins)
    run_agent "Database Agent" "agents/database-agent.sh" || exit 1

    # Phase 3: Service Deployment (15 mins)
    run_agent "Service Agent" "agents/service-agent.sh" || exit 1

    # Phase 4: Integration (10 mins)
    run_agent "Integration Agent" "agents/integration-agent.sh" || exit 1

    # Phase 5: Test Data (15 mins)
    run_agent "Data Agent" "agents/data-agent.sh" || exit 1

    # Phase 6: Testing (20 mins)
    run_agent "Testing Agent" "agents/testing-agent.sh" || exit 1

    # Phase 7: Validation (5 mins)
    run_agent "Validation Agent" "agents/validation-agent.sh" || exit 1

    # Complete
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    MINUTES=$((DURATION / 60))

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║              ✅ DEPLOYMENT SUCCESSFUL! ✅                    ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    log "🎉 Deployment completed in $MINUTES minutes"

    # Show access information
    source agents/lib/show-access-info.sh
    show_access_info

    log "📝 Full deployment log saved to: $LOG_FILE"
}

# Handle interruption
trap 'error "Deployment interrupted! Check $LOG_FILE for details"; exit 1' INT TERM

# Run main
main "$@"
