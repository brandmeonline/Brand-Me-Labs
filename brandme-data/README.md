# brandme-data

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Authoritative database schema, migrations, and seed data for Brand.Me platform.

## Overview

This repository contains:

- **spanner/**: Google Cloud Spanner DDL schema (v8 primary)
- **schemas/**: Legacy PostgreSQL schema definitions (deprecated)
- **migrations/**: Database migration scripts (timestamped)
- **seeds/**: Development and test data seeds
- **scripts/**: Database management utilities

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

## Legacy Database: PostgreSQL (DEPRECATED)

> **Note**: PostgreSQL is deprecated in v8. Use Spanner for new development.

### Connection (Legacy)

```bash
# Development
export DATABASE_URL="postgresql://user:password@localhost:5432/brandme_dev"

# Production (via Cloud SQL Proxy)
export DATABASE_URL="postgresql://user:password@/brandme?host=/cloudsql/PROJECT:REGION:INSTANCE"
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

## Legacy PostgreSQL Tables (DEPRECATED)

1. **users** - User accounts and personas
2. **garments** - Garment registry
3. **garment_passport_facets** - Garment metadata and provenance
4. **consent_policies** - Privacy and visibility rules
5. **scan_event** - Scan history and outcomes
6. **chain_anchor** - Blockchain transaction references
7. **audit_log** - Hash-chained audit trail

## Migrations

### Running Migrations

```bash
# Apply all pending migrations
python manage.py migrate

# Create new migration
python manage.py create-migration "add_user_preferences"

# Rollback last migration
python manage.py rollback
```

### Migration Naming Convention

```
YYYYMMDDHHMMSS_description.sql

Example:
20251025120000_create_users_table.sql
20251025120100_create_garments_table.sql
```

## Seeding Data

```bash
# Seed development data
python manage.py seed

# Seed specific fixture
python manage.py seed --fixture=users

# Clear and reseed
python manage.py seed --clear
```

## Schema Management

### Constraints

- All primary keys are UUID
- Foreign keys use ON DELETE CASCADE or RESTRICT based on data criticality
- All timestamps use `TIMESTAMPTZ` for timezone awareness
- Indexes on frequently queried columns

### Security

- No PII in plain text logs
- Wallet keys NEVER stored in database
- Midnight references stored encrypted at rest
- Audit logs are hash-chained and tamper-evident

## Testing

```bash
# Run database tests
pytest tests/

# Check migrations
python manage.py check-migrations
```

## Tools

### v8 (Spanner + Firestore)

- **google-cloud-spanner**: Spanner client with PingingPool
- **google-cloud-firestore**: Firestore async client
- **pytest**: Testing framework with emulator fixtures

### Legacy (PostgreSQL - DEPRECATED)

- **Alembic**: Migration framework
- **psycopg2/asyncpg**: PostgreSQL adapter

## Environment Variables

### v8 (Recommended)

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

### Legacy (PostgreSQL - DEPRECATED)

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/brandme_dev
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

## Backup & Recovery

```bash
# Backup production database
./scripts/backup.sh production

# Restore from backup
./scripts/restore.sh backup_20251025.sql
```

## Compliance

- GDPR: User data can be fully purged via `DELETE CASCADE`
- Audit Trail: All mutations logged with hash-chain
- Right to Access: User data export via `scripts/export_user_data.py`
