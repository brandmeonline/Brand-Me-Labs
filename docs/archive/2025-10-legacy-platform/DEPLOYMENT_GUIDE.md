# Brand.Me - Deployment Guide

**Copyright (c) Brand.Me, Inc. All rights reserved.**

---

## Table of Contents
1. [Local Development](#local-development)
2. [Docker Compose](#docker-compose)
3. [Kubernetes Deployment](#kubernetes-deployment)
4. [Environment Configuration](#environment-configuration)
5. [Health Verification](#health-verification)

---

## Local Development

### Prerequisites

```bash
# Required
- Docker and Docker Compose
- Node.js 18+
- Python 3.11+
- PostgreSQL 15+
- pnpm 8+

# Optional
- kubectl
- helm 3.13+
- terraform 1.5+
```

### Quick Start

```bash
# Clone repository
git clone https://github.com/brandme-labs/Brand-Me-Labs.git
cd Brand-Me-Labs

# Install dependencies
make install

# Start all services
make dev-up
# OR
docker-compose up -d

# Run migrations
make db-migrate

# Seed data
make db-seed

# Verify health
for port in 8000 8001 8002 8003 8004 8005 8006; do
  curl http://localhost:$port/health
done
```

### Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Gateway | http://localhost:3000 | API Gateway |
| Brain | http://localhost:8000 | Intent resolver |
| Policy | http://localhost:8001 | Policy decisions |
| Orchestrator | http://localhost:8002 | Scan processing |
| Knowledge | http://localhost:8003 | Facet retrieval |
| Compliance | http://localhost:8004 | Audit logging |
| Identity | http://localhost:8005 | User profiles |
| Governance | http://localhost:8006 | Human review |
| Chain | http://localhost:3001 | Blockchain TX |
| Console | http://localhost:3002 | Web UI |

---

## Docker Compose

### Production Compose

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: brandme
      POSTGRES_USER: brandme
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
  
  brain:
    build: ./brandme-core/brain
    environment:
      DATABASE_URL: postgresql://brandme:${POSTGRES_PASSWORD}@postgres:5432/brandme
      REGION_DEFAULT: us-east1
    ports:
      - "8000:8000"
    depends_on:
      - postgres
  
  # ... other services
```

### Development Compose

```bash
docker-compose -f docker-compose.dev.yml up -d
```

---

## Kubernetes Deployment

### Prerequisites

```bash
# GCP CLI
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# kubectl
gcloud container clusters get-credentials brandme-cluster --region us-east1

# helm
helm version
```

### Deployment Steps

```bash
# 1. Apply Terraform
cd brandme-infra/terraform
terraform init
terraform plan
terraform apply

# 2. Deploy with Helm
cd ../helm
helm upgrade --install brandme ./brandme-umbrella \
  --values values.yaml \
  --namespace brandme \
  --create-namespace \
  --wait

# 3. Verify deployment
kubectl get pods -n brandme
kubectl get services -n brandme
kubectl get ingress -n brandme
```

### Helm Values

```yaml
# values.yaml
global:
  imageRegistry: gcr.io/brandme-prod
  imageTag: latest
  environment: production
  
gateway:
  replicas: 3
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: 2000m
      memory: 2Gi
  
core:
  brain:
    replicas: 2
    resources:
      requests:
        cpu: 200m
        memory: 256Mi
  policy:
    replicas: 2
  orchestrator:
    replicas: 2
```

---

## Environment Configuration

### Required Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/brandme

# Region
REGION_DEFAULT=us-east1

# CORS
CORS_ORIGINS=https://brand.me,https://console.brand.me
```

### Optional Variables

```bash
# Service URLs (defaults provided)
BRAIN_SERVICE_URL=http://brain:8000
POLICY_SERVICE_URL=http://policy:8001
ORCHESTRATOR_SERVICE_URL=http://orchestrator:8002
KNOWLEDGE_SERVICE_URL=http://knowledge:8003
COMPLIANCE_SERVICE_URL=http://compliance:8004
IDENTITY_SERVICE_URL=http://identity:8005
GOVERNANCE_SERVICE_URL=http://governance_console:8006

# Observability
ENABLE_TRACING=true
OTLP_ENDPOINT=https://otel-collector:4317
LOG_LEVEL=INFO

# Gateway
OAUTH_CLIENT_ID=your_client_id
OAUTH_CLIENT_SECRET=your_client_secret
NATS_URL=nats://nats:4222
```

### Secrets Management

**Never commit secrets**. Use:
- Kubernetes secrets
- HashiCorp Vault
- AWS Secrets Manager
- GCP Secret Manager

```bash
# Create Kubernetes secret
kubectl create secret generic brandme-secrets \
  --from-literal=database-url='postgresql://...' \
  --from-literal=oauth-secret='...' \
  -n brandme
```

---

## Health Verification

### 1. Health Checks

```bash
# Check all services
for port in 8000 8001 8002 8003 8004 8005 8006; do
  echo "Checking port $port..."
  curl -s http://localhost:$port/health | jq
done
```

### 2. Metrics Verification

```bash
# Check metrics endpoint
curl http://localhost:8000/metrics | grep http_requests_total
```

### 3. Authentication Test

```bash
# Test authenticated endpoint
TOKEN="your_jwt_token"
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:3000/scan
```

### 4. Rate Limiting Test

```bash
# Should get 429 after rate limit exceeded
for i in {1..15}; do
  curl -H "Authorization: Bearer $TOKEN" \
    http://localhost:3000/scan
done
```

---

## Scaling

### Horizontal Pod Autoscaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: brandme-brain
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: brandme-brain
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## Disaster Recovery

### Backup Strategy

```bash
# Database backup
pg_dump $DATABASE_URL > backup.sql

# Persistent volume snapshots
gcloud compute disks snapshot brandme-pgdisk
```

### Restore

```bash
# Restore from backup
psql $DATABASE_URL < backup.sql
```

---

## Monitoring

### Prometheus Targets

All services automatically registered as Prometheus targets:

- `brain:8000/metrics`
- `policy:8001/metrics`
- `orchestrator:8002/metrics`
- `knowledge:8003/metrics`
- `compliance:8004/metrics`
- `identity:8005/metrics`
- `governance:8006/metrics`

### Grafana Access

```bash
# Port forward
kubectl port-forward svc/grafana 3000:3000 -n monitoring

# Access
open http://localhost:3000
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker logs brandme-brain
kubectl logs deployment/brandme-brain -n brandme

# Check events
kubectl describe pod brandme-brain -n brandme
```

### Database Connection Issues

```bash
# Verify DATABASE_URL
echo $DATABASE_URL

# Test connection
psql $DATABASE_URL -c "SELECT 1"
```

### Authentication Issues

```bash
# Verify JWT token
jwt decode $TOKEN

# Check token expiry
jwt decode $TOKEN | jq .exp
```

---

## Rollback Procedure

```bash
# Get previous revision
helm history brandme -n brandme

# Rollback
helm rollback brandme REVISION_NUMBER -n brandme

# Verify
kubectl rollout status deployment/brandme-gateway -n brandme
```

---

*Deployment Guide: Complete*  
*Local: ✅ Ready*  
*Docker: ✅ Ready*  
*Kubernetes: ✅ Ready*

