# Brand.Me Cube Service

**Port:** 8007
**Architecture:** Brand.Me v6 Integrity Spine
**Language:** Python / FastAPI

## Overview

cube-service is the Product Cube storage and serving layer for Brand.Me. It stores all 6 faces of a Product Cube and enforces the Integrity Spine (Policy → Compliance → Governance → Blockchain) for every face access.

## Architecture

### The Integrity Spine

```
User Request → cube-service → policy (allow/escalate/deny) →
  → compliance (audit) → governance (human if escalated) →
  → orchestrator (persist) → blockchain (Cardano + Midnight)
```

### Service Integrations

- **policy (8001)**: Access decisions for faces
- **compliance (8004)**: Audit logging and escalations
- **orchestrator (8002)**: Workflow coordination and blockchain anchoring
- **identity (8005)**: User context for policy decisions
- **knowledge (8003)**: Public-safe garment data

## API Endpoints

### Cube Operations

- `GET /cubes/{cubeId}` - Get full cube (policy-filtered)
- `GET /cubes/{cubeId}/faces/{faceName}` - Get single face
- `POST /cubes` - Create new cube
- `POST /cubes/{cubeId}/transferOwnership` - Transfer ownership
- `GET /cubes/search` - Search cubes

### Health & Metrics

- `GET /health` - Detailed health check
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe
- `GET /metrics` - Prometheus metrics

## Face States

cube-service returns faces in three possible states:

1. **visible**: Policy allowed, data returned
2. **escalated_pending_human**: Policy escalated, awaiting governance approval
3. **denied**: Policy denied, HTTP 403

## Development

### Local Setup

```bash
cd brandme-cube
pip install -r requirements.txt
```

### Environment Variables

```bash
DATABASE_URL=postgresql://brandme:password@localhost:5432/brandme
REDIS_URL=redis://localhost:6379
POLICY_URL=http://localhost:8001
COMPLIANCE_URL=http://localhost:8004
ORCHESTRATOR_URL=http://localhost:8002
IDENTITY_URL=http://localhost:8005
```

### Run Service

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8007 --reload
```

### Testing

```bash
pytest tests/
```

## Critical Patterns (v6 Standards)

1. ✅ **X-Request-Id propagation**: All service calls include request ID
2. ✅ **PII redaction**: Use `redact_user_id()` for all user IDs in logs
3. ✅ **Policy-first**: NEVER return face without policy check
4. ✅ **Compliance logging**: Log every face access attempt
5. ✅ **Hash-chained audit**: All audit logs cryptographically linked
6. ✅ **CORS enabled**: Public-facing service
7. ✅ **Health checks**: Kubernetes-ready probes
8. ✅ **Metrics export**: Prometheus integration
9. ✅ **OpenTelemetry tracing**: Distributed traces

## Security

- JWT authentication on all endpoints
- Rate limiting per-user
- No PII in logs
- Encryption at rest (PostgreSQL)
- TLS in transit (service-to-service)

## Monitoring

### Metrics

- `cube_face_requests_total` - Face access requests
- `cube_policy_decisions_total` - Policy decisions (allow/escalate/deny)
- `cube_escalations_total` - Escalation count
- `cube_ownership_transfers_total` - Ownership transfers

### Logs

```bash
# View logs
docker logs brandme-cube

# Follow logs
docker logs -f brandme-cube
```

## Deployment

### Docker

```bash
docker-compose up cube
```

### Kubernetes

```bash
helm upgrade --install brandme ./infrastructure/helm/brandme
```
