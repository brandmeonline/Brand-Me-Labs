# Brand.Me Labs

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Brand.Me is a symbiotic intelligence platform that merges digital fashion, identity expression, and verifiable trust on the Cardano blockchain. It is designed to redefine ownership, authenticity, and culture through agentic intelligence—where autonomous systems handle precision and scale, and humans govern intent, empathy, and ethics.

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
- **brandme-core**: AI Brain Hub, Policy Engine (Python/FastAPI)
- **brandme-agents**: Supporting agent services (Python/FastAPI)
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

# Run database migrations
make db-migrate

# Seed development data
make db-seed

# Run tests
make test
```

### Environment Configuration

Each service requires environment variables. See `.env.example` files in each service directory:

- `brandme-gateway/.env.example`
- `brandme-core/.env.example`
- `brandme-agents/.env.example`
- `brandme-chain/.env.example`
- `brandme-console/.env.example`

**IMPORTANT**: Never commit secrets or wallet keys. Use Kubernetes secrets in production.

## Runtime Flow: Garment Scan

1. **Mobile client** calls `POST /scan` with `garment_tag`
2. **Gateway** publishes `scan.requested` event to NATS
3. **AI Brain Hub** resolves intent and `garment_id`
4. **Policy & Safety** checks consent, region, and returns decision + scope
5. **Orchestrator** (if allowed):
   - Writes `scan_event` row
   - Fetches allowed facets from Knowledge Service
   - Calls TX Builder to anchor to Cardano + Midnight
   - Logs audit trail with hash-chain
6. **Mobile client** receives allowed facets only (never private data)
7. **Governance Console** can view scan and request selective reveals
8. **Transparency Portal** shows public proof without leaking private data

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
- No PII in logs
- Hash-chain all audit logs

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
