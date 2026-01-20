# Brand.Me Platform - Architecture Overview (v8)

**Copyright (c) Brand.Me, Inc. All rights reserved.**

---

## Table of Contents
1. [Mission & Vision](#mission--vision)
2. [System Architecture](#system-architecture)
3. [Service Architecture](#service-architecture)
4. [Data Model](#data-model)
5. [Communication Patterns](#communication-patterns)
6. [Security & Privacy](#security--privacy)

---

## v8 Release: Global Integrity Spine

**Version 8** introduces a dual-database production stack replacing PostgreSQL:

- **Google Cloud Spanner**: Global consistency, Consent Graph, O(1) provenance lookups
- **Firestore**: Real-time wardrobe state, edge caching, agentic state broadcasting

| Feature | v6/v7 (PostgreSQL) | v8 (Spanner + Firestore) |
|---------|-------------------|--------------------------|
| Consent lookup | O(n) FK joins | O(1) graph query |
| Global revocation | Per-item update | Single row update |
| Provenance chain | JSONB blob | Interleaved table |
| Real-time state | HTTP polling | Firestore listeners |
| Idempotency | Application-level | Commit timestamps |
| PII protection | Manual | Driver-level redaction |
| Connection pool | asyncpg 20 max | PingingPool 100 max |

---

## Mission & Vision

### North Star
**Verifiable identity, provenance, and cultural expression through fashion.**

### Integrity Definition
1. **Immutable provenance** for garments and creators
2. **Consent-driven visibility** for owners
3. **Auditability** for regulators
4. **No silent exposure** of private data

### Architecture Principles
- **Dual-Blockchain**: Public provenance on Cardano, private ownership on Midnight
- **Dual-Database**: Spanner for consistency, Firestore for real-time
- **Microservices**: Independent, scalable services with clear boundaries
- **Event-Driven**: Async communication via NATS JetStream
- **Security-First**: Zero-trust architecture with authentication and rate limiting
- **Observable**: Metrics, tracing, and logging throughout

---

## System Architecture

### High-Level Architecture (v8)

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                            │
│              (Mobile App, Web Browsers, API Clients)           │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      brandme-gateway (Port 3000)                │
│   - OAuth Authentication                                        │
│   - Rate Limiting (100/min global, 10/min scan)                │
│   - Request Routing                                             │
│   - NATS Event Publishing                                       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ NATS JetStream
                         │
         ┌───────────────┴────────────────┬──────────────────┐
         │                                │                  │
         ▼                                ▼                  ▼
┌──────────────────┐           ┌──────────────────┐  ┌───────────────┐
│ brandme-core     │           │ brandme-agents    │  │ brandme-chain │
│                  │◄──────────┤                   │  │               │
│ - Brain (8000)   │           │ - Identity (8005)│  │ TX Builder    │
│ - Policy (8001)  │           │ - Knowledge(8003)│  │ (Port 3001)   │
│ - Orchestrator(8002)│        │ - Compliance(8004)│  │               │
│ - Cube (8007)    │           │                   │  │               │
└────────┬────────┘           └──────────────────┘  └───────┬───────┘
         │                                                    │
         ▼                                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER (v8)                            │
│  ┌──────────────────────────┐  ┌──────────────────────────┐    │
│  │    Google Cloud Spanner  │  │       Firestore          │    │
│  │                          │  │                          │    │
│  │  • Users (node)          │  │  • /wardrobes/{user_id}  │    │
│  │  • Assets (node)         │  │    └─ /cubes/{cube_id}   │    │
│  │  • Owns (edge)           │  │       └─ faces, state    │    │
│  │  • Created (edge)        │  │                          │    │
│  │  • FriendsWith (edge)    │  │  • /agent_sessions/      │    │
│  │  • ConsentPolicies       │  │                          │    │
│  │  • ProvenanceChain       │  │  Real-time listeners     │    │
│  │  • AuditLog              │  │  for frontend updates    │    │
│  │                          │  │                          │    │
│  │  O(1) consent lookups    │  │  Agentic state sync      │    │
│  │  Global revocation       │  │  Edge caching            │    │
│  └──────────────────────────┘  └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
         │                                    │
         ▼                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BLOCKCHAIN LAYER                              │
│  ┌──────────────────────┐  ┌──────────────────────┐            │
│  │      Cardano         │  │      Midnight        │            │
│  │   (Public Chain)     │  │   (Private Chain)    │            │
│  │                      │  │                      │            │
│  │  • Provenance        │  │  • Ownership         │            │
│  │  • ESG anchors       │  │  • Pricing history   │            │
│  │  • Creator credits   │  │  • Consent proofs    │            │
│  └──────────────────────┘  └──────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
         ▲
         │
┌────────┴────────────────────────────────────────────────────┐
│                  brandme-console (Port 3002)                 │
│                                                              │
│  ┌────────────────────────┐  ┌──────────────────────────┐  │
│  │ Governance Console     │  │ Transparency Portal      │  │
│  │ (Internal, RBAC)       │  │ (Public)                 │  │
│  │ Port 8006             │  │ No Auth Required         │  │
│  └────────────────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## Service Architecture

### Core Services (brandme-core)

#### 1. Brain Service (Port 8000)
**Role**: Intent resolution and scan orchestration

**Responsibilities**:
- Resolve garment_tag to garment_id
- Call policy service for consent check
- Route decisions (allow/deny/escalate)
- Coordinate orchestrator for allowed scans
- Handle escalation workflow

**Endpoints**:
- `POST /intent/resolve` - Resolve scan intent
- `GET /health` - Health check with DB verification
- `GET /metrics` - Prometheus metrics

**Security**: CORS enabled, authentication via gateway

---

#### 2. Policy Service (Port 8001)
**Role**: Consent graph and policy enforcement

**Responsibilities**:
- Evaluate user consent policies
- Determine visibility scope (public/friends_only/private)
- Check regional compliance rules
- Make allow/deny/escalate decisions
- Track policy versions

**Endpoints**:
- `POST /policy/check` - Policy decision
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics

**Security**: CORS enabled

---

#### 3. Orchestrator Service (Port 8002)
**Role**: Scan processing and blockchain anchoring

**Responsibilities**:
- Process allowed scans only
- Fetch facets from knowledge service
- Persist scan events to database
- Build blockchain transactions
- Call compliance for audit logging

**Endpoints**:
- `POST /scan/commit` - Commit allowed scan
- `GET /health` - Health check with DB verification
- `GET /metrics` - Prometheus metrics

**Security**: Internal service, no CORS needed

---

### Agent Services (brandme-agents)

#### 4. Identity Service (Port 8005)
**Role**: User identity and trust management

**Responsibilities**:
- User profile retrieval
- Trust score calculation
- Relationship verification
- Consent graph management

**Endpoints**:
- `GET /identity/{user_id}/profile` - Get user profile
- `GET /health` - Health check with DB verification
- `GET /metrics` - Prometheus metrics

---

#### 5. Knowledge Service (Port 8003)
**Role**: Garment passport facet retrieval

**Responsibilities**:
- Return safe facets for display
- NEVER return private data (pricing, ownership lineage)
- Filter by consent scope
- Provide public-safe previews

**Endpoints**:
- `GET /garment/{garment_id}/passport` - Get passport facets
- `GET /health` - Health check with DB verification
- `GET /metrics` - Prometheus metrics

**Security**: CORS enabled, scope-based filtering

---

#### 6. Compliance Service (Port 8004)
**Role**: Audit logging and escalations

**Responsibilities**:
- Hash-chained audit logging
- Track all policy decisions
- Manage escalation workflow
- Provide audit trail queries

**Endpoints**:
- `POST /audit/log` - Log audit entry
- `POST /audit/escalate` - Queue escalation
- `POST /audit/anchorChain` - Record blockchain anchors
- `GET /audit/{scan_id}/explain` - Get audit trail
- `GET /health` - Health check with DB verification
- `GET /metrics` - Prometheus metrics

---

### Governance & Console

#### 7. Governance Console (Port 8006)
**Role**: Human review and oversight

**Responsibilities**:
- List pending escalations
- Provide human approval for escalated scans
- Display audit trail
- Controlled reveal workflow

**Endpoints**:
- `GET /governance/escalations` - List pending escalations
- `POST /governance/escalations/{scan_id}/decision` - Approve/deny
- `GET /health` - Health check with DB verification
- `GET /metrics` - Prometheus metrics

**Security**: CORS enabled, RBAC required

---

### Gateway

#### 8. API Gateway (Port 3000)
**Role**: Edge API gateway

**Responsibilities**:
- OAuth authentication (JWT validation)
- Rate limiting (token bucket algorithm)
- Request routing
- NATS event publishing
- Security headers (helmet)

**Security Features**:
- JWT Bearer token authentication
- 100 req/min global rate limit
- 10 req/min for /scan endpoints
- CORS with origin validation
- Content Security Policy

---

### Blockchain

#### 9. Chain Service (Port 3001)
**Role**: Blockchain transaction builder

**Responsibilities**:
- Build Cardano transactions (public data)
- Build Midnight transactions (private data)
- Cross-chain verification
- Transaction signing and submission

**Endpoints**:
- `POST /tx/anchor-scan` - Anchor scan to chains
- `POST /tx/verify-root` - Verify cross-chain hash
- `GET /health` - Health check

---

## Data Model (v8)

See [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) for complete schema.

### Spanner Tables (Source of Truth)

**Node Tables:**
- `Users` - User accounts with trust scores, consent versions
- `Assets` - Asset records (cubes, garments) with provenance

**Edge Tables:**
- `Owns` - Ownership relationships (O(1) lookup)
- `Created` - Creator attribution
- `FriendsWith` - Social graph for consent scoping

**Supporting Tables:**
- `ConsentPolicies` - Per-user/per-asset consent settings
- `ProvenanceChain` - Interleaved provenance with sequence numbers
- `CubeFaces` - Product Cube face data
- `AuditLog` - Hash-chained audit trail
- `ChainAnchor` - Blockchain transaction references
- `MutationLog` - Idempotent write deduplication

### Firestore Collections (Real-Time State)

- `/wardrobes/{user_id}` - User wardrobe metadata
  - `/cubes/{cube_id}` - Cube state, faces, visibility
- `/agent_sessions/{session_id}` - Agentic modification tracking

### Consent Graph Model

```sql
-- O(1) consent check via graph traversal
GRAPH IntegritySpineGraph
MATCH (viewer:Users)-[:FRIENDS_WITH*0..1]-(owner:Users)-[:OWNS]->(asset:Assets)
WHERE asset.asset_id = @asset_id
  AND NOT EXISTS {
    MATCH (owner)-[:HAS_CONSENT]->(consent:ConsentPolicies)
    WHERE consent.is_revoked = true
  }
RETURN owner.user_id, viewer.user_id;
```

---

## Communication Patterns

### 1. Synchronous (HTTP/REST)
- Client → Gateway → Core Services
- Service-to-service calls
- Uses retry logic with exponential backoff

### 2. Asynchronous (Events)
- Gateway → NATS → Core Services
- Event-driven workflow
- NATS JetStream for reliability

### 3. Database (Spanner)
- PingingPool connection management (min: 10, max: 100)
- Commit timestamp idempotency
- O(1) graph queries for consent

### 4. Real-Time (Firestore)
- Wardrobe state listeners for frontends
- Agentic modification broadcasting
- Background sync to Spanner

---

## Security & Privacy

### Security Guarantees (v8)
1. **O(1) Consent Checks**: Spanner graph queries for instant policy decisions
2. **Global Revocation**: Single operation revokes all consent policies
3. **Idempotent Writes**: Commit timestamps prevent duplicate operations
4. **PII Redaction**: Driver-level redaction for all database operations
5. **Real-time Sync**: Firestore broadcasts state changes to frontends
6. **Connection Pooling**: PingingPool handles NATS high-concurrency
7. **Hash-Chained Audit**: Every compliance log entry cryptographically linked
8. **Authentication Required**: All scan endpoints protected by JWT
9. **Rate Limiting**: Prevents abuse with token bucket algorithm

### Privacy Layers
- **Public Chain (Cardano)**: Provenance, ESG, creator attribution
- **Private Chain (Midnight)**: Ownership lineage, pricing history
- **Cross-Chain Proof**: Cryptographic linking between chains
- **Scope-Based Access**: public/friends_only/private

### PII Redaction (Driver Level)
```python
# PII is redacted at the database driver level
client = PIIRedactingClient(pool_manager)
results = await client.execute_sql(
    "SELECT * FROM Users WHERE user_id = @id",
    params={"id": user_id},
    redact_results=True  # For external APIs
)
# Logs show: user_id=11111111...1111
```

---

## Observability

### Metrics (Prometheus)
All services expose `/metrics` endpoint with:
- HTTP request metrics
- Database connection metrics
- Service-to-service call metrics
- Business metrics (scans, decisions, escalations)
- Error tracking
- Health check status

### Tracing (OpenTelemetry)
- Distributed tracing ready
- Request ID propagation
- Service call tracing
- Error recording in spans

### Logging
- Structured JSON logging
- PII redaction
- Request tracing
- Error context

---

## Deployment Architecture

### Infrastructure (GCP) - v8
- **GKE**: Kubernetes orchestration
- **Google Cloud Spanner**: Global consistency database (source of truth)
- **Firestore**: Real-time wardrobe state, edge caching
- **GCS**: Object storage
- **NATS JetStream**: Event streaming
- **Prometheus**: Metrics collection
- **Grafana**: Visualization

### Database Libraries (v8)
- **Spanner**: `google-cloud-spanner` with PingingPool
- **Firestore**: `google-cloud-firestore` with async client
- **Legacy**: `asyncpg` (deprecated, kept for migration)

### Local Development with Emulators
```bash
# Start local development environment with emulators
docker-compose up -d

# This starts:
# - Spanner Emulator (ports 9010, 9020)
# - Firestore Emulator (port 8080)
# - All 8 backend services

# Run tests against emulators
pytest tests/ -v
```

### Scaling Strategy
- **Horizontal**: Auto-scaling (HPA)
- **Vertical**: Resource requests/limits
- **Regional**: Multi-region ready via Spanner

---

## References

- [Service Specifications](./SERVICES.md)
- [Database Schema](./DATABASE_SCHEMA.md)
- [Deployment Guide](../deployment/DEPLOYMENT.md)
- [Status](../status/CURRENT_STATUS.md)

