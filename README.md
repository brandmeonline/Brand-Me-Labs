# Brand.Me Labs — v8 Global Integrity Spine

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Brand.Me is a symbiotic intelligence platform that merges digital fashion, identity expression, and verifiable trust on the Cardano blockchain. It is designed to redefine ownership, authenticity, and culture through agentic intelligence—where autonomous systems handle precision and scale, and humans govern intent, empathy, and ethics.

## 📋 Documentation

**Quick Links**:
- 📖 [Architecture](./docs/architecture/OVERVIEW.md) - System architecture
- 🚀 [Deployment Guide](./docs/deployment/DEPLOYMENT_GUIDE.md) - How to deploy
- 📊 [Current Status](./docs/status/CURRENT_STATUS.md) - Platform status
- 🎯 [Roadmap](./docs/next_steps/ROADMAP.md) - Next steps
- 📈 [Observability](./docs/infrastructure/OBSERVABILITY.md) - Monitoring & metrics

**Complete Documentation**: See [docs/](./docs/) directory

## v8 Release: Global Integrity Spine with Spanner + Firestore

**Version 8** introduces a dual-database production stack replacing PostgreSQL:

- **Google Cloud Spanner**: Global consistency, Consent Graph, O(1) provenance lookups
- **Firestore**: Real-time wardrobe state, edge caching, agentic state broadcasting

### What's New in v8

| Feature | v6/v7 (PostgreSQL) | v8 (Spanner + Firestore) |
|---------|-------------------|--------------------------|
| Consent lookup | O(n) FK joins | O(1) graph query |
| Global revocation | Per-item update | Single row update |
| Provenance chain | JSONB blob | Interleaved table |
| Real-time state | HTTP polling | Firestore listeners |
| Idempotency | Application-level | Commit timestamps |
| PII protection | Manual | Driver-level redaction |
| Connection pool | asyncpg 20 max | PingingPool 100 max |

## North Star Mission

**Verifiable identity, provenance, and cultural expression through fashion.**

### Integrity Definition

- Immutable provenance for garments and creators
- Consent-driven visibility for owners
- Auditability for regulators
- No silent exposure of private data

## Architecture Overview

Brand.Me uses a dual-blockchain architecture for privacy-preserving garment provenance:

- **Cardano**: Public provenance, creator attribution, and ESG anchors
- **Midnight**: Private ownership lineage, pricing history, and consent snapshots
- **Cross-Chain Verification**: Cryptographic linking between chains

### v6 Service Architecture

All 9 backend services are production-ready with:
- ✅ X-Request-Id tracing propagation
- ✅ PII redaction with `redact_user_id()` and `truncate_id()`
- ✅ CORS middleware on public-facing services
- ✅ Consent graph integration
- ✅ Hash-chained audit logging
- ✅ Human escalation guardrails
- ✅ Safe facet previews only

#### Service Ports
| Service | Port | Description |
|---------|------|-------------|
| **brain** | 8000 | Intent resolver, scan entrypoint, CORS enabled |
| **policy** | 8001 | Consent graph & policy decisions, CORS enabled |
| **orchestrator** | 8002 | Scan processing & blockchain anchoring |
| **knowledge** | 8003 | Safe facet retrieval, CORS enabled |
| **compliance** | 8004 | Hash-chained audit logging & escalations |
| **identity** | 8005 | User profiles & consent graph |
| **governance_console** | 8006 | Human review UI, CORS enabled |
| **cube** | 8007 | Product Cube storage & serving, CORS enabled |
| **agentic/orchestrator** | — | Multi-agent workflow (library) |
| **brandme_core/logging** | — | Shared logging utilities (library) |

### Key Components
Brand.Me uses a **triple-layer architecture** for global consistency and real-time updates:

- **Spanner**: Source of truth for users, assets, consent graph, provenance chain
- **Firestore**: Real-time wardrobe state, agentic modifications, frontend sync
- **Cardano + Midnight**: Blockchain anchoring for immutable provenance

### v8 Database Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     APPLICATION LAYER                            │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐            │
│  │ Brain   │  │ Policy  │  │Identity │  │  Cube   │            │
│  │ (8000)  │  │ (8001)  │  │ (8005)  │  │ (8007)  │            │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘            │
└───────┼────────────┼────────────┼────────────┼──────────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                  │
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
```

### Consent Graph Model (Spanner)

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

### Service Ports

| Service | Port | Description | Database |
|---------|------|-------------|----------|
| **brain** | 8000 | Intent resolver, scan entrypoint | Spanner |
| **policy** | 8001 | Consent graph & policy decisions | Spanner |
| **orchestrator** | 8002 | Scan processing & blockchain anchoring | Spanner |
| **knowledge** | 8003 | Safe facet retrieval | Spanner |
| **compliance** | 8004 | Hash-chained audit logging | Spanner |
| **identity** | 8005 | User profiles, friends, consent | Spanner |
| **governance_console** | 8006 | Human review UI | Spanner |
| **cube** | 8007 | Product Cube with real-time state | Spanner + Firestore |

## Repository Structure

This monorepo contains all Brand.Me services:

```
Brand-Me-Labs/
├── brandme-gateway/          # Edge API gateway (Node/TypeScript)
├── brandme-core/             # Core services (Python/FastAPI)
│   ├── brain/                # Intent resolver (port 8000)
│   ├── policy/               # Consent graph & policy (port 8001)
│   └── orchestrator/         # Scan processing (port 8002)
├── brandme-agents/           # Agent services (Python/FastAPI)
│   ├── identity/             # User profiles, friends (port 8005)
│   ├── knowledge/            # Safe facet retrieval (port 8003)
│   ├── compliance/           # Audit logging (port 8004)
│   └── agentic/              # Multi-agent workflow (library)
├── brandme-governance/       # Human review console (port 8006)
├── brandme-cube/             # Product Cube service (port 8007)
├── brandme_core/             # Shared utilities
│   ├── spanner/              # Spanner client library
│   │   ├── client.py         # Core Spanner client
│   │   ├── pool.py           # PingingPool for NATS
│   │   ├── consent_graph.py  # O(1) consent lookups
│   │   ├── provenance.py     # Interleaved provenance
│   │   ├── idempotent.py     # Commit timestamp dedup
│   │   └── pii_redactor.py   # Driver-level PII redaction
│   ├── firestore/            # Firestore client library
│   │   ├── client.py         # Async Firestore client
│   │   ├── wardrobe.py       # Wardrobe state manager
│   │   ├── realtime.py       # Real-time listeners
│   │   ├── agentic.py        # Agentic state manager
│   │   └── sync.py           # Spanner ↔ Firestore sync
│   └── logging.py            # Structured logging, PII redaction
├── brandme-data/             # Database schema
│   ├── spanner/              # Spanner DDL
│   │   └── schema.sql        # Full Spanner Graph schema
│   └── schemas/              # Legacy PostgreSQL (deprecated)
├── brandme-chain/            # Blockchain integration (Node/TypeScript)
├── brandme-console/          # Web interfaces (Next.js/React)
├── brandme-infra/            # Infrastructure as Code (Terraform/Helm)
├── tests/                    # Integration tests
│   ├── conftest.py           # Emulator fixtures
│   ├── test_consent_graph.py # Consent graph tests
│   ├── test_provenance.py    # Provenance tests
│   └── test_wardrobe.py      # Firestore tests
└── docker-compose.yml        # Local dev with emulators
```

## Tech Stack

### Infrastructure
- **Cloud**: Google Cloud Platform (GCP)
- **Kubernetes**: GKE
- **Primary Database**: Google Cloud Spanner (global consistency)
- **Real-time Cache**: Firestore (wardrobe state)
- **Event Bus**: NATS JetStream
- **Storage**: Google Cloud Storage (GCS)
- **Observability**: OpenTelemetry, Prometheus, Grafana, Loki

### Services
- **Backend**: Python (FastAPI), Node.js (TypeScript)
- **Frontend**: Next.js, React, Tailwind CSS
- **Blockchain**: Cardano, Midnight
- **Infrastructure**: Terraform, Helm

### Database Libraries
- **Spanner**: `google-cloud-spanner` with PingingPool
- **Firestore**: `google-cloud-firestore` with async client

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Node.js 18+ and pnpm
- Python 3.11+
- kubectl and helm
- gcloud CLI
- Terraform 1.5+

### Local Development with Emulators

```bash
# Clone the repository
git clone https://github.com/brandme-labs/Brand-Me-Labs.git
cd Brand-Me-Labs

# Start local development environment with emulators
docker-compose up -d

# This starts:
# - Spanner Emulator (ports 9010, 9020)
# - Firestore Emulator (port 8080)
# - All 8 backend services

# Wait for Spanner schema initialization
docker-compose logs -f spanner-init

# Verify all services are running
curl http://localhost:8000/health  # brain
curl http://localhost:8001/health  # policy
curl http://localhost:8002/health  # orchestrator
curl http://localhost:8003/health  # knowledge
curl http://localhost:8004/health  # compliance
curl http://localhost:8005/health  # identity
curl http://localhost:8006/health  # governance
curl http://localhost:8007/health  # cube

# Run tests against emulators
pytest tests/ -v
```

### Environment Configuration

Key environment variables for Spanner + Firestore:

```bash
# Spanner Configuration
SPANNER_EMULATOR_HOST=localhost:9010  # For local dev
SPANNER_PROJECT_ID=brandme-project
SPANNER_INSTANCE_ID=brandme-instance
SPANNER_DATABASE_ID=brandme-db
SPANNER_POOL_SIZE=10
SPANNER_MAX_SESSIONS=100

# Firestore Configuration
FIRESTORE_EMULATOR_HOST=localhost:8080  # For local dev
FIRESTORE_PROJECT_ID=brandme-dev
```

## Runtime Flow: Garment Scan (v8)

1. **Mobile client** calls `POST /scan` with `garment_tag`
2. **Gateway** publishes `scan.requested` event to NATS
3. **Brain** (port 8000) resolves intent and `garment_id`
4. **Policy** (port 8001) checks consent via **Spanner Graph**:
   - O(1) consent lookup using graph traversal
   - Checks friendship status via `FriendsWith` edge table
   - Resolves scope: `private` | `friends_only` | `public`
5. **Orchestrator** (port 8002) processes allowed scans:
   - **Idempotent writes** using Spanner commit timestamps
   - Records provenance in interleaved `ProvenanceChain` table
   - Builds blockchain transactions
6. **Cube** (port 8007) serves product data:
   - **Real-time state** from Firestore
   - Agents modify faces → Firestore broadcasts to frontend
   - Background sync to Spanner (source of truth)
7. **Identity** (port 8005) provides user profiles:
   - Friends list from `FriendsWith` table
   - Consent policies from `ConsentPolicies` table
   - **Global revocation** in single operation

## Production Readiness

### Idempotency (Spanner Commit Timestamps)

```python
# All writes are idempotent via MutationLog table
result = await idempotent_writer.execute_idempotent(
    operation_name="transfer_ownership",
    params={"cube_id": "abc", "new_owner": "xyz"},
    mutations=[...]
)
# Returns 'executed' or 'duplicate'
```

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

### Connection Pooling (NATS High-Concurrency)

```python
# PingingPool keeps sessions warm for NATS JetStream
pool = SpannerPoolManager(
    min_sessions=10,
    max_sessions=100,
    ping_interval=300  # 5 minutes
)
```

### Real-time Updates (Firestore)

```typescript
// Frontend receives live updates when agents modify cubes
const { cubes, isConnected } = useWardrobeRealtime(userId);

// Toast notification when agent modifies
if (cube.agentic_state === 'modified') {
  toast({ title: 'Wardrobe Updated', ... });
}
```

## Deployment

### Production Deployment to GKE

```bash
# Configure GCP project
gcloud config set project YOUR_PROJECT_ID

# Create Spanner instance
gcloud spanner instances create brandme-instance \
  --config=regional-us-central1 \
  --description="Brand.Me Production" \
  --nodes=3

# Create database with schema
gcloud spanner databases create brandme-db \
  --instance=brandme-instance \
  --ddl-file=brandme-data/spanner/schema.sql

# Provision remaining infrastructure
cd brandme-infra/terraform
terraform init
terraform apply

# Deploy services via Helm
cd ../helm
helm upgrade --install brandme ./brandme-umbrella \
  --values values.yaml \
  --namespace brandme \
  --create-namespace
```

## Security Guarantees (v8)

1. ✅ **O(1) Consent Checks**: Spanner graph queries for instant policy decisions
2. ✅ **Global Revocation**: Single operation revokes all consent policies
3. ✅ **Idempotent Writes**: Commit timestamps prevent duplicate operations
4. ✅ **PII Redaction**: Driver-level redaction for all database operations
5. ✅ **Real-time Sync**: Firestore broadcasts state changes to frontends
6. ✅ **Connection Pooling**: PingingPool handles NATS high-concurrency
7. ✅ **Hash-Chained Audit**: Every compliance log entry cryptographically linked

## Contributing

### Code Standards
- TypeScript: ESLint + Prettier
- Python: Black + Ruff + MyPy
- All services must emit OpenTelemetry traces
- **No PII in logs** - Use `redact_user_id()` and `truncate_id()`
- Use Spanner for writes, Firestore for real-time reads
- All database operations must be idempotent

### Git Workflow
1. Create feature branch from `main`
2. Make changes with clear commit messages
3. Ensure all tests pass (including emulator tests)
4. Submit PR with description
5. Require 2 approvals for merge

## License

Copyright (c) Brand.Me, Inc. All rights reserved.

Proprietary and confidential. Unauthorized copying or distribution is prohibited.
