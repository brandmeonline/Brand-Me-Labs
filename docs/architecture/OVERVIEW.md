# Brand.Me Platform - Architecture Overview

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
- **Microservices**: Independent, scalable services with clear boundaries
- **Event-Driven**: Async communication via NATS JetStream
- **Security-First**: Zero-trust architecture with authentication and rate limiting
- **Observable**: Metrics, tracing, and logging throughout

---

## System Architecture

### High-Level Architecture

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
└────────┬────────┘           └──────────────────┘  └───────┬───────┘
         │                                                    │
         │                                                    │
         ▼                                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Data & Blockchain Layer                       │
│                                                                 │
│  ┌───────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ Cloud SQL     │  │   Cardano   │  │     Midnight        │  │
│  │ PostgreSQL 16 │  │ (Public L1)│  │  (Private Chain)    │  │
│  └───────────────┘  └──────────────┘  └─────────────────────┘  │
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

## Data Model

See [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) for complete schema.

### Core Tables
- `users` - User accounts with trust scores
- `garments` - Garment records with provenance
- `garment_passport_facets` - Facet data (public/private)
- `scan_event` - Scan history
- `chain_anchor` - Blockchain transaction references
- `audit_log` - Hash-chained audit trail

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

### 3. Database (PostgreSQL)
- Connection pooling (min: 5, max: 20)
- Environment-based configuration
- Health checks verify connectivity

---

## Security & Privacy

### Security Guarantees
1. **Authentication Required**: All scan endpoints protected by JWT
2. **Rate Limiting**: Prevents abuse with token bucket algorithm
3. **Secure CORS**: Origin validation, no wildcards in production
4. **CSP Headers**: Content Security Policy protects against XSS
5. **Request Size Limits**: 1MB max payload size
6. **PII Redaction**: All user IDs truncated in logs
7. **Hash-Chained Audit**: Tamper-evident audit trail

### Privacy Layers
- **Public Chain (Cardano)**: Provenance, ESG, creator attribution
- **Private Chain (Midnight)**: Ownership lineage, pricing history
- **Cross-Chain Proof**: Cryptographic linking between chains
- **Scope-Based Access**: public/friends_only/private

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

### Infrastructure (GCP)
- **GKE**: Kubernetes orchestration
- **Cloud SQL**: PostgreSQL database
- **GCS**: Object storage
- **NATS JetStream**: Event streaming
- **Prometheus**: Metrics collection
- **Grafana**: Visualization

### Scaling Strategy
- **Horizontal**: Auto-scaling (HPA)
- **Vertical**: Resource requests/limits
- **Regional**: Multi-region ready

---

## References

- [Service Specifications](./SERVICES.md)
- [Database Schema](./DATABASE_SCHEMA.md)
- [Deployment Guide](../deployment/DEPLOYMENT.md)
- [Status](../status/CURRENT_STATUS.md)

