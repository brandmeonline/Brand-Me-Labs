#!/bin/bash
################################################################################
# Database Setup Agent
# Sets up PostgreSQL, Neo4j, NATS, and runs migrations
################################################################################

set -e
source .env.deploy
source agents/lib/common.sh
source .deployment/infrastructure.env

log_agent "Database Agent" "Starting database setup..."

# ============================================================================
# PostgreSQL Setup
# ============================================================================

log_step "Connecting to Cloud SQL PostgreSQL..."

# Get Cloud SQL connection name
SQL_CONNECTION=$(gcloud sql instances list --format="value(connectionName)" --filter="name:brandme-db")

# Create databases
log_step "Creating databases..."
gcloud sql databases create brandme --instance=brandme-db || true

# Create user
DB_PASSWORD=$(openssl rand -base64 32)
gcloud sql users create brandme \
    --instance=brandme-db \
    --password="$DB_PASSWORD" || true

# Run migrations
log_step "Running PostgreSQL migrations..."
cd brandme-data

# Use Cloud SQL Proxy for secure connection
cloud_sql_proxy -instances="$SQL_CONNECTION"=tcp:5432 &
PROXY_PID=$!
sleep 5

# Run migrations
DATABASE_URL="postgresql://brandme:$DB_PASSWORD@localhost:5432/brandme" python manage.py migrate

# Seed data
if [ "$GENERATE_TEST_DATA" = "true" ]; then
    log_step "Seeding database..."
    DATABASE_URL="postgresql://brandme:$DB_PASSWORD@localhost:5432/brandme" python manage.py seed
fi

kill $PROXY_PID
cd ..

# ============================================================================
# Neo4j Setup
# ============================================================================

log_step "Deploying Neo4j to Kubernetes..."

# Create namespace
kubectl create namespace brandme || true

# Deploy Neo4j
NEO4J_PASSWORD=$(openssl rand -base64 32)

helm repo add neo4j https://helm.neo4j.com/neo4j
helm repo update

helm install neo4j neo4j/neo4j \
    --namespace brandme \
    --set neo4j.password="$NEO4J_PASSWORD" \
    --set neo4j.edition=enterprise \
    --set neo4j.acceptLicenseAgreement=yes \
    --set volumes.data.mode=defaultStorageClass \
    --set services.neo4j.enabled=true \
    --set services.bolt.enabled=true

# Wait for Neo4j to be ready
log_step "Waiting for Neo4j to be ready..."
kubectl wait --for=condition=ready pod -l app=neo4j --timeout=300s -n brandme

# Get Neo4j service
NEO4J_HOST=$(kubectl get svc neo4j -n brandme -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# ============================================================================
# NATS JetStream Setup
# ============================================================================

log_step "Deploying NATS JetStream..."

helm repo add nats https://nats-io.github.io/k8s/helm/charts/
helm repo update

helm install nats nats/nats \
    --namespace brandme \
    --set nats.jetstream.enabled=true \
    --set nats.jetstream.memStorage.enabled=true \
    --set nats.jetstream.fileStorage.enabled=true \
    --set nats.jetstream.fileStorage.size=10Gi

# Wait for NATS
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=nats --timeout=300s -n brandme

# ============================================================================
# Redis Setup (for Celery)
# ============================================================================

log_step "Deploying Redis..."

helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

helm install redis bitnami/redis \
    --namespace brandme \
    --set auth.enabled=false

# Wait for Redis
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=redis --timeout=300s -n brandme

# ============================================================================
# Save Configuration
# ============================================================================

cat > .deployment/database.env <<EOF
DB_HOST=$DB_IP
DB_USER=brandme
DB_PASSWORD=$DB_PASSWORD
DB_NAME=brandme
NEO4J_URI=bolt://$NEO4J_HOST:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=$NEO4J_PASSWORD
NATS_URL=nats://nats.brandme.svc.cluster.local:4222
REDIS_URL=redis://redis-master.brandme.svc.cluster.local:6379
EOF

log_agent "Database Agent" "✅ Database setup complete!"
