# brandme-data

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Authoritative database schema and seed data for Brand.Me platform.

## Overview

This repository contains:

- **spanner/**: Google Cloud Spanner DDL schema (v8 primary database)
- **schemas/**: Legacy PostgreSQL schema definitions (deprecated, kept for reference)
- **seeds/**: Development and test data seeds

## v8 Database Architecture

**Version 8** uses a dual-database stack:

- **Google Cloud Spanner**: Source of truth for users, assets, consent graph, provenance
- **Firestore**: Real-time wardrobe state, edge caching, agentic state

### Spanner Connection

```bash
# Development (with emulator)
export SPANNER_EMULATOR_HOST=localhost:9010
export SPANNER_PROJECT_ID=brandme-project
export SPANNER_INSTANCE_ID=brandme-instance
export SPANNER_DATABASE_ID=brandme-db

# Production
export SPANNER_PROJECT_ID=brandme-production
export SPANNER_INSTANCE_ID=brandme-global
export SPANNER_DATABASE_ID=brandme-db
```

### Firestore Connection

```bash
# Development (with emulator)
export FIRESTORE_EMULATOR_HOST=localhost:8080
export FIRESTORE_PROJECT_ID=brandme-dev

# Production
export FIRESTORE_PROJECT_ID=brandme-production
```

## v8 Spanner Tables

### Node Tables (Graph)

1. **Users** - User accounts with trust scores
2. **Assets** - Asset records (cubes, garments)

### Edge Tables (Graph Relationships)

3. **Owns** - Ownership relationships (Owner → Asset)
4. **Created** - Creator attribution (Creator → Asset)
5. **FriendsWith** - Social graph (User ↔ User)

### Supporting Tables

6. **ConsentPolicies** - Privacy and visibility rules
7. **ProvenanceChain** - Interleaved provenance with sequence numbers
8. **CubeFaces** - Product Cube face data
9. **AuditLog** - Hash-chained audit trail
10. **ChainAnchor** - Blockchain transaction references
11. **MutationLog** - Idempotent write deduplication

### Graph Definition

See `spanner/schema.sql` for the full Spanner Graph DDL.

## Schema Initialization

### Local Development with Emulator

The Spanner schema is automatically initialized when running:

```bash
docker-compose up -d
```

The `spanner-init` service applies `spanner/schema.sql` to the emulator.

### Production Deployment

```bash
# Create Spanner database with schema
gcloud spanner databases create brandme-db \
  --instance=brandme-instance \
  --ddl-file=brandme-data/spanner/schema.sql
```

## Seeding Data

Seed files in `seeds/` can be loaded via the spanner-init service or manually:

```bash
# Load seed data (development only)
docker-compose exec spanner-init python load_seeds.py
```

## Schema Management

### Constraints

- All primary keys are UUIDs stored as STRING(36)
- Foreign keys enforced via graph edge constraints
- All timestamps use `TIMESTAMP` with commit timestamp support
- Indexes on frequently queried columns

### Security

- No PII in plain text logs
- Wallet keys NEVER stored in database
- Midnight references stored encrypted at rest
- Audit logs are hash-chained and tamper-evident
- Driver-level PII redaction in brandme_core.spanner.pii_redactor

## Testing

```bash
# Run database tests against emulator
pytest tests/ -v
```

## Environment Variables

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

## Compliance

- GDPR: User data can be fully purged via cascade delete
- Audit Trail: All mutations logged with hash-chain
- Right to Access: User data export via service endpoints
