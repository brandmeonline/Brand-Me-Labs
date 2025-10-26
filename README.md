# Brand.Me Labs — v6 Stable Integrity Spine

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Brand.Me is a symbiotic intelligence platform that merges digital fashion, identity expression, and verifiable trust on the Cardano blockchain. It is designed to redefine ownership, authenticity, and culture through agentic intelligence—where autonomous systems handle precision and scale, and humans govern intent, empathy, and ethics.

## v6 Release: Stable Integrity Spine

**Version 6** implements the core integrity spine with request tracing, human escalation guardrails, and safe facet previews across all 9 backend services.

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
| **agentic/orchestrator** | — | Multi-agent workflow (library) |
| **brandme_core/logging** | — | Shared logging utilities (library) |

### Key Components

```
┌─────────────────┐
│  Mobile Client  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    brandme-gateway                          │
│              (OAuth, NATS Publisher, API)                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼ NATS JetStream
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌────────────────────┐         ┌──────────────────────┐
│   brandme-core     │         │  brandme-agents      │
│  - AI Brain Hub    │◄────────┤  - Identity Service  │
│  - Policy & Safety │         │  - Knowledge/RAG     │
│  - Orchestrator    │         │  - Compliance/Audit  │
└────────┬───────────┘         └──────────────────────┘
         │
         ▼
┌──────────────────────┐       ┌──────────────────────┐
│   brandme-chain      │       │   brandme-console    │
│  - TX Builder        │       │  - Governance UI     │
│  - Cross-Chain       │       │  - Transparency      │
│    Verifier          │       │    Portal            │
└──────────────────────┘       └──────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  Cardano          │      Midnight      │
│  (Public Chain)   │   (Private Chain)  │
└────────────────────────────────────────┘
```

## Repository Structure

This monorepo contains all Brand.Me services:

- **brandme-gateway**: Edge API gateway (Node/TypeScript)
- **brandme-core**: AI Brain Hub, Policy Engine, Orchestrator (Python/FastAPI)
  - `brain/main.py` - Intent resolver (port 8000)
  - `policy/main.py` - Consent graph & policy decisions (port 8001)
  - `orchestrator/worker.py` - Scan processing & anchoring (port 8002)
- **brandme-agents**: Supporting agent services (Python/FastAPI)
  - `identity/src/main.py` - User profiles (port 8005)
  - `knowledge/src/main.py` - Safe facet retrieval (port 8003)
  - `compliance/src/main.py` - Audit logging (port 8004)
  - `agentic/orchestrator/agents.py` - Multi-agent workflow
- **brandme-governance**: Human review console (Python/FastAPI)
  - `governance_console/main.py` - Escalation review UI (port 8006)
- **brandme_core**: Shared utilities
  - `logging.py` - Structured logging, PII redaction, request tracing
- **brandme-data**: Database schema and migrations (SQL/Python)
- **brandme-chain**: Blockchain integration (Node/TypeScript)
- **brandme-console**: Web interfaces (Next.js/React)
- **brandme-infra**: Infrastructure as Code (Terraform/Helm)

## Tech Stack

### Infrastructure
- **Cloud**: Google Cloud Platform (GCP)
- **Kubernetes**: GKE
- **Database**: Cloud SQL (PostgreSQL)
- **Event Bus**: NATS JetStream
- **Storage**: Google Cloud Storage (GCS)
- **Observability**: OpenTelemetry, Prometheus, Grafana, Loki

### Services
- **Backend**: Python (FastAPI), Node.js (TypeScript)
- **Frontend**: Next.js, React, Tailwind CSS
- **Blockchain**: Cardano, Midnight
- **Infrastructure**: Terraform, Helm

## Privacy & Compliance Model

### Privacy Layers
- **Public Chain (Cardano)**: Provenance, ESG, creator attribution
- **Private Chain (Midnight)**: Ownership, pricing, consent policies
- **Cross-Chain Proof**: Cryptographic link via Cross-Chain Verifier

### Access Control
- **Midnight Decrypt Policy**: governance_humans_and_compliance_agent
- **Transparency Portal**: Public (sanitized data only)
- **Governance Console**: RBAC-protected (ROLE_GOVERNANCE, ROLE_COMPLIANCE)
- **Regulator View**: Read-only, auditable trail

### Security Guarantees
1. Policy & Safety MUST run before any reveal
2. TX Builder is the ONLY path to blockchain writes
3. Compliance & Audit MUST hash-chain every decision
4. Governance Console MUST enforce dual approval for Midnight reveals
5. Transparency Portal MUST NOT leak private data

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Node.js 18+ and pnpm
- Python 3.11+
- kubectl and helm
- gcloud CLI
- Terraform 1.5+

### Local Development

```bash
# Clone the repository
git clone https://github.com/brandme-labs/Brand-Me-Labs.git
cd Brand-Me-Labs

# Install dependencies for all services
make install

# Start local development environment (requires Docker)
make dev-up
# OR use docker-compose directly:
docker-compose up -d

# Run database migrations
make db-migrate

# Seed development data
make db-seed

# Verify all services are running
curl http://localhost:8000/health  # brain
curl http://localhost:8001/health  # policy
curl http://localhost:8002/health  # orchestrator
curl http://localhost:8003/health  # knowledge
curl http://localhost:8004/health  # compliance
curl http://localhost:8005/health  # identity
curl http://localhost:8006/health  # governance

# Run tests
make test
```

### v6 Service Validation

All 9 Python services have been validated:
```bash
python3 -m py_compile brandme_core/logging.py
python3 -m py_compile brandme-core/brain/main.py
python3 -m py_compile brandme-core/policy/main.py
python3 -m py_compile brandme-core/orchestrator/worker.py
python3 -m py_compile brandme-agents/identity/src/main.py
python3 -m py_compile brandme-agents/knowledge/src/main.py
python3 -m py_compile brandme-agents/compliance/src/main.py
python3 -m py_compile brandme-agents/agentic/orchestrator/agents.py
python3 -m py_compile brandme-governance/governance_console/main.py
```

### Environment Configuration

Each service requires environment variables. See `.env.example` files in each service directory:

- `brandme-gateway/.env.example`
- `brandme-core/.env.example`
- `brandme-agents/.env.example`
- `brandme-chain/.env.example`
- `brandme-console/.env.example`

**IMPORTANT**: Never commit secrets or wallet keys. Use Kubernetes secrets in production.

## Testing

### Unit Tests

Run unit tests for all services:

```bash
# Run all tests
make test

# Run tests for specific service
cd brandme-chain && pnpm test

# Run with coverage
cd brandme-chain && pnpm test:coverage

# Watch mode for development
cd brandme-chain && pnpm test:watch
```

### Blockchain Integration Tests

Test against real Cardano testnet:

```bash
# 1. Set up test wallet (one-time setup)
cd brandme-chain
./scripts/setup-test-wallet.sh

# 2. Get Blockfrost API key from https://blockfrost.io
# 3. Edit .env.integration with your API key

# 4. Fund wallet from testnet faucet
# Visit: https://docs.cardano.org/cardano-testnet/tools/faucet/

# 5. Run integration tests
export $(cat .env.integration | xargs)
INTEGRATION=true pnpm test:integration
```

See [brandme-chain/TESTING.md](brandme-chain/TESTING.md) for detailed testing documentation.

## Runtime Flow: Garment Scan (v6)

1. **Mobile client** calls `POST /scan` with `garment_tag`
2. **Gateway** publishes `scan.requested` event to NATS
3. **Brain** (port 8000) resolves intent and `garment_id`
   - Calls `POST /policy/check` with X-Request-Id forwarding
4. **Policy** (port 8001) checks consent graph, returns decision + scope
   - Fetches owner consent from Identity service (port 8005)
   - Resolves scope: `private` | `friends_only` | `public`
   - If trust_score < 0.75 for non-public scopes → `escalate`
5. **Brain** routes based on policy decision:
   - **If `allow`**: Calls `POST /scan/commit` on Orchestrator
   - **If `escalate`**: Calls `POST /audit/escalate` on Compliance
   - **If `deny`**: Returns empty response
6. **Orchestrator** (port 8002) processes allowed scans:
   - **v6 fix**: Checks if `policy_decision == "escalate"` → returns `escalated_pending_human` WITHOUT anchoring
   - Fetches allowed facets from Knowledge Service (port 8003)
   - Writes `scan_event` row to database
   - Builds blockchain transactions (Cardano + Midnight + crosschain root)
   - Writes `chain_anchor` row to database
   - Calls Compliance `/audit/log` and `/audit/anchorChain`
7. **Knowledge** (port 8003) returns public-safe facets only
   - **v6 fix**: Always ignores requested scope, returns public previews only
   - NEVER returns pricing history, ownership lineage, or PII
8. **Compliance** (port 8004) logs with hash-chaining
   - **v6 fix**: Escalations are queryable by governance_console
   - Each audit log entry hashes: `prev_hash + decision_summary + decision_detail`
9. **Governance Console** (port 8006) allows human review
   - `GET /governance/escalations` - List pending escalations
   - `POST /governance/escalations/{scan_id}/decision` - Approve/deny
   - **TODO**: After approval, callback to Orchestrator to finalize anchoring
10. **Mobile client** receives allowed facets only (never private data)
11. **Transparency Portal** shows public proof without leaking private data

## Deployment

### Production Deployment to GKE

```bash
# Configure GCP project
gcloud config set project YOUR_PROJECT_ID

# Provision infrastructure
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

### CI/CD

GitHub Actions automatically:
- Builds Docker images for all services
- Runs tests and linters
- Pushes images to registry
- Deploys to GKE on tagged releases

See `.github/workflows/` for pipeline definitions.

## Contributing

### Code Standards
- TypeScript: ESLint + Prettier
- Python: Black + Ruff + MyPy
- All services must emit OpenTelemetry traces
- **No PII in logs** - Use `redact_user_id()` and `truncate_id()`
- Hash-chain all audit logs (SHA256 with UTF-8 encoding)
- **NEVER log sensitive data**: wallet_keys, purchase_history, ownership_lineage, facet bodies, DID secrets
- All FastAPI services use lifespan context managers for db_pool and http_client
- Every route must call `ensure_request_id()` for X-Request-Id propagation
- CORS middleware on public-facing services (brain, policy, knowledge, governance_console)

### v6 Security Guarantees
1. ✅ **Request Tracing**: X-Request-Id propagated across all service calls
2. ✅ **PII Redaction**: All user IDs truncated to 8 chars in logs
3. ✅ **Escalation Guardrails**: Orchestrator skips anchoring if policy_decision == "escalate"
4. ✅ **Safe Facet Previews**: Knowledge service always returns public-safe data only
5. ✅ **Hash-Chained Audit**: Every compliance log entry cryptographically linked
6. ✅ **Consent Graph**: Policy service enforces owner consent via Identity service
7. ✅ **Human Review**: Governance console provides escalation approval workflow

### Git Workflow
1. Create feature branch from `main`
2. Make changes with clear commit messages
3. Ensure all tests pass
4. Submit PR with description
5. Require 2 approvals for merge

## Organization

- **GitHub Org**: brandme-labs
- **Subsidiaries**:
  - brandme-intelligence
  - brandme-augmentation
  - brandme-chaintech

## License

Copyright (c) Brand.Me, Inc. All rights reserved.

Proprietary and confidential. Unauthorized copying or distribution is prohibited.

## Support

For questions or issues:
- Internal team: Slack #brandme-engineering
- Documentation: [docs/](./docs/)
- Architecture: [ARCHITECTURE.md](./ARCHITECTURE.md)
