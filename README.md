# Brand.Me Labs — v9 Agentic & Circular Economy

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Brand.Me is a symbiotic intelligence platform that merges digital fashion, identity expression, and verifiable trust on the Cardano blockchain. Autonomous agents handle precision and scale while humans govern intent, empathy, and ethics.

## Documentation

**Quick Links**:
- [Architecture](./docs/architecture/SYSTEM_ARCHITECTURE.md) - v9 System architecture
- [Agentic Architecture](./docs/architecture/AGENTIC_ARCHITECTURE.md) - Agent system design
- [Deployment Guide](./docs/deployment/DEPLOYMENT_GUIDE.md) - How to deploy
- [Current Status](./docs/status/CURRENT_STATUS.md) - Platform status

## v9 Core Technologies

| Technology | Purpose |
|------------|---------|
| **Google Cloud Spanner** | Native Property Graph, O(1) consent lookups, Material tracking |
| **Firestore** | Real-time wardrobe sync, AR glasses biometric sync (<100ms) |
| **Model Context Protocol** | External agent access to Style Vault (7 tools) |
| **Cardano** | Public provenance, ESG oracle verification |
| **Midnight** | Private ownership, ZK burn proofs for circular economy |

## Key Features

### Product Cube (7 Faces)

Digital passport for physical assets:

| Face | Visibility | Blockchain |
|------|------------|------------|
| product_details | Public | Cardano |
| provenance | Public | Cardano |
| ownership | Private | Midnight |
| social_layer | Friends/Public | - |
| esg_impact | Public | Cardano |
| lifecycle | Public | Cardano |
| molecular_data | Private | Midnight |

### DPP Lifecycle State Machine

```
PRODUCED → ACTIVE → REPAIR → ACTIVE
                  ↘ DISSOLVE → REPRINT → PRODUCED
```

Enables circular economy with ZK burn proof verification for material recovery.

### MCP Tools for External Agents

```json
{
  "tools": [
    "search_wardrobe",
    "get_cube_details",
    "suggest_outfit",
    "initiate_rental",
    "list_for_resale",
    "request_repair",
    "request_dissolve"
  ]
}
```

All transaction tools require ESG verification from Cardano oracle.

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
│                     Client Layer                                 │
│         (Mobile App, Web, AR Glasses via Biometric Sync)        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────────┐
│                      brandme-gateway                             │
│            OAuth, Rate Limiting, MCP Server, NATS                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐
│  brandme-core   │ │ brandme-agents  │ │     brandme-chain       │
│                 │ │                 │ │                         │
│ • Brain (8000)  │ │ • Identity      │ │ • TX Builder            │
│ • Policy (8001) │ │ • Knowledge     │ │   Cardano + Midnight    │
│ • Orchestrator  │ │ • Compliance    │ │ • Cross-Chain Verifier  │
│ • Cube (8007)   │ │ • Agentic       │ │                         │
└────────┬────────┘ └────────┬────────┘ └────────────┬────────────┘
         │                   │                       │
         └───────────────────┼───────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                                │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐│
│  │ Google Cloud Spanner │  │ Firestore                        ││
│  │ Native Property Graph│  │ Real-time sync, AR glasses       ││
│  │ O(1) consent lookups │  │ Agentic state tracking           ││
│  └──────────────────────┘  └──────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────────┐
│                     BLOCKCHAIN LAYER                             │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐│
│  │ Cardano (Public)     │  │ Midnight (Private)               ││
│  │ Provenance, ESG      │  │ Ownership, Burn Proofs           ││
│  └──────────────────────┘  └──────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| brain | 8000 | Intent resolver, scan entrypoint |
| policy | 8001 | Consent graph & policy decisions |
| orchestrator | 8002 | Scan processing & blockchain anchoring |
| knowledge | 8003 | Safe facet retrieval |
| compliance | 8004 | Hash-chained audit, ESG verification |
| identity | 8005 | User profiles, ZK proofs |
| governance | 8006 | Human review console |
| cube | 8007 | Product Cube with real-time state |

## Repository Structure

```
Brand-Me-Labs/
├── brandme-gateway/          # Edge gateway, MCP server
├── brandme-core/             # Core services (brain, policy, orchestrator)
├── brandme-agents/           # Agent services (identity, knowledge, compliance, agentic)
├── brandme-governance/       # Human review console
├── brandme-cube/             # Product Cube service
├── brandme_core/             # Shared utilities (spanner, firestore, mcp, zk)
├── brandme-data/             # Database schemas (spanner/)
├── brandme-chain/            # Blockchain integration
├── brandme-console/          # Web interfaces
└── brandme-infra/            # Infrastructure as Code
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ and pnpm
- Python 3.11+
- kubectl and helm
- gcloud CLI

### Local Development

```bash
# Clone the repository
git clone https://github.com/brandme-labs/Brand-Me-Labs.git
cd Brand-Me-Labs

# Start emulators and services
docker-compose up -d

# Services started:
# - Spanner Emulator (9010, 9020)
# - Firestore Emulator (8080)
# - All 8 backend services

# Run tests
pytest tests/ -v
```

### Environment Variables

```bash
# Spanner
SPANNER_EMULATOR_HOST=localhost:9010
SPANNER_PROJECT_ID=brandme-project
SPANNER_INSTANCE_ID=brandme-instance
SPANNER_DATABASE_ID=brandme-db

# Firestore
FIRESTORE_EMULATOR_HOST=localhost:8080
FIRESTORE_PROJECT_ID=brandme-dev

# Blockchain (Production)
CARDANO_NODE_URL=http://cardano-node:3001
MIDNIGHT_API_URL=http://midnight-devnet:9000
```

## Security Guarantees

1. **O(1) Consent Checks** - Spanner graph queries for instant policy decisions
2. **ESG Verification** - All agent transactions require Cardano oracle check
3. **Idempotent Writes** - Commit timestamps prevent duplicate operations
4. **PII Redaction** - Driver-level redaction for all database operations
5. **Hash-Chained Audit** - Tamper-evident compliance trail
6. **Human-in-the-Loop** - Escalation workflow for high-risk decisions

## Tech Stack

### Infrastructure
- **Cloud**: Google Cloud Platform (GCP)
- **Kubernetes**: GKE
- **Primary Database**: Google Cloud Spanner (global consistency)
- **Real-time State**: Firestore
- **Event Bus**: NATS JetStream
- **Observability**: OpenTelemetry, Prometheus, Grafana

### Services
- **Backend**: Python (FastAPI), Node.js (TypeScript)
- **Frontend**: Next.js, React, Tailwind CSS
- **Blockchain**: Cardano, Midnight
- **Infrastructure**: Terraform, Helm

## Contributing

### Code Standards
- TypeScript: ESLint + Prettier
- Python: Black + Ruff + MyPy
- All services emit OpenTelemetry traces
- **No PII in logs** - Use `redact_user_id()` and `truncate_id()`
- Spanner for writes, Firestore for real-time reads
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
