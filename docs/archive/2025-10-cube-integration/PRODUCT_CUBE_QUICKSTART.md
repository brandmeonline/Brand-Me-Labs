# Product Cube Service - Quick Start Guide

**Service:** brandme-cube
**Port:** 8007
**Status:** ✅ Operational

---

## 5-Minute Setup

### Prerequisites
- Docker and Docker Compose installed
- PostgreSQL running (via docker-compose)
- Port 8007 available

### Start the Service

```bash
# 1. Navigate to repository
cd Brand-Me-Labs

# 2. Initialize database schema
docker-compose up -d postgres
sleep 10
docker-compose exec postgres psql -U brandme -d brandme -f /docker-entrypoint-initdb.d/init.sql

# 3. Start all services
docker-compose up -d

# 4. Verify cube service is running
curl http://localhost:8007/health
# Expected: {"status":"ok","service":"cube"}
```

---

## Test the Service

### Health Check
```bash
curl http://localhost:8007/health
```

### Metrics
```bash
curl http://localhost:8007/metrics | head -20
```

### Get Cube (with mock authentication)
```bash
# Note: In production, you need a valid JWT token
curl -H "X-User-Id: test-user-123" \
     http://localhost:8007/cubes/550e8400-e29b-41d4-a716-446655440000
```

### Get Single Face
```bash
curl -H "X-User-Id: test-user-123" \
     http://localhost:8007/cubes/550e8400-e29b-41d4-a716-446655440000/faces/product_details
```

---

## Understanding Face States

When you request cube data, each face can be in one of three states:

### 1. Visible (Data Returned)
```json
{
  "face_name": "product_details",
  "status": "visible",
  "visibility": "public",
  "data": {
    "product_id": "prod-123",
    "product_name": "Designer Jacket",
    "brand_name": "LuxeBrand"
  }
}
```

### 2. Escalated (Awaiting Approval)
```json
{
  "face_name": "ownership",
  "status": "escalated_pending_human",
  "visibility": "private",
  "escalation_id": "esc-xyz789",
  "message": "Owner approval required to view this data",
  "estimated_response_time": "24 hours",
  "governance_console_url": "http://localhost:8006/review/esc-xyz789"
}
```

### 3. Denied (No Access)
```
HTTP 403 Forbidden
{
  "error": "access_denied",
  "message": "You do not have permission to view lifecycle"
}
```

---

## The Six Faces

| Face | Default Visibility | Description |
|------|-------------------|-------------|
| `product_details` | Public | Immutable product specs |
| `provenance` | Public | Append-only origin and journey |
| `ownership` | Private | Current owner and transfer history |
| `social_layer` | Public | Ratings, reviews, flex score |
| `esg_impact` | Public | Environmental and social scores |
| `lifecycle` | Authenticated | Repairs, resale, end-of-life |

---

## Common Operations

### Transfer Ownership
```bash
curl -X POST http://localhost:8007/cubes/CUBE_ID/transferOwnership \
  -H "Content-Type: application/json" \
  -H "X-User-Id: current-owner-id" \
  -d '{
    "from_owner_id": "current-owner-id",
    "to_owner_id": "new-owner-id",
    "transfer_method": "purchase",
    "price": 1500.00
  }'
```

**Response:**
```json
{
  "status": "transfer_complete",
  "transfer_id": "transfer-abc123",
  "blockchain_tx_hash": "cardano_tx_def456",
  "new_owner_id": "new-owner-id",
  "transfer_date": "2025-10-26T12:34:56Z"
}
```

---

## Architecture Flow

```
User Request
    ↓
Cube Service (8007)
    ↓
Policy Check (8001) ──→ [allow/escalate/deny]
    ↓
if allow:
    ↓
    Return Data + Log to Compliance (8004)

if escalate:
    ↓
    Create Escalation in Compliance (8004)
    ↓
    Notify Governance Console (8006)

if deny:
    ↓
    Return 403 + Log to Compliance
```

---

## Policy Rules

### Public Faces (Always Visible)
- product_details
- provenance
- social_layer
- esg_impact

### Private Face (Escalates for Non-Owners)
- ownership
  - Owner: ✅ Visible
  - Friends (trust_score ≥ 0.75): ✅ Visible
  - Others: ⚠️ Escalated

### Authenticated Face (Requires Login)
- lifecycle
  - Anonymous: ❌ Denied
  - Friends: ✅ Visible
  - Authenticated Non-Friends: ⚠️ Escalated

---

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker logs brandme-cube

# Common fixes
docker-compose restart cube
docker-compose restart policy
```

### Health Check Fails
```bash
# Check all dependencies
docker-compose ps

# Restart dependencies
docker-compose restart postgres policy compliance orchestrator identity
```

### Database Schema Missing
```bash
# Reinitialize
docker-compose exec postgres psql -U brandme -d brandme -f /docker-entrypoint-initdb.d/init.sql
```

---

## Development Mode

### Run with Hot Reload
```bash
cd brandme-cube
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql://brandme:brandme@localhost:5432/brandme
export POLICY_URL=http://localhost:8001
export COMPLIANCE_URL=http://localhost:8004
export ORCHESTRATOR_URL=http://localhost:8002
export IDENTITY_URL=http://localhost:8005

# Run with auto-reload
uvicorn src.main:app --host 0.0.0.0 --port 8007 --reload
```

### Run Tests
```bash
cd brandme-cube
pytest tests/ -v
```

---

## Next Steps

1. **Create test cubes** - Use the `/cubes` POST endpoint (to be implemented)
2. **Test ownership transfers** - Try different transfer methods
3. **Explore escalations** - Request private faces and check Governance Console
4. **View metrics** - Monitor face request patterns in Prometheus
5. **Read full docs** - See `docs/CUBE_SERVICE_INTEGRATION.md`

---

## Quick Reference

**Service URL:** http://localhost:8007

**Key Endpoints:**
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `GET /cubes/{id}` - Get full cube
- `GET /cubes/{id}/faces/{name}` - Get single face
- `POST /cubes/{id}/transferOwnership` - Transfer ownership

**Dependencies:**
- postgres (5432)
- policy (8001)
- compliance (8004)
- orchestrator (8002)
- identity (8005)

**Documentation:**
- Integration Guide: `docs/CUBE_SERVICE_INTEGRATION.md`
- Service README: `brandme-cube/README.md`
- Architecture: `docs/architecture/OVERVIEW.md`

---

**Status:** ✅ Ready to Use
**Support:** See troubleshooting section or main documentation
**Version:** 1.0.0 (Brand.Me v6)
