# Brand.Me Architecture Specification (v9)

**Copyright (c) Brand.Me, Inc. All rights reserved.**

## v9 Release: 2030 Agentic & Circular Economy

**Version 9** builds on the Global Integrity Spine with features for the 2030 circular economy:

- **Google Cloud Spanner**: Native Property Graph (GQL), O(1) consent lookups, Material tracking
- **Firestore**: Real-time wardrobe state, Biometric Sync for AR glasses (<100ms)
- **Model Context Protocol (MCP)**: External agent access to Style Vault
- **DPP Lifecycle State Machine**: PRODUCED → ACTIVE → REPAIR → DISSOLVE → REPRINT
- **Zero-Knowledge Proofs**: Proof of ownership for AR glasses without exposing private keys
- **ESG Verification**: Cardano oracle for ethical oversight of agentic transactions
- **Midnight Integration**: Burn proofs for circular economy material verification
# Brand.Me Architecture Specification (v8)

**Copyright (c) Brand.Me, Inc. All rights reserved.**

## v8 Release: Global Integrity Spine

**Version 8** introduces a dual-database production stack replacing PostgreSQL:

- **Google Cloud Spanner**: Global consistency, Consent Graph, O(1) provenance lookups
- **Firestore**: Real-time wardrobe state, edge caching, agentic state broadcasting

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

### High-Level Components (v8)

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
│ - Cube Service      │──────►                    │   │   Verifier           │
└─────────────────────┘      └────────────────────┘   └──────────┬───────────┘
         │                            │                           │
         ▼                            ▼                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DATA LAYER (v8)                                │
│  ┌──────────────────────────┐  ┌──────────────────────────┐       │
│  │    Google Cloud Spanner  │  │       Firestore          │       │
│  │                          │  │                          │       │
│  │  • Users (node)          │  │  • /wardrobes/{user_id}  │       │
│  │  • Assets (node)         │  │    └─ /cubes/{cube_id}   │       │
│  │  • Owns (edge)           │  │       └─ faces, state    │       │
│  │  • Created (edge)        │  │                          │       │
│  │  • FriendsWith (edge)    │  │  • /agent_sessions/      │       │
│  │  • ConsentPolicies       │  │                          │       │
│  │  • ProvenanceChain       │  │  Real-time listeners     │       │
│  │                          │  │  for frontend updates    │       │
│  │  O(1) consent lookups    │  │  Agentic state sync      │       │
│  └──────────────────────────┘  └──────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
         │                                    │
         ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BLOCKCHAIN LAYER                                 │
│  ┌──────────────────────┐  ┌──────────────────────┐               │
│  │      Cardano         │  │      Midnight        │               │
│  │   (Public Chain)     │  │   (Private Chain)    │               │
│  │  • Provenance        │  │  • Ownership         │               │
│  │  • ESG anchors       │  │  • Pricing history   │               │
│  │  • Creator credits   │  │  • Consent proofs    │               │
│  └──────────────────────┘  └──────────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
         ▲
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

## Data Model (v8)

### Primary Database: Google Cloud Spanner

v8 uses Spanner Graph DDL for O(1) consent lookups. See `brandme-data/spanner/schema.sql` for full DDL.

#### Node Tables


### Primary Database: Google Cloud Spanner

v8 uses Spanner Graph DDL for O(1) consent lookups. See `brandme-data/spanner/schema.sql` for full DDL.

#### Node Tables

##### Users
```sql
CREATE TABLE Users (
  user_id STRING(36) NOT NULL,
  handle STRING(64) NOT NULL,
  display_name STRING(256),
  region_code STRING(16),
  trust_score FLOAT64,
  consent_version STRING(64),
  is_active BOOL NOT NULL DEFAULT (true),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at TIMESTAMP OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (user_id);
```

##### Assets
```sql
CREATE TABLE Assets (
  asset_id STRING(36) NOT NULL,
  asset_type STRING(32) NOT NULL,  -- 'cube', 'garment', etc.
  display_name STRING(256) NOT NULL,
  creator_user_id STRING(36) NOT NULL,
  current_owner_id STRING(36) NOT NULL,
  authenticity_hash STRING(128),
  is_active BOOL NOT NULL DEFAULT (true),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (asset_id);
```

#### Edge Tables (Graph Relationships)

##### Owns (Owner → Asset)
```sql
CREATE TABLE Owns (
  owner_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  acquired_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  transfer_method STRING(32),  -- 'mint', 'purchase', 'gift', 'transfer'
  is_current BOOL NOT NULL DEFAULT (true),
  FOREIGN KEY (owner_id) REFERENCES Users(user_id),
  FOREIGN KEY (asset_id) REFERENCES Assets(asset_id),
) PRIMARY KEY (owner_id, asset_id);
```

##### FriendsWith (User ↔ User)
```sql
CREATE TABLE FriendsWith (
  user_id_1 STRING(36) NOT NULL,
  user_id_2 STRING(36) NOT NULL,
  status STRING(16) NOT NULL DEFAULT 'pending',  -- 'pending', 'accepted', 'blocked'
  initiated_by STRING(36),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (user_id_1) REFERENCES Users(user_id),
  FOREIGN KEY (user_id_2) REFERENCES Users(user_id),
) PRIMARY KEY (user_id_1, user_id_2);
```

#### Supporting Tables

##### ConsentPolicies
```sql
CREATE TABLE ConsentPolicies (
  consent_id STRING(36) NOT NULL,
  user_id STRING(36) NOT NULL,
  asset_id STRING(36),  -- NULL = global policy
  scope STRING(32) NOT NULL,  -- 'global', 'asset', 'facet'
  visibility STRING(32) NOT NULL,  -- 'public', 'friends_only', 'private'
  is_revoked BOOL NOT NULL DEFAULT (false),
  revoked_at TIMESTAMP,
  revoke_reason STRING(256),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (user_id) REFERENCES Users(user_id),
) PRIMARY KEY (consent_id);
```

##### ProvenanceChain (Interleaved)
```sql
CREATE TABLE ProvenanceChain (
  provenance_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  sequence_num INT64 NOT NULL,
  from_user_id STRING(36),
  to_user_id STRING(36) NOT NULL,
  transfer_type STRING(32) NOT NULL,  -- 'mint', 'purchase', 'gift', 'transfer'
  price FLOAT64,
  currency STRING(8),
  transfer_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  tx_hash STRING(128),
  FOREIGN KEY (asset_id) REFERENCES Assets(asset_id),
) PRIMARY KEY (asset_id, sequence_num),
  INTERLEAVE IN PARENT Assets ON DELETE CASCADE;
```

#### Graph Definition

```sql
CREATE OR REPLACE PROPERTY GRAPH IntegritySpineGraph
  NODE TABLES (
    Users,
    Assets
  )
  EDGE TABLES (
    Owns
      SOURCE KEY (owner_id) REFERENCES Users(user_id)
      DESTINATION KEY (asset_id) REFERENCES Assets(asset_id)
      LABEL OWNS,
    FriendsWith
      SOURCE KEY (user_id_1) REFERENCES Users(user_id)
      DESTINATION KEY (user_id_2) REFERENCES Users(user_id)
      LABEL FRIENDS_WITH
  );
```

### Real-Time State: Firestore

#### Collections

- `/wardrobes/{user_id}` - User wardrobe metadata
  - `/cubes/{cube_id}` - Cube state, faces, visibility
- `/agent_sessions/{session_id}` - Agentic modification tracking

#### Wardrobe Document Schema
```json
{
  "owner_id": "uuid",
  "display_name": "User's Wardrobe",
  "total_cubes": 5,
  "last_modified": "timestamp",
  "settings": {
    "default_visibility": "friends_only"
  }
}
```

#### Cube Document Schema
```json
{
  "cube_id": "uuid",
  "owner_id": "uuid",
  "agentic_state": "idle|processing|modified|syncing|error",
  "faces": {
    "product_details": {
      "data": {...},
      "visibility": "public",
      "pending_sync": false
    }
  },
  "visibility_settings": {...},
  "spanner_synced_at": "timestamp"
}
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

## Infrastructure (v8)

### Google Cloud Platform (GCP)

#### Core Services

- **GKE (Kubernetes)**: Container orchestration
- **Google Cloud Spanner**: Global consistency database (source of truth)
- **Firestore**: Real-time wardrobe state, edge caching
- **GCS**: Object storage for garment passport blobs
- **VPC**: Network isolation
- **Workload Identity**: Service account management

#### Database Libraries

- **Spanner**: `google-cloud-spanner` with PingingPool
- **Firestore**: `google-cloud-firestore` with async client
- **Legacy**: `asyncpg` (deprecated, kept for migration)

#### Observability

- **OpenTelemetry**: Distributed tracing
- **Prometheus**: Metrics collection
- **Grafana**: Visualization
- **Loki**: Log aggregation

#### Event Bus

- **NATS JetStream**: Event streaming on GKE

### Local Development with Emulators

```bash
# Start local development environment
docker-compose up -d

# This starts:
# - Spanner Emulator (ports 9010, 9020)
# - Firestore Emulator (port 8080)
# - All 8 backend services

# Run tests against emulators
pytest tests/ -v
```

### Deployment Regions

- **Primary**: `us-east1`
- **Future**: Multi-region via Spanner

### Scaling Goal

**Planetary billion-user scale** via Spanner global consistency

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

---

## v8 Production Readiness

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

---

**Document Version**: 9.0.0
**Document Version**: 8.0.0
**Last Updated**: January 2026
**Maintained By**: Brand.Me Engineering

---

## v9 New Features

### 1. Product Cube (7 Faces)

v9 adds a seventh face to the Product Cube:

| Face | Purpose | v9 Changes |
|------|---------|------------|
| product_details | Immutable product info | - |
| provenance | Append-only journey | - |
| ownership | Current owner | - |
| social_layer | Ratings, reviews | - |
| esg_impact | ESG scores | Cardano oracle verification |
| lifecycle | Durability, repair | DPP state machine |
| **molecular_data** | **NEW: Material tracking** | Material composition, dissolve auth |

### 2. DPP Lifecycle State Machine

```
PRODUCED → ACTIVE → REPAIR → ACTIVE
                  ↘ DISSOLVE → REPRINT → PRODUCED
```

Valid transitions:
- PRODUCED → ACTIVE (item enters circulation)
- ACTIVE → REPAIR (item needs repair)
- ACTIVE → DISSOLVE (owner authorizes material recovery)
- REPAIR → ACTIVE (repair complete)
- REPAIR → DISSOLVE (beyond repair)
- DISSOLVE → REPRINT (materials used in new product)
- REPRINT → PRODUCED (new product enters circulation)

### 3. MCP (Model Context Protocol)

External agents can access the Style Vault through MCP tools:

```json
{
  "tools": [
    {"name": "search_wardrobe", "category": "search"},
    {"name": "get_cube_details", "category": "view"},
    {"name": "suggest_outfit", "category": "style"},
    {"name": "initiate_rental", "category": "transaction", "requires_esg_check": true},
    {"name": "list_for_resale", "category": "transaction", "requires_esg_check": true},
    {"name": "request_repair", "category": "lifecycle"},
    {"name": "request_dissolve", "category": "lifecycle", "requires_esg_check": true}
  ]
}
```

All transaction tools require:
- User consent (stored in ConsentedByAgent table)
- ESG verification from Cardano oracle
- Optional human approval for high-value transactions

### 4. ZK Proof of Ownership

AR glasses verify ownership without exposing private keys:

```
User Phone                    AR Glasses
     │                             │
     ├───── Generate ZK Proof ─────►
     │      (ownership proof)      │
     │                             ├── Verify locally
     │                             │   (no private key)
     │                             ▼
     │                        Display overlay
```

Endpoints:
- `POST /identity/{user_id}/zk/generate` - Generate proof
- `POST /identity/{user_id}/zk/verify` - Verify proof
- `GET /identity/{user_id}/zk/proofs` - List active proofs
- `DELETE /identity/{user_id}/zk/proofs` - Invalidate after transfer

### 5. Biometric Sync

Firestore collection for AR glasses real-time sync (<100ms target):

```json
{
  "user_id": "uuid",
  "cube_id": "uuid",
  "active_facet": {
    "face_name": "product_details",
    "display_mode": "overlay",
    "sync_timestamp": "2026-01-20T12:00:00Z"
  },
  "biometric_data": {
    "device_id": "ar_glasses_123",
    "last_sync": "2026-01-20T12:00:00Z",
    "sync_latency_ms": 45
  }
}
```

### 6. Material Tracking

Spanner tables for circular economy:

```sql
-- Materials table
CREATE TABLE Materials (
  material_id STRING(36) NOT NULL,
  material_type STRING(64) NOT NULL,
  esg_score FLOAT64,
  tensile_strength_mpa FLOAT64,
  dissolve_auth_key STRING(128),
  is_recyclable BOOL DEFAULT (true)
);

-- ComposedOf edge (Asset → Material)
CREATE TABLE ComposedOf (
  asset_id STRING(36) NOT NULL,
  material_id STRING(36) NOT NULL,
  weight_pct FLOAT64
);

-- DerivedFrom edge (Asset → Asset for reprint lineage)
CREATE TABLE DerivedFrom (
  child_asset_id STRING(36) NOT NULL,
  parent_asset_id STRING(36) NOT NULL,
  burn_proof_tx_hash STRING(128)
);
```
