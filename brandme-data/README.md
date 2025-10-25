# brandme-data

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Authoritative database schema, migrations, and seed data for Brand.Me platform.

## Overview

This repository contains:

- **schemas/**: SQL schema definitions for all tables
- **migrations/**: Database migration scripts (timestamped)
- **seeds/**: Development and test data seeds
- **scripts/**: Database management utilities

## Database: PostgreSQL (Cloud SQL)

### Connection

```bash
# Development
export DATABASE_URL="postgresql://user:password@localhost:5432/brandme_dev"

# Production (via Cloud SQL Proxy)
export DATABASE_URL="postgresql://user:password@/brandme?host=/cloudsql/PROJECT:REGION:INSTANCE"
```

## Tables

### Core Tables

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

- **Alembic**: Migration framework
- **psycopg2**: PostgreSQL adapter
- **pytest**: Testing framework

## Environment Variables

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
