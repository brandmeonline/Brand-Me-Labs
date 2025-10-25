#!/bin/bash
################################################################################
# Service Deployment Agent
# Builds and deploys all Brand.Me services
################################################################################

set -e
source .env.deploy
source agents/lib/common.sh
source .deployment/infrastructure.env
source .deployment/database.env

log_agent "Service Agent" "Starting service deployment..."

SERVICES=(
    "brandme-gateway"
    "brandme-chain"
    "brandme-core"
    "brandme-agents"
    "brandme-console"
)

# ============================================================================
# Build and Push Docker Images
# ============================================================================

log_step "Building Docker images..."

# Configure Docker for GCR
gcloud auth configure-docker --quiet

for service in "${SERVICES[@]}"; do
    log_info "Building $service..."

    cd "$service"

    IMAGE_TAG="gcr.io/$GCP_PROJECT_ID/$service:latest"

    docker build -t "$IMAGE_TAG" .
    docker push "$IMAGE_TAG"

    cd ..
done

# ============================================================================
# Create Kubernetes Secrets
# ============================================================================

log_step "Creating Kubernetes secrets..."

kubectl create namespace brandme || true

# Create secret with all credentials
kubectl create secret generic brandme-secrets \
    --from-literal=anthropic-api-key="$ANTHROPIC_API_KEY" \
    --from-literal=openai-api-key="$OPENAI_API_KEY" \
    --from-literal=blockfrost-api-key="$BLOCKFROST_API_KEY" \
    --from-literal=db-password="$DB_PASSWORD" \
    --from-literal=neo4j-password="$NEO4J_PASSWORD" \
    --namespace=brandme \
    --dry-run=client -o yaml | kubectl apply -f -

# ============================================================================
# Deploy Services via Helm
# ============================================================================

log_step "Deploying services with Helm..."

cd brandme-infra/helm

# Update values with actual configuration
cat > values-prod.yaml <<EOF
global:
  project_id: $GCP_PROJECT_ID
  region: $GCP_REGION
  environment: production

database:
  host: $DB_HOST
  port: 5432
  name: $DB_NAME
  user: $DB_USER

neo4j:
  uri: $NEO4J_URI
  user: $NEO4J_USER

nats:
  url: $NATS_URL

redis:
  url: $REDIS_URL

blockchain:
  cardano_network: $CARDANO_NETWORK
  fallback_mode: false

images:
  gateway: gcr.io/$GCP_PROJECT_ID/brandme-gateway:latest
  chain: gcr.io/$GCP_PROJECT_ID/brandme-chain:latest
  core: gcr.io/$GCP_PROJECT_ID/brandme-core:latest
  agents: gcr.io/$GCP_PROJECT_ID/brandme-agents:latest
  console: gcr.io/$GCP_PROJECT_ID/brandme-console:latest

ingress:
  enabled: true
  domain: ${DOMAIN_NAME:-}
  ssl_mode: ${SSL_MODE:-auto}

autoscaling:
  enabled: ${ENABLE_AUTOSCALING:-true}
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
EOF

# Deploy umbrella chart
helm upgrade --install brandme ./brandme-umbrella \
    --namespace brandme \
    --values values-prod.yaml \
    --create-namespace \
    --wait \
    --timeout 10m

cd ../..

# ============================================================================
# Wait for Services to be Ready
# ============================================================================

log_step "Waiting for services to be ready..."

DEPLOYMENTS=(
    "brandme-gateway"
    "brandme-chain"
    "brandme-console"
)

for deployment in "${DEPLOYMENTS[@]}"; do
    log_info "Waiting for $deployment..."
    kubectl rollout status deployment/"$deployment" -n brandme --timeout=5m
done

# Get ingress IP
log_step "Getting load balancer IP..."
INGRESS_IP=$(kubectl get svc -n brandme brandme-ingress -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Wait for IP to be assigned
while [ -z "$INGRESS_IP" ]; do
    sleep 5
    INGRESS_IP=$(kubectl get svc -n brandme brandme-ingress -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
done

# Save service URLs
cat > .deployment/services.env <<EOF
INGRESS_IP=$INGRESS_IP
GATEWAY_URL=http://$INGRESS_IP
CONSOLE_URL=http://$INGRESS_IP:3002
NEO4J_BROWSER_URL=http://$NEO4J_HOST:7474
EOF

log_agent "Service Agent" "✅ Service deployment complete!"
