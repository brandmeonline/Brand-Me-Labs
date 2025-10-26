# Brand.Me Infrastructure Guide

## Overview

Complete infrastructure setup for the Brand.Me platform, including containerization, observability, deployment automation, and operations tooling.

## 📦 Components Created

### 1. Orchestration & Task Queue

**Celery Worker System** (`brandme-core/orchestrator/`)
- ✅ `celery_app.py` - Celery configuration with queue routing
- ✅ `tasks.py` - Async tasks for scan processing, blockchain integration, audit logging
- Features:
  - Persistent scan events to database
  - Fetch filtered facets from knowledge service
  - Submit blockchain transactions (Cardano/Midnight)
  - Hash-chained audit log entries
  - Notification system
  - Periodic tasks (cleanup, integrity verification, blockchain sync)
  - Workflow orchestration with chains and groups

**Queues Configured:**
- `default` - General purpose tasks
- `scans` - Scan processing workflow
- `blockchain` - Transaction submission
- `audit` - Compliance logging
- `notifications` - User notifications
- `priority` - High-priority tasks

### 2. Observability Stack

**OpenTelemetry Integration** (`brandme_core/telemetry.py`)
- Distributed tracing with OTLP export
- Automatic instrumentation for FastAPI, httpx, asyncpg, Redis
- Prometheus metrics export
- Custom metrics: scans, blockchain TXs, audit entries, durations
- Context propagation across services

**Prometheus Monitoring** (`infrastructure/prometheus/`)
- Service discovery for all microservices
- Exporters: PostgreSQL, Redis, NATS, Celery, Node, cAdvisor
- Alert rules (`rules/alerts.yml`):
  - Service health (downtime, error rates, latency)
  - Database (connection pool, slow queries)
  - Blockchain (TX failures)
  - Audit (integrity violations, escalations)
  - Infrastructure (CPU, memory, disk)

**Grafana Dashboards** (`infrastructure/grafana/`)
- Overview dashboard with:
  - Scan request rate
  - Error rates (gauge visualization)
  - Duration percentiles (p50, p95, p99)
  - Blockchain transaction rates
  - Service health status grid

**Loki Log Aggregation** (`infrastructure/loki/`)
- 7-day retention
- BoltDB shipper with filesystem storage
- Automatic compaction
- Integration with Grafana

**Tempo Distributed Tracing**
- OTLP trace ingestion
- Correlation with logs via trace IDs

**OpenTelemetry Collector** (`infrastructure/otel-collector/`)
- OTLP receiver (gRPC + HTTP)
- PII filtering processor
- Batch processing for performance
- Export to Prometheus, Loki, Tempo

### 3. Containerization

**Dockerfiles Created:**

`brandme-core/Dockerfile`
- Multi-stage build for Python services
- Targets: brain, policy, orchestrator, orchestrator-beat
- Non-root user (brandme:1000)
- Health checks configured
- Hot-reload support for development

`brandme-agents/Dockerfile`
- Targets: identity, knowledge, compliance, agentic
- Shared brandme_core module
- Individual service ports (8100-8102, 8200)

`brandme-chain/Dockerfile`
- Node.js 18 Alpine
- pnpm package manager
- TypeScript compilation
- Production & development targets

`brandme-console/Dockerfile`
- Next.js optimized build
- Standalone output for minimal image size
- Static assets separation
- Development hot-reload

### 4. Docker Compose

**docker-compose.yml** - Full production-ready stack:

**Infrastructure:**
- PostgreSQL 15 with auto-initialized schemas
- Redis 7 with persistence & custom config
- NATS JetStream with monitoring

**Observability:**
- Prometheus + Alertmanager
- Grafana with provisioned dashboards
- Loki log aggregation
- Tempo tracing
- OpenTelemetry Collector
- Exporters: PostgreSQL, Redis, Node, cAdvisor

**Services:**
- Gateway (load balanced, 3 replicas in prod)
- Brain (intent resolver)
- Policy (consent & compliance)
- Orchestrator Worker (4 concurrency)
- Orchestrator Beat (scheduler)
- Identity, Knowledge, Compliance agents
- Chain (blockchain integration)
- Console (Next.js frontend)

**Networks:**
- `brandme` bridge network for service communication

**Volumes:**
- Persistent storage for databases, metrics, logs

### 5. Environment Configuration

**.env.development**
- Local development settings
- Debug logging
- Insecure defaults for rapid iteration
- Feature flags for testing

**.env.staging**
- Pre-production testing
- Testnet blockchain
- Real authentication
- Monitoring enabled

**.env.production**
- Production-ready configuration
- Secrets placeholders (use secrets manager)
- Mainnet blockchain
- Full observability
- Backup automation
- Compliance settings (GDPR, CCPA)

### 6. Kubernetes Deployment

**Helm Chart** (`infrastructure/helm/brandme/`)

`Chart.yaml`
- Platform chart definition
- Dependencies: PostgreSQL, Redis, Prometheus, Grafana

`values.yaml` - Production configuration:
- **Gateway**: 3 replicas, autoscaling 3-10, LoadBalancer with TLS
- **Brain**: 2 replicas, autoscaling 2-8, 512Mi-1Gi memory
- **Policy**: 2 replicas, autoscaling 2-6
- **Agents**: Identity, Knowledge, Compliance (2 replicas each)
- **Chain**: 2 replicas for HA
- **Orchestrator**: 4 workers + 1 beat scheduler
- **PostgreSQL**: 100Gi SSD, metrics enabled
- **Redis**: 20Gi persistence, monitoring
- **NATS**: 3 replicas, JetStream with 10Gi file store
- **Ingress**: nginx with cert-manager (Let's Encrypt)
- **Monitoring**: Prometheus 50Gi retention, Grafana dashboards
- **Security**: Network policies, pod security policies, mTLS option

`namespace.yaml`
- Namespaces: `brandme`, `brandme-staging`, `observability`

### 7. Health Checks

**`brandme_core/health.py`** - Standardized health check system:

**Endpoints:**
- `/health` - Detailed health with all dependencies
- `/health/live` - Kubernetes liveness probe
- `/health/ready` - Kubernetes readiness probe
- `/health/startup` - Kubernetes startup probe
- `/healthz` - Simple 200 OK probe

**Dependency Checks:**
- PostgreSQL (connection pool status)
- Redis (ping + stats)
- NATS (connection state)
- Custom application checks (extensible)

**Features:**
- Graceful degradation (degraded vs unhealthy)
- Uptime tracking
- Pool utilization metrics
- Automatic integration with FastAPI

### 8. Database Migrations

**Alembic Configuration** (`brandme-data/`)

`alembic.ini`
- Migration script location
- File naming templates
- Logging configuration
- Post-write hooks (code formatting)

`migrations/env.py`
- Async migration support
- Environment variable override for DATABASE_URL
- Offline and online migration modes

**Usage:**
```bash
# Initialize
alembic init migrations

# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### 9. Operations Scripts

**`scripts/deploy.sh`** - Full deployment automation:
- Environment selection (dev/staging/prod)
- Component-specific or full deployment
- Prerequisites validation
- Database migrations
- Docker Compose deployment (development)
- Kubernetes/Helm deployment (production)
- Health check verification
- Log tailing support

**Usage:**
```bash
./scripts/deploy.sh development all
./scripts/deploy.sh production gateway
./scripts/deploy.sh staging all --logs
```

**`scripts/db-init.sh`** - Database initialization:
- Wait for database readiness
- Create database if missing
- Install PostgreSQL extensions (uuid-ossp, pgcrypto)
- Apply all schemas in order
- Load seed data
- Verification checks

**`scripts/test-infrastructure.sh`** - Comprehensive testing:
- **Database Tests**: PostgreSQL connection, version
- **Cache Tests**: Redis ping, set/get operations
- **Messaging Tests**: NATS health, JetStream enabled
- **Service Tests**: Health endpoints for all 7 services
- **Observability Tests**: Prometheus, Grafana, Loki, OTEL
- **Container Tests**: Running status, restart loops
- **Network Tests**: Service-to-service connectivity
- **Metrics Tests**: All exporters responding
- **Schema Tests**: All 7 tables exist
- **Orchestrator Tests**: Celery workers active

**`scripts/backup.sh`** - Database backup automation:
- Compressed SQL dumps
- Configurable retention (default 30 days)
- Cloud storage upload support
- Automated cleanup

### 10. Redis Configuration

**`infrastructure/redis/redis.conf`**
- 2GB memory limit with LRU eviction
- AOF + RDB persistence
- Security: password auth, disabled dangerous commands
- Slow log monitoring
- Event notifications
- Performance tuning (hz=10, lazy freeing)

### 11. Infrastructure Configurations

**Prometheus (`infrastructure/prometheus/prometheus.yml`)**
- 15s scrape interval
- 12 job configurations
- Alertmanager integration
- Service labels (service, tier)

**Alert Rules (`infrastructure/prometheus/rules/alerts.yml`)**
- 6 rule groups covering:
  - Service health (downtime, errors, latency)
  - Database performance
  - Blockchain failures
  - Audit integrity violations
  - Celery queue backlogs
  - Infrastructure resources
  - Redis memory

**Loki (`infrastructure/loki/loki-config.yml`)**
- BoltDB shipper with filesystem backend
- 7-day retention
- 10MB/s ingestion rate
- Ruler for alerting
- Compaction enabled

**OpenTelemetry Collector (`infrastructure/otel-collector/otel-collector-config.yml`)**
- OTLP receiver on 4317 (gRPC) and 4318 (HTTP)
- Batch processor (1024 batch size)
- Memory limiter (512MiB)
- PII filter processor
- Resource enrichment
- Export to Prometheus, Loki, Tempo
- Health check on port 13133

**Grafana Dashboard** (`infrastructure/grafana/dashboards/brandme-overview.json`)
- Scan request rate (time series)
- Error rate (gauge)
- Duration percentiles (p50/p95/p99)
- Blockchain TX rate (success/failed)
- Service health status (stat panels)
- 30s auto-refresh
- UTC timezone

## 🚀 Quick Start

### Development

```bash
# 1. Initialize database
./scripts/db-init.sh

# 2. Deploy full stack
./scripts/deploy.sh development all

# 3. Wait for services to start (30-60 seconds)
sleep 30

# 4. Run infrastructure tests
./scripts/test-infrastructure.sh

# 5. Access services
open http://localhost:3000  # Gateway API
open http://localhost:3002  # Console UI
open http://localhost:9090  # Prometheus
open http://localhost:3030  # Grafana (admin/admin)
```

### Production

```bash
# 1. Set production secrets
export DATABASE_URL="postgresql://..."
export REDIS_PASSWORD="..."
export JWT_SECRET="..."

# 2. Deploy to Kubernetes
./scripts/deploy.sh production all

# 3. Verify deployment
kubectl get pods -n brandme
kubectl get ingress -n brandme

# 4. Monitor
open https://grafana.brandme.io
```

## 📊 Monitoring

### Dashboards

**Grafana - Brand.Me Overview**
- Real-time scan metrics
- Error rates and latencies
- Blockchain transaction status
- Service health matrix

### Alerts

**Critical Alerts** (PagerDuty):
- Service down > 1 minute
- Audit chain integrity violation
- Database pool exhausted
- All Celery workers down

**Warning Alerts** (Slack):
- High error rate (> 10%)
- Slow response time (> 2s p95)
- Blockchain TX failures (> 10%)
- High escalation rate (> 5%)

### Logs

**Loki Query Examples:**
```logql
# All errors
{service="brain"} |= "ERROR"

# Scan processing
{service="orchestrator"} | json | task="persist_scan_event"

# Audit violations
{service="compliance"} | json | integrity_valid="false"
```

### Traces

**Tempo - Example Queries:**
- Service: `brain`
- Operation: `/intent/resolve`
- Filter by duration > 1s
- Correlation to logs via trace_id

## 🔐 Security

### Secrets Management

**Development:**
- Use `.env.development` with insecure defaults
- NOT for production use

**Production:**
- **Never** commit secrets to git
- Use external secrets manager:
  - AWS Secrets Manager
  - Google Secret Manager
  - HashiCorp Vault
  - Kubernetes Secrets with encryption at rest

**Kubernetes Example:**
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: brandme-secrets
spec:
  backend: gcpSecretsManager
  data:
    - key: brandme-db-password
      name: DB_PASSWORD
```

### Network Security

**Service Mesh (Optional):**
- Istio for mTLS between services
- Automatic certificate rotation
- Traffic encryption in transit

**Network Policies:**
- Deny all by default
- Explicit allow rules for service communication
- Egress control to external APIs

## 📈 Performance

### Resource Limits

**Development:**
- Brain: 512Mi memory, 500m CPU
- Gateway: 512Mi memory, 500m CPU
- PostgreSQL: 2Gi memory, 1 CPU

**Production:**
- Brain: 1Gi memory, 1 CPU (autoscale to 8 replicas)
- Gateway: 512Mi memory, 500m CPU (autoscale to 10 replicas)
- PostgreSQL: 4Gi memory, 2 CPU
- Redis: 2Gi memory, 1 CPU

### Caching Strategy

**Redis Caches:**
- Scan results: 1 hour TTL
- User sessions: 24 hours TTL
- Policy decisions: 5 minutes TTL
- Garment metadata: 1 hour TTL

### Database Optimization

**Indexes Created:**
- All foreign keys
- Frequently queried fields (garment_id, scanner_user_id, region_code)
- GIN index on JSONB columns
- Composite indexes for common queries

## 🔄 CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build and push Docker images
        run: |
          docker build -t gcr.io/brandme/gateway:${{ github.sha }} ./brandme-gateway
          docker push gcr.io/brandme/gateway:${{ github.sha }}

      - name: Deploy to Kubernetes
        run: |
          helm upgrade --install brandme ./infrastructure/helm/brandme \
            --set gateway.image.tag=${{ github.sha }}

      - name: Run smoke tests
        run: ./scripts/test-infrastructure.sh
```

## 📚 Additional Resources

### Documentation
- [Prometheus Docs](https://prometheus.io/docs/)
- [Grafana Docs](https://grafana.com/docs/)
- [OpenTelemetry Docs](https://opentelemetry.io/docs/)
- [Celery Docs](https://docs.celeryproject.org/)
- [Helm Docs](https://helm.sh/docs/)

### Runbooks
- **Service Down**: Check logs, restart pod, verify dependencies
- **High Latency**: Check database slow queries, Redis memory, network
- **Audit Violation**: CRITICAL - investigate immediately, notify security team
- **Backup Failure**: Verify storage access, check disk space

## 🎯 Next Steps

**Immediate:**
1. ✅ Run `./scripts/deploy.sh development all`
2. ✅ Verify all services healthy
3. ✅ Access Grafana dashboards
4. ✅ Test scan workflow end-to-end

**Week 1:**
- Replace database stubs with real queries
- Integrate NATS consumers
- Implement knowledge service endpoints
- Set up staging environment

**Week 2:**
- Production secrets configuration
- Load testing
- Disaster recovery testing
- Security audit

**Production Readiness:**
- [ ] All health checks passing
- [ ] Observability stack operational
- [ ] Backup/restore tested
- [ ] Runbooks documented
- [ ] On-call rotation established
- [ ] SLA/SLO defined
