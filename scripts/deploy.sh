#!/bin/bash
# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Brand.Me Deployment Script
# ===========================
#
# Usage:
#   ./scripts/deploy.sh [environment] [component]
#
# Examples:
#   ./scripts/deploy.sh development all
#   ./scripts/deploy.sh production gateway
#   ./scripts/deploy.sh staging core

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT="${1:-development}"
COMPONENT="${2:-all}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Brand.Me Deployment Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Environment: ${YELLOW}${ENVIRONMENT}${NC}"
echo -e "Component:   ${YELLOW}${COMPONENT}${NC}"
echo ""

# Load environment variables
ENV_FILE="${PROJECT_ROOT}/.env.${ENVIRONMENT}"
if [ -f "$ENV_FILE" ]; then
    echo -e "${GREEN}✓${NC} Loading environment from ${ENV_FILE}"
    set -a
    source "$ENV_FILE"
    set +a
else
    echo -e "${RED}✗${NC} Environment file not found: ${ENV_FILE}"
    exit 1
fi

# Function to check prerequisites
check_prerequisites() {
    echo -e "\n${YELLOW}Checking prerequisites...${NC}"

    local missing_tools=()

    if ! command -v docker &> /dev/null; then
        missing_tools+=("docker")
    fi

    if ! command -v docker-compose &> /dev/null; then
        missing_tools+=("docker-compose")
    fi

    if [ "$ENVIRONMENT" = "production" ] || [ "$ENVIRONMENT" = "staging" ]; then
        if ! command -v kubectl &> /dev/null; then
            missing_tools+=("kubectl")
        fi

        if ! command -v helm &> /dev/null; then
            missing_tools+=("helm")
        fi
    fi

    if [ ${#missing_tools[@]} -ne 0 ]; then
        echo -e "${RED}✗${NC} Missing required tools: ${missing_tools[*]}"
        exit 1
    fi

    echo -e "${GREEN}✓${NC} All prerequisites met"
}

# Function to run database migrations
run_migrations() {
    echo -e "\n${YELLOW}Running database migrations...${NC}"

    cd "${PROJECT_ROOT}/brandme-data"

    if [ -f "alembic.ini" ]; then
        alembic upgrade head
        echo -e "${GREEN}✓${NC} Database migrations completed"
    else
        echo -e "${YELLOW}⚠${NC}  No migrations found, skipping"
    fi

    cd "$PROJECT_ROOT"
}

# Function to build Docker images
build_images() {
    local component=$1
    echo -e "\n${YELLOW}Building Docker images for ${component}...${NC}"

    case $component in
        gateway)
            docker build -t brandme/gateway:latest ./brandme-gateway
            ;;
        core)
            docker build -t brandme/core:latest ./brandme-core
            ;;
        agents)
            docker build -t brandme/agents:latest ./brandme-agents
            ;;
        chain)
            docker build -t brandme/chain:latest ./brandme-chain
            ;;
        console)
            docker build -t brandme/console:latest ./brandme-console
            ;;
        all)
            docker build -t brandme/gateway:latest ./brandme-gateway &
            docker build -t brandme/core:latest ./brandme-core &
            docker build -t brandme/agents:latest ./brandme-agents &
            docker build -t brandme/chain:latest ./brandme-chain &
            docker build -t brandme/console:latest ./brandme-console &
            wait
            ;;
        *)
            echo -e "${RED}✗${NC} Unknown component: ${component}"
            exit 1
            ;;
    esac

    echo -e "${GREEN}✓${NC} Docker images built successfully"
}

# Function to deploy with docker-compose (development)
deploy_docker_compose() {
    echo -e "\n${YELLOW}Deploying with docker-compose...${NC}"

    docker-compose -f docker-compose.yml down
    docker-compose -f docker-compose.yml up -d

    echo -e "${GREEN}✓${NC} Services deployed with docker-compose"
    echo -e "\nService URLs:"
    echo -e "  Gateway:    ${GREEN}http://localhost:3000${NC}"
    echo -e "  Console:    ${GREEN}http://localhost:3002${NC}"
    echo -e "  Prometheus: ${GREEN}http://localhost:9090${NC}"
    echo -e "  Grafana:    ${GREEN}http://localhost:3030${NC}"
}

# Function to deploy to Kubernetes (production/staging)
deploy_kubernetes() {
    echo -e "\n${YELLOW}Deploying to Kubernetes...${NC}"

    # Create namespace if it doesn't exist
    kubectl create namespace brandme --dry-run=client -o yaml | kubectl apply -f -

    # Deploy with Helm
    helm upgrade --install brandme \
        ./infrastructure/helm/brandme \
        --namespace brandme \
        --values ./infrastructure/helm/brandme/values.yaml \
        --set global.environment="${ENVIRONMENT}" \
        --wait \
        --timeout 10m

    echo -e "${GREEN}✓${NC} Deployed to Kubernetes"

    # Show deployment status
    kubectl get pods -n brandme
}

# Function to run health checks
run_health_checks() {
    echo -e "\n${YELLOW}Running health checks...${NC}"

    local services=("gateway:3000" "brain:8000" "policy:8001")
    local failed=0

    for service in "${services[@]}"; do
        local name="${service%%:*}"
        local port="${service##*:}"

        if curl -f "http://localhost:${port}/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} ${name} is healthy"
        else
            echo -e "${RED}✗${NC} ${name} is unhealthy"
            ((failed++))
        fi
    done

    if [ $failed -eq 0 ]; then
        echo -e "\n${GREEN}✓${NC} All health checks passed"
        return 0
    else
        echo -e "\n${RED}✗${NC} ${failed} health check(s) failed"
        return 1
    fi
}

# Function to tail logs
tail_logs() {
    local component=$1
    echo -e "\n${YELLOW}Tailing logs for ${component}...${NC}"

    if [ "$ENVIRONMENT" = "development" ]; then
        docker-compose logs -f "$component"
    else
        kubectl logs -f -n brandme -l "app.kubernetes.io/name=${component}"
    fi
}

# Main deployment flow
main() {
    check_prerequisites

    if [ "$ENVIRONMENT" = "development" ]; then
        build_images "$COMPONENT"
        run_migrations
        deploy_docker_compose
        sleep 10  # Wait for services to start
        run_health_checks || echo -e "${YELLOW}⚠${NC}  Some services are not healthy yet"
    else
        build_images "$COMPONENT"

        # Tag and push images to registry
        echo -e "\n${YELLOW}Pushing images to registry...${NC}"
        # TODO: Add your container registry here
        # docker tag brandme/gateway:latest gcr.io/brandme-prod/gateway:latest
        # docker push gcr.io/brandme-prod/gateway:latest

        run_migrations
        deploy_kubernetes
        run_health_checks
    fi

    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}Deployment Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
}

# Parse additional flags
case "${3:-}" in
    --logs)
        tail_logs "$COMPONENT"
        exit 0
        ;;
    --health)
        run_health_checks
        exit $?
        ;;
    --migrate)
        run_migrations
        exit 0
        ;;
esac

# Run main deployment
main
