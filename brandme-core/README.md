# brandme-core

**Copyright (c) Brand.Me, Inc. All rights reserved.**

AI Brain Hub, Policy & Safety Engine, and Task Orchestrator for Brand.Me platform.

## Overview

This repository contains three core services:

1. **AI Brain Hub** (`/brain`) - Intent resolution and AI-driven decision making
2. **Policy & Safety** (`/policy`) - Consent checking, policy enforcement, and safety validation
3. **Orchestrator** (`/orchestrator`) - Task coordination and workflow management (Celery workers)

## Services

### 1. AI Brain Hub

**Port**: 8000
**Endpoint**: `POST /intent/resolve`

Resolves user intent from scan requests and maps garment tags to garment IDs.

### 2. Policy & Safety

**Port**: 8001
**Endpoint**: `POST /policy/check`

Validates consent policies, checks regional restrictions, and determines visibility scope.

### 3. Orchestrator

**Type**: Celery Worker

Coordinates workflows:
- Inserts scan events
- Fetches allowed facets
- Calls blockchain TX builder
- Logs audit trails

## Development

### Prerequisites

- Python 3.11+
- PostgreSQL
- Redis (for Celery)
- NATS Server

### Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy environment variables
cp .env.example .env
```

### Running Services

```bash
# AI Brain Hub
cd brain && uvicorn main:app --reload --port 8000

# Policy & Safety
cd policy && uvicorn main:app --reload --port 8001

# Orchestrator (Celery worker)
cd orchestrator && celery -A worker worker --loglevel=info
```

### Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Lint
ruff check src/
black --check src/

# Format
black src/ tests/
ruff check --fix src/
```

## Architecture

```
┌──────────────────────┐
│   NATS JetStream     │
│  scan.requested      │
└─────────┬────────────┘
          │
          ▼
┌─────────────────────┐      ┌──────────────────────┐
│   AI Brain Hub      │─────▶│  Policy & Safety     │
│  - Resolve intent   │      │  - Check consent     │
│  - Lookup garment   │      │  - Validate region   │
└─────────────────────┘      └──────────┬───────────┘
                                        │ decision: allow
                                        ▼
                             ┌─────────────────────┐
                             │   Orchestrator      │
                             │  - Insert scan      │
                             │  - Fetch facets     │
                             │  - Call TX Builder  │
                             │  - Log audit        │
                             └─────────────────────┘
```

## Database Models

Shared database models in `/shared/models/`:
- `User`
- `Garment`
- `GarmentPassportFacet`
- `ConsentPolicy`
- `ScanEvent`
- `ChainAnchor`
- `AuditLog`

## Configuration

Environment variables:
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string (for Celery)
- `NATS_URL`: NATS server URL
- `REGION_DEFAULT`: Default region code
- `LOG_LEVEL`: Logging level

## Policy Storage

Policies are stored in `policies/region/*.yaml`:

```yaml
# policies/region/us-east1.yaml
region_code: us-east1
policies:
  - scope: public
    facet_types:
      - authenticity
      - esg
    allowed: true
  - scope: private
    facet_types:
      - pricing
      - ownership
    allowed: false
```

## Compliance

- **No PII in logs**: All logging sanitizes personally identifiable information
- **Trace ID only**: Log correlation uses trace IDs, not user data
- **Policy versioning**: All policy decisions include SHA256 hash of policy version
- **Audit trail**: Every decision is logged with tamper-evident hash chain

## Deployment

### Docker

```bash
# Build images
docker build -t brandme-core-brain:latest -f brain/Dockerfile .
docker build -t brandme-core-policy:latest -f policy/Dockerfile .
docker build -t brandme-core-orchestrator:latest -f orchestrator/Dockerfile .
```

### Kubernetes

Each service has a Helm chart in `/brandme-infra/helm/`.

## License

Copyright (c) Brand.Me, Inc. All rights reserved.

Proprietary and confidential.
