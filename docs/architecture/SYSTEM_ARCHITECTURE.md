# Brand.Me Architecture Specification

**Copyright (c) Brand.Me, Inc. All rights reserved.**

## Table of Contents

1. [Mission & Compliance](#mission--compliance)
2. [System Architecture](#system-architecture)
3. [Service Specifications](#service-specifications)
4. [Data Model](#data-model)
5. [Runtime Flows](#runtime-flows)
6. [Security & Privacy](#security--privacy)
7. [Infrastructure](#infrastructure)
8. [Deployment](#deployment)

---

## Mission & Compliance

### North Star

**Verifiable identity, provenance, and cultural expression through fashion.**

### Integrity Definition

1. **Immutable provenance** for garments and creators
2. **Consent-driven visibility** for owners
3. **Auditability** for regulators
4. **No silent exposure** of private data

### Compliance Model

#### Privacy Layers

| Layer | Blockchain | Purpose | Data Types |
|-------|-----------|---------|------------|
| **Public** | Cardano | Provenance, ESG | Creator attribution, authenticity hash, ESG score |
| **Private** | Midnight | Ownership, Pricing | Ownership lineage, price history, consent snapshots |
| **Cross-Chain** | Both | Verification | Cryptographic link via root hash |

**Rule**: Public provenance and ESG anchors go to Cardano. Ownership lineage, pricing history, and consent snapshots go to Midnight.

#### Access Control Policies

- **Midnight Decrypt Policy**: `governance_humans_and_compliance_agent`
- **Transparency Portal**: Live, public (sanitized data only)
- **Default Region**: `us-east1` (extensible to other regions)

---

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Client Layer                               │
│                  (Mobile App, Web Browsers)                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTPS
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      brandme-gateway                                │
│        OAuth Authentication, Rate Limiting, NATS Publishing         │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         │ NATS JetStream (Event Bus)
                         │
         ┌───────────────┴────────────────┬──────────────────────┐
         │                                │                      │
         ▼                                ▼                      ▼
┌─────────────────────┐      ┌────────────────────┐   ┌──────────────────────┐
│   brandme-core      │      │  brandme-agents    │   │   brandme-chain      │
│                     │◄─────┤                    │   │                      │
│ - AI Brain Hub      │      │ - Identity Service │   │ - TX Builder         │
│ - Policy & Safety   │      │ - Knowledge/RAG    │   │   (Cardano+Midnight) │
│ - Orchestrator      │      │ - Compliance/Audit │   │ - Cross-Chain        │
│                     │──────►                    │   │   Verifier           │
└─────────────────────┘      └────────────────────┘   └──────────┬───────────┘
         │                            │                           │
         │                            │                           │
         ▼                            ▼                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Data & Blockchain Layer                         │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Cloud SQL        │  │   Cardano    │  │     Midnight       │  │
│  │ (PostgreSQL)     │  │ (Public L1)  │  │  (Private Chain)   │  │
│  └──────────────────┘  └──────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
         ▲
         │
         │
┌────────┴──────────────────────────────────────────────────────┐
│                    brandme-console                            │
│                                                               │
│  ┌─────────────────────────┐  ┌──────────────────────────┐  │
│  │ Governance Console      │  │ Transparency Portal      │  │
│  │ (Internal, RBAC)        │  │ (Public)                 │  │
│  └─────────────────────────┘  └──────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

### Communication Patterns

1. **Synchronous HTTP/REST**: Client → Gateway, Service-to-Service
2. **Asynchronous Events**: Gateway → NATS → Core Services
3. **Database Access**: Services → Cloud SQL via connection pools
4. **Blockchain Transactions**: Services → brandme-chain → Cardano/Midnight

---

## Service Specifications

### 1. brandme-gateway

**Language**: Node.js + TypeScript
**Role**: Edge API gateway, OAuth intake, NATS event publisher

#### Endpoints

##### POST /scan

**Authentication**: OAuth JWT
**Request Body**:
```json
{
  "garment_tag": "string"
}
```

**Behavior**:
1. Extract `scanner_user_id` from JWT
2. Attach `region_code` (default: `us-east1`)
3. Generate `scan_id` (UUID)
4. Publish event to NATS subject `scan.requested`:
   ```json
   {
     "scan_id": "uuid",
     "scanner_user_id": "uuid",
     "garment_tag": "string",
     "timestamp": "ISO8601",
     "region_code": "us-east1"
   }
   ```
5. Return `202 Accepted` with `scan_id`

**Response**:
```json
{
  "scan_id": "uuid",
  "status": "processing"
}
```

##### GET /healthz

**Authentication**: None
**Response**:
```json
{
  "status": "ok"
}
```

#### Infrastructure

- **Proxy Layer**: Nginx or Envoy (config in `/gateway/`)
- **Helm Chart**: `brandme-gateway`
- **Rate Limiting**: Enabled
- **Environment Variables**:
  - `OAUTH_CLIENT_ID`
  - `OAUTH_CLIENT_SECRET`
  - `DEFAULT_REGION`
  - `NATS_URL`
- **Headers**: Attach `X-Region` to downstream calls

---

### 2. brandme-core

**Language**: Python + FastAPI (API) + Celery (workers)
**Role**: AI Brain Hub, Policy & Safety, Task Orchestrator

#### 2.1 AI Brain Hub

**Endpoint**: `POST /intent/resolve`

**Input**:
```json
{
  "scan_id": "uuid",
  "scanner_user_id": "uuid",
  "garment_tag": "string",
  "region_code": "us-east1"
}
```

**Output**:
```json
{
  "action": "request_passport_view",
  "garment_id": "uuid",
  "scanner_user_id": "uuid"
}
```

**Logic**:
- Lookup `garment_id` by `garment_tag` via knowledge service or cache
- Return normalized intent struct

**Logging Rule**: Trace ID only, no PII

---

#### 2.2 Policy & Safety

**Endpoint**: `POST /policy/check`

**Input**:
```json
{
  "scanner_user_id": "uuid",
  "garment_id": "uuid",
  "region_code": "us-east1",
  "action": "request_passport_view"
}
```

**Output**:
```json
{
  "decision": "allow|deny|escalate",
  "resolved_scope": "public|friends_only|private",
  "policy_version": "sha256_hash"
}
```

**Logic**:
1. Fetch `current_owner_id` and `consent_policies` for `garment_id`
2. Map `scanner_user_id` → `current_owner_id` to relationship scope:
   - `public`: Anyone can view
   - `friends_only`: Only connected users
   - `private`: Only owner
3. Check `region_code` for legal restrictions
4. If unclear or risky → `decision: 'escalate'`

**Requirements**:
- Hash policy version
- Write audit stub

---

#### 2.3 Orchestrator (Celery Worker)

**Input Queue**: Events from Policy & Safety when `decision == 'allow'`

**Responsibilities**:
1. Insert row into `scan_event` table
2. Call `knowledge_service` to fetch allowed facets for `resolved_scope`
3. Call `brandme-chain` `/tx/anchor-scan`
4. Call `compliance_audit_service` `/audit/log` and `/audit/anchorChain`
5. Update `chain_anchor` with transaction hashes

#### Infrastructure

- **Helm Charts**: Separate charts for each service
- **Environment Variables**:
  - `DATABASE_URL`
  - `NATS_URL`
  - `REGION_DEFAULT`
- **Policy Storage**: `policies/region/*.yaml` (committed in repo)
- **Telemetry**: OpenTelemetry tracing on all endpoints

---

### 3. brandme-agents

**Language**: Python + FastAPI
**Role**: Supporting agent services (Identity, Knowledge/RAG, Compliance & Audit)

#### 3.1 Identity Service

**Endpoint**: `GET /user/{user_id}/persona`

**Output**:
```json
{
  "persona_warm_cold": 0.75,
  "persona_sport_couture": 0.60,
  "trust_score": 95.50,
  "region_code": "us-east1",
  "did_cardano": "did:cardano:abc123" // nullable
}
```

**DB Reads**: `users`

---

#### 3.2 Knowledge Service

**Endpoint**: `GET /garment/{garment_id}/passport?scope=public|friends_only|private`

**Output**:
```json
[
  {
    "facet_type": "authenticity",
    "facet_payload_preview": { "status": "verified", "hash": "..." }
  },
  {
    "facet_type": "esg_score",
    "facet_payload_preview": { "score": "A+", "details": "..." }
  }
]
```

**Logic**:
- Join `garments` + `garment_passport_facets` + `consent_policies`
- Filter facets by `resolved_scope`
- **NEVER** include Midnight-private `facet_payload` when scope is `public`

**DB Reads**: `garments`, `garment_passport_facets`, `consent_policies`

---

#### 3.3 Compliance & Audit Service

##### POST /audit/log

**Input**:
```json
{
  "scan_id": "uuid",
  "decision_summary": "string",
  "decision_detail": {},
  "risk_flagged": false,
  "escalated_to_human": false
}
```

**Behavior**:
- Insert `audit_log` row
- **Hash-chain**: Each new row's `entry_hash` references `prev_hash`

---

##### POST /audit/anchorChain

**Input**:
```json
{
  "scan_id": "uuid",
  "cardano_tx_hash": "string",
  "midnight_tx_hash": "string",
  "crosschain_root_hash": "string"
}
```

**Behavior**:
- Create or update `chain_anchor` row
- Update `audit_log` for `scan_id` with chain linkage

---

##### GET /audit/{scan_id}/explain

**Output**:
```json
{
  "human_readable_explanation": "User A scanned garment B...",
  "cardano_tx_hash": "string",
  "midnight_tx_hash": "string",
  "crosschain_root_hash": "string",
  "policy_version": "sha256_hash",
  "resolved_scope": "public"
}
```

**Visibility**:
- **Governance Console**: Full access (RBAC)
- **Regulator Portal**: Read-only, sanitized

#### Infrastructure

- **Helm Charts**: Separate per service
- **DB Access**: Cloud SQL via `DATABASE_URL`
- **Telemetry**: OpenTelemetry auto-instrumentation
- **RBAC Roles**: `ROLE_GOVERNANCE`, `ROLE_COMPLIANCE`, `ROLE_REGULATOR_VIEW`

---

### 4. brandme-chain

**Language**: Node.js + TypeScript
**Role**: TX Builder (Cardano + Midnight), Cross-Chain Verifier

#### Endpoints

##### POST /tx/anchor-scan

**Input**:
```json
{
  "scan_id": "uuid",
  "garment_id": "uuid",
  "allowed_facets": [],
  "resolved_scope": "public",
  "policy_version": "sha256_hash"
}
```

**Output**:
```json
{
  "cardano_tx_hash": "string",
  "midnight_tx_hash": "string",
  "crosschain_root_hash": "string"
}
```

**Behavior**:
1. Build **Cardano payload**: Creator attribution, authenticity hash, ESG proof
2. Build **Midnight payload**: Ownership lineage ref, pricing ref, consent snapshot
3. Generate `crosschain_root_hash` linking both chains
4. **DO NOT** log private keys
5. Return transaction hashes

---

##### POST /tx/verify-root

**Input**:
```json
{
  "crosschain_root_hash": "string"
}
```

**Output**:
```json
{
  "is_consistent": true
}
```

#### Infrastructure

- **Helm Chart**: `brandme-chain`
- **Secrets**: Kubernetes secret mounts (not in repo)
  - `CARDANO_WALLET_KEY`
  - `MIDNIGHT_WALLET_KEY`
- **CI/CD**: GitHub Actions → Build → Push container
- **Notes**:
  - Include TODO for DID mint step at account creation
  - Never expose Midnight-private facet contents

---

### 5. brandme-console

**Language**: Next.js + React + Tailwind CSS
**Role**: Governance Console (internal) + Transparency Portal (public)

#### 5.1 Governance Console

**Authentication**: RBAC (`ROLE_GOVERNANCE`, `ROLE_COMPLIANCE`)

**Pages**:
- `/dashboard/scans` - List all scans
- `/dashboard/scan/[scan_id]` - Detailed scan view
- `/dashboard/escalations` - Flagged scans requiring human review
- `/dashboard/reveal` - Controlled Midnight facet reveal

**Data Sources**:
- `GET /audit/{scan_id}/explain` from compliance_audit_service
- `scan_event` table via internal API
- `chain_anchor` table via internal API

**Requirements**:
- Display `decision_summary` and `policy_version` for each scan
- Show `cardano_tx_hash`, `midnight_tx_hash`, `crosschain_root_hash`
- Support controlled Midnight facet reveal with **dual approval**:
  - Governance human + Compliance agent
- Every reveal action POSTs back to `compliance_audit_service`
- Writes hash-chained `audit_log`

---

#### 5.2 Transparency Portal (Public)

**Authentication**: Public (no login required)

**Pages**:
- `/proof/[scan_id]` - Public proof view

**Output**:
- Authenticity status (real/counterfeit)
- Creator attribution
- ESG proof hash summary
- Policy version used
- **NO** private Midnight data

#### Infrastructure

- **Helm Chart**: `brandme-console`
- **Ingress**:
  - Public ingress for Transparency Portal
  - Private ingress for Governance Console
- **Environment Variables**:
  - `COMPLIANCE_AUDIT_SERVICE_URL`
  - `IDENTITY_SERVICE_URL`

---

## Data Model

### Database: Cloud SQL (PostgreSQL)

#### Tables

##### users
```sql
CREATE TABLE users (
  user_id UUID PRIMARY KEY,
  handle TEXT UNIQUE NOT NULL,
  display_name TEXT,
  did_cardano TEXT NULL, -- Future: Cardano DID
  region_code TEXT,
  persona_warm_cold NUMERIC(3,2),
  persona_sport_couture NUMERIC(3,2),
  trust_score NUMERIC(6,2),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

##### garments
```sql
CREATE TABLE garments (
  garment_id UUID PRIMARY KEY,
  creator_id UUID REFERENCES users(user_id),
  current_owner_id UUID REFERENCES users(user_id),
  display_name TEXT NOT NULL,
  category TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  cardano_asset_ref TEXT,
  authenticity_hash TEXT,
  public_esg_score TEXT,
  public_story_snippet TEXT
);
```

##### garment_passport_facets
```sql
CREATE TABLE garment_passport_facets (
  facet_id UUID PRIMARY KEY,
  garment_id UUID REFERENCES garments(garment_id),
  facet_type TEXT, -- e.g., 'authenticity', 'esg', 'ownership', 'pricing'
  facet_payload JSONB,
  is_public_default BOOLEAN NOT NULL DEFAULT FALSE,
  midnight_ref TEXT, -- Reference to Midnight chain data
  cardano_ref TEXT, -- Reference to Cardano chain data
  last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

##### consent_policies
```sql
CREATE TABLE consent_policies (
  policy_id UUID PRIMARY KEY,
  garment_id UUID REFERENCES garments(garment_id),
  visibility_scope TEXT, -- 'public', 'friends_only', 'private'
  facet_type TEXT, -- Which facet this policy applies to
  allowed BOOLEAN,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

##### scan_event
```sql
CREATE TABLE scan_event (
  scan_id UUID PRIMARY KEY,
  scanner_user_id UUID REFERENCES users(user_id),
  garment_id UUID REFERENCES garments(garment_id),
  occurred_at TIMESTAMPTZ DEFAULT NOW(),
  resolved_scope TEXT, -- 'public', 'friends_only', 'private'
  policy_version TEXT, -- SHA256 hash of policy used
  region_code TEXT,
  shown_facets JSONB -- Array of facets shown to scanner
);
```

##### chain_anchor
```sql
CREATE TABLE chain_anchor (
  anchor_id UUID PRIMARY KEY,
  scan_id UUID REFERENCES scan_event(scan_id),
  cardano_tx_hash TEXT,
  cardano_payload_ref TEXT,
  midnight_tx_hash TEXT,
  midnight_payload_ref TEXT,
  crosschain_root_hash TEXT, -- Links Cardano and Midnight
  anchored_at TIMESTAMPTZ DEFAULT NOW()
);
```

##### audit_log
```sql
CREATE TABLE audit_log (
  audit_id UUID PRIMARY KEY,
  related_scan_id UUID REFERENCES scan_event(scan_id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  actor_type TEXT, -- 'system', 'governance_human', 'compliance_agent'
  decision_summary TEXT,
  decision_detail JSONB,
  risk_flagged BOOLEAN DEFAULT FALSE,
  escalated_to_human BOOLEAN DEFAULT FALSE,
  human_approver_id UUID NULL REFERENCES users(user_id),
  prev_hash TEXT NULL, -- Hash-chain: previous audit_log entry_hash
  entry_hash TEXT NOT NULL -- Hash of current entry
);
```

---

## Runtime Flows

### Garment Scan Flow

```
┌─────────┐
│ Mobile  │
│ Client  │
└────┬────┘
     │ POST /scan {garment_tag}
     ▼
┌─────────────────┐
│ brandme-gateway │
│  - Validate JWT │
│  - Gen scan_id  │
│  - Publish NATS │
└────┬────────────┘
     │ NATS: scan.requested
     ▼
┌──────────────────────┐
│ brandme-core         │
│  AI Brain Hub        │
│  - Resolve garment_id│
└────┬─────────────────┘
     │
     ▼
┌──────────────────────┐
│ Policy & Safety      │
│  - Check consent     │
│  - Check region      │
│  - Return decision   │
└────┬─────────────────┘
     │ decision: allow
     ▼
┌──────────────────────┐
│ Orchestrator         │
│  - Write scan_event  │
│  - Fetch facets      │
│  - Call TX Builder   │
│  - Log audit         │
└────┬─────────────────┘
     │
     ├─────────────────────┐
     │                     │
     ▼                     ▼
┌─────────────────┐  ┌────────────────┐
│ brandme-chain   │  │ Compliance     │
│  - Anchor       │  │ & Audit        │
│    Cardano      │  │  - Hash-chain  │
│  - Anchor       │  │    audit_log   │
│    Midnight     │  └────────────────┘
│  - Gen root hash│
└─────────────────┘
     │
     ▼
┌─────────────────────────┐
│ Return allowed facets   │
│ to Mobile Client        │
│ (NO private data)       │
└─────────────────────────┘
```

### Escalation & Reveal Flow

```
┌──────────────────────┐
│ Governance Console   │
│  - View flagged scan │
│  - Request reveal    │
└────┬─────────────────┘
     │
     ▼
┌──────────────────────┐
│ Dual Approval Check  │
│  - Governance human  │
│  - Compliance agent  │
└────┬─────────────────┘
     │ Both approved
     ▼
┌──────────────────────┐
│ Compliance & Audit   │
│  - Decrypt Midnight  │
│    facet (controlled)│
│  - Write audit_log   │
│  - Hash-chain entry  │
└────┬─────────────────┘
     │
     ▼
┌──────────────────────┐
│ Display private data │
│ to authorized user   │
└──────────────────────┘
```

---

## Security & Privacy

### Hard Guarantees

1. **Policy & Safety MUST run before any reveal**
   - No data is shown without explicit consent check
   - Region-specific compliance rules enforced

2. **TX Builder is the ONLY path to blockchain writes**
   - No direct blockchain access from other services
   - Centralized wallet management

3. **Compliance & Audit MUST hash-chain every decision**
   - Every audit log entry references previous entry's hash
   - Tamper-evident audit trail

4. **Governance Console MUST enforce dual approval for Midnight reveals**
   - Human governance approval required
   - Compliance agent verification required
   - Both must agree before decrypt

5. **Transparency Portal MUST NOT leak private data**
   - Only public Cardano data shown
   - No Midnight references exposed

### Secrets Management

- **Wallet Keys**: Stored ONLY in Kubernetes secrets
- **No Plaintext in Repo**: Use `.env.example` templates only
- **No Logging of Secrets**: Sanitize all logs
- **No PII in Logs**: Trace IDs only, never personal data

### Data Privacy Layers

| Data Type | Storage | Visibility | Blockchain |
|-----------|---------|------------|------------|
| Creator Attribution | PostgreSQL + Cardano | Public | Cardano |
| Authenticity Hash | PostgreSQL + Cardano | Public | Cardano |
| ESG Score | PostgreSQL + Cardano | Public | Cardano |
| Ownership Lineage | PostgreSQL + Midnight | Private | Midnight |
| Pricing History | PostgreSQL + Midnight | Private | Midnight |
| Consent Policies | PostgreSQL + Midnight | Private | Midnight |

---

## Infrastructure

### Google Cloud Platform (GCP)

#### Core Services

- **GKE (Kubernetes)**: Container orchestration
- **Cloud SQL (PostgreSQL)**: Relational database
- **GCS**: Object storage for garment passport blobs
- **VPC**: Network isolation
- **Workload Identity**: Service account management

#### Observability

- **OpenTelemetry**: Distributed tracing
- **Prometheus**: Metrics collection
- **Grafana**: Visualization
- **Loki**: Log aggregation

#### Event Bus

- **NATS JetStream**: Event streaming on GKE

### Deployment Regions

- **Primary**: `us-east1`
- **Future**: Multi-region (extensible)

### Scaling Goal

**Planetary billion-user scale**

---

## Deployment

### Terraform (Infrastructure)

```hcl
# brandme-infra/terraform/main.tf

module "gke_cluster" {
  source = "./modules/gke"
  region = "us-east1"
}

module "cloud_sql" {
  source = "./modules/cloudsql"
  region = "us-east1"
}

module "gcs_bucket" {
  source = "./modules/gcs"
  bucket_name = "brandme-passport-blobs"
}

module "vpc" {
  source = "./modules/vpc"
}
```

### Helm (Services)

```yaml
# brandme-infra/helm/brandme-umbrella/values.yaml

gateway:
  image: gcr.io/brandme/gateway:latest
  replicas: 3
  env:
    OAUTH_CLIENT_ID: "..."
    NATS_URL: "nats://nats:4222"

core:
  brain:
    image: gcr.io/brandme/core-brain:latest
  policy:
    image: gcr.io/brandme/core-policy:latest
  orchestrator:
    image: gcr.io/brandme/core-orchestrator:latest

agents:
  identity:
    image: gcr.io/brandme/agent-identity:latest
  knowledge:
    image: gcr.io/brandme/agent-knowledge:latest
  compliance:
    image: gcr.io/brandme/agent-compliance:latest

chain:
  image: gcr.io/brandme/chain:latest
  secrets:
    - CARDANO_WALLET_KEY
    - MIDNIGHT_WALLET_KEY

console:
  governance:
    image: gcr.io/brandme/console-governance:latest
  portal:
    image: gcr.io/brandme/console-portal:latest
```

### CI/CD (GitHub Actions)

```yaml
# .github/workflows/deploy.yml

name: Build and Deploy

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build Docker images
        run: make build-all
      - name: Push to registry
        run: make push-all

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to GKE
        run: |
          helm upgrade --install brandme \
            ./brandme-infra/helm/brandme-umbrella \
            --namespace brandme
```

---

## Future Enhancements

### Identity & Auth

- **Cardano DID**: Mint DIDs at account creation
- **Magic Link**: Passwordless authentication
- **Multi-Factor Auth**: Enhanced security for governance roles

### Regional Expansion

- **EU Region**: GDPR compliance
- **APAC Region**: Data residency
- **Multi-Cloud**: AWS, Azure fallbacks

### AI & ML

- **Persona Learning**: Adaptive warm/cold, sport/couture scoring
- **Fraud Detection**: ML models for counterfeit detection
- **Recommendation Engine**: Personalized garment suggestions

---

**Document Version**: 1.0.0
**Last Updated**: 2025-10-25
**Maintained By**: Brand.Me Engineering
