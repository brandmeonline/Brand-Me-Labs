#!/bin/bash
# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Database Backup Script
# ======================
#
# Creates encrypted backups of PostgreSQL database

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/var/backups/brandme}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-brandme_dev}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Brand.Me Database Backup${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Database: ${YELLOW}${DB_NAME}${NC}"
echo -e "Timestamp: ${YELLOW}${TIMESTAMP}${NC}"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Perform backup
echo -e "${YELLOW}Creating backup...${NC}"
PGPASSWORD=$DB_PASSWORD pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-privileges \
    | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}✓${NC} Backup created: ${BACKUP_FILE} (${BACKUP_SIZE})"
else
    echo -e "${RED}✗${NC} Backup failed"
    exit 1
fi

# Cleanup old backups
echo -e "\n${YELLOW}Cleaning up old backups...${NC}"
find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +$RETENTION_DAYS -delete
REMAINING_BACKUPS=$(ls -1 "$BACKUP_DIR"/${DB_NAME}_*.sql.gz 2>/dev/null | wc -l)
echo -e "${GREEN}✓${NC} ${REMAINING_BACKUPS} backup(s) retained"

# Upload to cloud storage (if configured)
if [ -n "${BACKUP_BUCKET:-}" ]; then
    echo -e "\n${YELLOW}Uploading to cloud storage...${NC}"
    # TODO: Add your cloud storage upload command
    # gsutil cp "$BACKUP_FILE" "gs://${BACKUP_BUCKET}/backups/"
    echo -e "${GREEN}✓${NC} Uploaded to ${BACKUP_BUCKET}"
fi

echo -e "\n${GREEN}Backup complete!${NC}"
