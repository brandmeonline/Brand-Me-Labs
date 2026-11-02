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

## 2030 Agentic & Circular Economy

Version 9 is the production-ready architecture for planetary-scale fashion identity, provenance, and circular economy operations.

**Core Technologies:**
- **Google Cloud Spanner**: Native Property Graph (GQL), O(1) consent lookups, Material tracking
- **Firestore**: Real-time wardrobe sync, Biometric sync for AR glasses (<100ms)
- **Model Context Protocol (MCP)**: External agent access to Style Vault
- **Cardano**: Public provenance, ESG oracle verification
- **Midnight**: Private ownership, ZK burn proofs for circular economy

---

## Table of Contents

1. [Mission & Compliance](#mission--compliance)
2. [System Architecture](#system-architecture)
3. [Data Model](#data-model)
4. [Product Cube](#product-cube)
5. [MCP Integration](#mcp-integration)
6. [DPP Lifecycle](#dpp-lifecycle)
7. [ZK Proof System](#zk-proof-system)
8. [Runtime Flows](#runtime-flows)
9. [Security & Privacy](#security--privacy)
10. [Infrastructure](#infrastructure)

---

## Mission & Compliance

### North Star

**Verifiable identity, provenance, and cultural expression through fashion.**

### Integrity Definition

1. **Immutable provenance** for assets and creators
2. **Consent-driven visibility** for owners
3. **Auditability** for regulators
4. **No silent exposure** of private data

### Privacy Layers

| Layer | Blockchain | Purpose | Data Types |
|-------|-----------|---------|------------|
| **Public** | Cardano | Provenance, ESG | Creator attribution, authenticity hash, ESG score |
| **Private** | Midnight | Ownership, Pricing | Ownership lineage, price history, consent snapshots |
| **Cross-Chain** | Both | Verification | Cryptographic link via root hash |

**Rule**: Public provenance and ESG anchors go to Cardano. Ownership lineage, pricing history, and consent snapshots go to Midnight.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                                │
│         (Mobile App, Web, AR Glasses via Biometric Sync)             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTPS / MCP
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      brandme-gateway                                 │
│     OAuth Authentication, Rate Limiting, MCP Server, NATS Pub       │
└────────────────────────┬───────────────────┬────────────────────────┘
                         │                   │
         ┌───────────────┴───────────────────┴───────────────────┐
         │                   NATS JetStream                       │
         └───────────┬───────────────┬───────────────┬───────────┘
                     ▼               ▼               ▼
┌─────────────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│     brandme-core        │ │ brandme-agents  │ │   brandme-chain     │
│                         │ │                 │ │                     │
│ • Brain (8000)          │ │ • Identity      │ │ • TX Builder        │
│ • Policy (8001)         │ │   (8005)        │ │   Cardano+Midnight  │
│ • Orchestrator (8002)   │ │ • Knowledge     │ │ • Cross-Chain       │
│ • Cube (8007)           │ │   (8003)        │ │   Verifier          │
│                         │ │ • Compliance    │ │                     │
│                         │ │   (8004)        │ │                     │
│                         │ │ • Agentic       │ │                     │
│                         │ │   Orchestrator  │ │                     │
└───────────┬─────────────┘ └────────┬────────┘ └──────────┬──────────┘
            │                        │                      │
            └────────────────────────┼──────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          DATA LAYER                                  │
│  ┌──────────────────────────┐  ┌──────────────────────────┐        │
│  │    Google Cloud Spanner  │  │       Firestore          │        │
│  │                          │  │                          │        │
│  │  • Users (node)          │  │  • /wardrobes/{user_id}  │        │
│  │  • Assets (node)         │  │    └─ /cubes/{cube_id}   │        │
│  │  • Materials (node)      │  │       └─ faces, state    │        │
│  │  • Owns (edge)           │  │                          │        │
│  │  • ComposedOf (edge)     │  │  • /biometric_sync/      │        │
│  │  • DerivedFrom (edge)    │  │    └─ AR glasses <100ms  │        │
│  │  • ConsentPolicies       │  │                          │        │
│  │  • ProvenanceChain       │  │  • /agent_sessions/      │        │
│  │  • AgentTransaction      │  │    └─ MCP state tracking │        │
│  │  • ZKProofCache          │  │                          │        │
│  │  • MaterialESGCache      │  │                          │        │
│  │  • BurnProofCache        │  │                          │        │
│  │                          │  │                          │        │
│  │  O(1) consent lookups    │  │  Real-time listeners     │        │
│  │  Native Property Graph   │  │  Agentic state sync      │        │
│  └──────────────────────────┘  └──────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       BLOCKCHAIN LAYER                               │
│  ┌──────────────────────┐  ┌──────────────────────┐                │
│  │      Cardano         │  │      Midnight        │                │
│  │   (Public Chain)     │  │   (Private Chain)    │                │
│  │                      │  │                      │                │
│  │  • Provenance        │  │  • Ownership         │                │
│  │  • ESG oracle        │  │  • Pricing history   │                │
│  │  • Creator credits   │  │  • Consent proofs    │                │
│  │                      │  │  • Burn proofs (ZK)  │                │
│  └──────────────────────┘  └──────────────────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

### Service Ports

| Service | Port | Description | Database |
|---------|------|-------------|----------|
| **brain** | 8000 | Intent resolver, scan entrypoint | Spanner |
| **policy** | 8001 | Consent graph & policy decisions | Spanner |
| **orchestrator** | 8002 | Scan processing & blockchain anchoring | Spanner |
| **knowledge** | 8003 | Safe facet retrieval | Spanner |
| **compliance** | 8004 | Hash-chained audit logging, ESG verification | Spanner |
| **identity** | 8005 | User profiles, ZK proofs, consent | Spanner |
| **governance** | 8006 | Human review UI, escalations | Spanner |
| **cube** | 8007 | Product Cube with real-time state | Spanner + Firestore |

---

## Data Model

### Google Cloud Spanner (Source of Truth)

Full schema: `brandme-data/spanner/schema.sql`

#### Node Tables


### Google Cloud Spanner (Source of Truth)

Full schema: `brandme-data/spanner/schema.sql`

#### Node Tables

**Users**
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
) PRIMARY KEY (user_id);
```

**Assets**
```sql
CREATE TABLE Assets (
  asset_id STRING(36) NOT NULL,
  asset_type STRING(32) NOT NULL,  -- 'cube', 'garment'
  display_name STRING(256) NOT NULL,
  creator_user_id STRING(36) NOT NULL,
  current_owner_id STRING(36) NOT NULL,
  physical_tag_id STRING(128),     -- NFC/RFID tag
  authenticity_hash STRING(128),
  dpp_state STRING(32) DEFAULT 'PRODUCED',  -- PRODUCED, ACTIVE, REPAIR, DISSOLVE, REPRINT
  is_active BOOL NOT NULL DEFAULT (true),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (asset_id);
```

**Materials**
```sql
CREATE TABLE Materials (
  material_id STRING(36) NOT NULL,
  material_type STRING(64) NOT NULL,
  esg_score FLOAT64,
  tensile_strength_mpa FLOAT64,
  dissolve_auth_key STRING(128),
  is_recyclable BOOL DEFAULT (true),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (material_id);
```

#### Edge Tables (Graph Relationships)

**Owns** (User → Asset)
```sql
CREATE TABLE Owns (
  owner_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  device_session_id STRING(128),
  acquired_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  transfer_method STRING(32),  -- 'mint', 'purchase', 'gift', 'rental', 'reprint'
  is_current BOOL NOT NULL DEFAULT (true),
) PRIMARY KEY (owner_id, asset_id);
```

**ComposedOf** (Asset → Material)
```sql
CREATE TABLE ComposedOf (
  asset_id STRING(36) NOT NULL,
  material_id STRING(36) NOT NULL,
  weight_pct FLOAT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (asset_id, material_id);
```

**DerivedFrom** (Asset → Asset for reprint lineage)
```sql
CREATE TABLE DerivedFrom (
  child_asset_id STRING(36) NOT NULL,
  parent_asset_id STRING(36) NOT NULL,
  burn_proof_tx_hash STRING(128) NOT NULL,
  material_recovery_pct FLOAT64,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (child_asset_id, parent_asset_id);
```

#### Graph Definition

```sql
CREATE OR REPLACE PROPERTY GRAPH IntegritySpineGraph
  NODE TABLES (
    Users,
    Assets,
    Materials
  )
  EDGE TABLES (
    Owns
      SOURCE KEY (owner_id) REFERENCES Users(user_id)
      DESTINATION KEY (asset_id) REFERENCES Assets(asset_id)
      LABEL OWNS,
    FriendsWith
      SOURCE KEY (user_id_1) REFERENCES Users(user_id)
      DESTINATION KEY (user_id_2) REFERENCES Users(user_id)
      LABEL FRIENDS_WITH,
    ComposedOf
      SOURCE KEY (asset_id) REFERENCES Assets(asset_id)
      DESTINATION KEY (material_id) REFERENCES Materials(material_id)
      LABEL COMPOSED_OF,
    DerivedFrom
      SOURCE KEY (child_asset_id) REFERENCES Assets(asset_id)
      DESTINATION KEY (parent_asset_id) REFERENCES Assets(asset_id)
      LABEL DERIVED_FROM
  );
```

#### O(1) Consent Query

```sql
GRAPH IntegritySpineGraph
MATCH (viewer:Users)-[:FRIENDS_WITH*0..1]-(owner:Users)-[:OWNS]->(asset:Assets)
WHERE asset.asset_id = @asset_id
  AND NOT EXISTS {
    MATCH (owner)-[:HAS_CONSENT]->(consent:ConsentPolicies)
    WHERE consent.is_revoked = true
  }
RETURN owner.user_id, viewer.user_id;
```

### Firestore (Real-Time State)

#### Collections

- `/wardrobes/{user_id}` - Wardrobe metadata
  - `/cubes/{cube_id}` - Cube state, faces, visibility
- `/biometric_sync/{user_id}` - AR glasses sync (<100ms)
- `/agent_sessions/{session_id}` - MCP agent tracking

#### Biometric Sync Document

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
    "device_session_id": "ar_glasses_123",
    "last_sync": "2026-01-20T12:00:00Z",
    "sync_latency_ms": 45
  }
}
```

---

## Product Cube

The Product Cube is a 7-face digital passport for physical assets.

### Faces

| Face | Purpose | Visibility | Blockchain |
|------|---------|------------|------------|
| product_details | Immutable product info | Public | Cardano |
| provenance | Append-only ownership journey | Public | Cardano |
| ownership | Current owner reference | Private | Midnight |
| social_layer | Ratings, reviews, stories | Friends/Public | - |
| esg_impact | ESG scores from Cardano oracle | Public | Cardano |
| lifecycle | DPP state, repair history | Public | Cardano |
| molecular_data | Material composition, dissolve auth | Private | Midnight |

### Cube Document (Firestore)

```json
{
  "cube_id": "uuid",
  "owner_id": "uuid",
  "agentic_state": "idle|processing|modified|syncing|error",
  "dpp_state": "PRODUCED|ACTIVE|REPAIR|DISSOLVE|REPRINT",
  "faces": {
    "product_details": {
      "data": {...},
      "visibility": "public",
      "pending_sync": false
    },
    "molecular_data": {
      "data": {...},
      "visibility": "private",
      "pending_sync": false
    }
  },
  "spanner_synced_at": "timestamp"
}
```

---

## MCP Integration

Model Context Protocol enables external AI agents to access the Style Vault.

### MCP Tools

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

### Transaction Requirements

All transaction tools require:
1. **User consent** stored in `ConsentedByAgent` table
2. **ESG verification** from Cardano oracle (via `ESGVerifier`)
3. **Optional human approval** for high-value transactions
4. **AgentTransaction** record in Spanner for audit trail

### Agent Transaction Table

```sql
CREATE TABLE AgentTransaction (
  transaction_id STRING(36) NOT NULL,
  agent_id STRING(64) NOT NULL,
  user_id STRING(36) NOT NULL,
  asset_id STRING(36),
  action_type STRING(32) NOT NULL,
  esg_verified BOOL DEFAULT (false),
  esg_score FLOAT64,
  human_approved BOOL,
  status STRING(32) DEFAULT 'pending',
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (transaction_id);
```

---

## DPP Lifecycle

Digital Product Passport state machine for circular economy.

### State Machine

```
PRODUCED → ACTIVE → REPAIR → ACTIVE
                  ↘ DISSOLVE → REPRINT → PRODUCED
```

### Valid Transitions

| From | To | Trigger | Blockchain |
|------|----|---------|------------|
| PRODUCED | ACTIVE | Item enters circulation | Cardano anchor |
| ACTIVE | REPAIR | Repair requested | Cardano anchor |
| ACTIVE | DISSOLVE | Owner authorizes dissolution | Midnight burn proof |
| REPAIR | ACTIVE | Repair complete | Cardano anchor |
| REPAIR | DISSOLVE | Beyond repair | Midnight burn proof |
| DISSOLVE | REPRINT | Materials used in new product | Midnight ZK proof |
| REPRINT | PRODUCED | New product enters circulation | Cardano anchor + lineage |

### Burn Proof Verification

For DISSOLVE→REPRINT transitions:

```python
verifier = BurnProofVerifier(
    midnight_api_url="http://midnight-devnet:9000",
    spanner_pool=pool,
    require_midnight=True,  # Production mode
    allow_stub_fallback=False
)

result = await verifier.verify_detailed(
    burn_proof_hash="sha256_proof_hash",
    parent_asset_id="dissolved_asset_id"
)

if result.is_valid and result.midnight_confirmed:
    # Proceed with reprint
    pass
```

### ESG Verification

For rental, resale, and dissolve transactions:

```python
verifier = ESGVerifier(
    cardano_node_url="http://cardano-node:3001",
    spanner_pool=pool,
    require_cardano=True,  # Production mode
    allow_stub_fallback=False
)

result = await verifier.verify_transaction(
    asset_id="asset_123",
    material_id="material_456",
    transaction_type="rental",  # threshold: 0.5
    agent_id="agent_789"
)

if result.is_approved:
    # Proceed with transaction
    pass
```

---

## ZK Proof System

Zero-knowledge proofs enable AR glasses to verify ownership without exposing private keys.

### Proof Flow

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

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /identity/{user_id}/zk/generate` | Generate ownership proof |
| `POST /identity/{user_id}/zk/verify` | Verify proof |
| `GET /identity/{user_id}/zk/proofs` | List active proofs |
| `DELETE /identity/{user_id}/zk/proofs` | Invalidate after transfer |

### ZK Proof Cache (Spanner)

```sql
CREATE TABLE ZKProofCache (
  proof_id STRING(36) NOT NULL,
  user_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  proof_type STRING(32) NOT NULL,
  proof_hash STRING(128) NOT NULL,
  proof_data BYTES(MAX),
  public_signals JSON,
  device_session_id STRING(128),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  expires_at TIMESTAMP NOT NULL,
) PRIMARY KEY (proof_id);
```

---

## Runtime Flows

### Asset Scan Flow

```
┌─────────┐
│ Client  │
└────┬────┘
     │ POST /scan {physical_tag_id}
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
│ Brain (8000)         │
│  - Resolve asset_id  │
│    via physical_tag  │
└────┬─────────────────┘
     │
     ▼
┌──────────────────────┐
│ Policy (8001)        │
│  - O(1) consent check│
│  - Resolve scope     │
└────┬─────────────────┘
     │ decision: allow
     ▼
┌──────────────────────┐
│ Orchestrator (8002)  │
│  - Idempotent write  │
│  - Fetch facets      │
│  - Build TX          │
└────┬─────────────────┘
     │
     ├─────────────────────┐
     ▼                     ▼
┌─────────────────┐  ┌────────────────┐
│ brandme-chain   │  │ Compliance     │
│  - Cardano TX   │  │ (8004)         │
│  - Midnight TX  │  │  - Hash-chain  │
│  - Root hash    │  │    audit_log   │
└─────────────────┘  └────────────────┘
```

### MCP Agent Transaction Flow

```
┌─────────────────┐
│ External Agent  │
│ (via MCP)       │
└────┬────────────┘
     │ search_wardrobe / initiate_rental
     ▼
┌─────────────────────────────────────────┐
│ MCP Server (Gateway)                    │
│  - Verify agent consent                 │
│  - Check user consent for agent access  │
└────┬────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│ Agentic Orchestrator                    │
│  - ScanAgent: resolve asset             │
│  - IdentityAgent: verify relationships  │
│  - PolicyAgent: check consent + region  │
│  - ComplianceAgent: ESG verification    │
└────┬────────────────────────────────────┘
     │
     ├── If requires_human_approval ──────►┌──────────────┐
     │                                      │ Governance   │
     │                                      │ Console      │
     │◄── approval_granted ────────────────┘              │
     │
     ▼
┌─────────────────────────────────────────┐
│ Transaction Execution                    │
│  - Record AgentTransaction              │
│  - Update DPP state if applicable       │
│  - Anchor to blockchain                 │
└─────────────────────────────────────────┘
```

---

## Security & Privacy

### Hard Guarantees

1. **Policy check before any data reveal** - No data shown without consent verification
2. **TX Builder is the only blockchain write path** - Centralized wallet management
3. **Hash-chained audit logs** - Tamper-evident compliance trail
4. **Dual approval for Midnight reveals** - Human + Compliance agent
5. **No private data in public endpoints** - Transparency Portal shows only Cardano data
6. **ESG verification for all agent transactions** - Ethical oversight enforced

### Data Classification

| Data Type | Storage | Visibility | Blockchain |
|-----------|---------|------------|------------|
| Creator Attribution | Spanner | Public | Cardano |
| Authenticity Hash | Spanner | Public | Cardano |
| ESG Score | Spanner + Cache | Public | Cardano |
| Ownership Lineage | Spanner | Private | Midnight |
| Pricing History | Spanner | Private | Midnight |
| Consent Policies | Spanner | Private | Midnight |
| Material Composition | Spanner | Private | Midnight |
| Burn Proofs | Spanner + Cache | Private | Midnight |

### Secrets Management

- **Wallet Keys**: Kubernetes secrets only
- **No plaintext secrets in repo**: Use `.env.example` templates
- **No PII in logs**: Use `redact_user_id()` and `truncate_id()`

---

## Infrastructure

### Google Cloud Platform

| Service | Purpose |
|---------|---------|
| **GKE** | Container orchestration |
| **Spanner** | Global consistency database |
| **Firestore** | Real-time state, AR glasses sync |
| **GCS** | Passport blob storage |
| **VPC** | Network isolation |
| **Workload Identity** | Service account management |

### Database Libraries

- **Spanner**: `google-cloud-spanner` with PingingPool
- **Firestore**: `google-cloud-firestore` with async client

### Observability

- **OpenTelemetry**: Distributed tracing
- **Prometheus**: Metrics collection
- **Grafana**: Visualization
- **Loki**: Log aggregation

### Local Development

```bash
# Start emulators
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
SPANNER_POOL_SIZE=10

# Firestore
FIRESTORE_EMULATOR_HOST=localhost:8080
FIRESTORE_PROJECT_ID=brandme-dev

# Blockchain (Production)
CARDANO_NODE_URL=http://cardano-node:3001
MIDNIGHT_API_URL=http://midnight-devnet:9000
```

---

## Repository Structure

```
Brand-Me-Labs/
├── brandme-gateway/          # Edge gateway, MCP server
├── brandme-core/             # Core services
│   ├── brain/                # Intent resolver (8000)
│   ├── policy/               # Consent graph (8001)
│   └── orchestrator/         # Scan processing (8002)
├── brandme-agents/           # Agent services
│   ├── identity/             # User profiles, ZK proofs (8005)
│   ├── knowledge/            # Safe facet retrieval (8003)
│   ├── compliance/           # Audit, ESG, burn proofs (8004)
│   └── agentic/              # Multi-agent orchestrator
├── brandme-governance/       # Human review console (8006)
├── brandme-cube/             # Product Cube service (8007)
├── brandme_core/             # Shared utilities
│   ├── spanner/              # Spanner client, consent graph
│   ├── firestore/            # Firestore client, realtime
│   ├── mcp/                  # MCP tools and handlers
│   └── zk/                   # ZK proof generation/verification
├── brandme-data/             # Database schemas
│   └── spanner/              # Spanner DDL
├── brandme-chain/            # Blockchain integration
├── brandme-console/          # Web interfaces
└── brandme-infra/            # Infrastructure as Code
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
