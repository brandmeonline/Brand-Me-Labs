#!/bin/bash
# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Database Initialization Script
# ===============================
#
# Initializes the Brand.Me database with schemas and seed data

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SCHEMAS_DIR="${PROJECT_ROOT}/brandme-data/schemas"
SEEDS_DIR="${PROJECT_ROOT}/brandme-data/seeds"

# Database configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-brandme_dev}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Brand.Me Database Initialization${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Database: ${YELLOW}${DB_NAME}${NC}"
echo -e "Host:     ${YELLOW}${DB_HOST}:${DB_PORT}${NC}"
echo ""

# Function to wait for database
wait_for_db() {
    echo -e "${YELLOW}Waiting for database to be ready...${NC}"

    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "SELECT 1" > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} Database is ready"
            return 0
        fi

        echo -e "${YELLOW}⏳${NC} Waiting for database (attempt $attempt/$max_attempts)..."
        sleep 2
        ((attempt++))
    done

    echo -e "${RED}✗${NC} Database failed to become ready"
    exit 1
}

# Function to create database if it doesn't exist
create_database() {
    echo -e "\n${YELLOW}Creating database if it doesn't exist...${NC}"

    if PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
        echo -e "${YELLOW}⚠${NC}  Database ${DB_NAME} already exists"
    else
        PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE ${DB_NAME};"
        echo -e "${GREEN}✓${NC} Database ${DB_NAME} created"
    fi
}

# Function to install extensions
install_extensions() {
    echo -e "\n${YELLOW}Installing PostgreSQL extensions...${NC}"

    PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<EOF
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create trigger function for updated_at columns
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS \$\$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
\$\$ language 'plpgsql';
EOF

    echo -e "${GREEN}✓${NC} Extensions installed"
}

# Function to apply schemas
apply_schemas() {
    echo -e "\n${YELLOW}Applying database schemas...${NC}"

    if [ ! -d "$SCHEMAS_DIR" ]; then
        echo -e "${RED}✗${NC} Schemas directory not found: $SCHEMAS_DIR"
        exit 1
    fi

    # Apply schemas in order
    for schema_file in "$SCHEMAS_DIR"/*.sql; do
        if [ -f "$schema_file" ]; then
            local filename=$(basename "$schema_file")
            echo -e "  Applying ${YELLOW}${filename}${NC}..."

            PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$schema_file"

            if [ $? -eq 0 ]; then
                echo -e "  ${GREEN}✓${NC} ${filename} applied successfully"
            else
                echo -e "  ${RED}✗${NC} Failed to apply ${filename}"
                exit 1
            fi
        fi
    done

    echo -e "${GREEN}✓${NC} All schemas applied"
}

# Function to load seed data
load_seed_data() {
    echo -e "\n${YELLOW}Loading seed data...${NC}"

    if [ ! -d "$SEEDS_DIR" ]; then
        echo -e "${YELLOW}⚠${NC}  Seeds directory not found, skipping seed data"
        return 0
    fi

    local seed_count=0
    for seed_file in "$SEEDS_DIR"/*.sql; do
        if [ -f "$seed_file" ]; then
            local filename=$(basename "$seed_file")
            echo -e "  Loading ${YELLOW}${filename}${NC}..."

            PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$seed_file"

            if [ $? -eq 0 ]; then
                echo -e "  ${GREEN}✓${NC} ${filename} loaded successfully"
                ((seed_count++))
            else
                echo -e "  ${YELLOW}⚠${NC}  Failed to load ${filename} (continuing...)"
            fi
        fi
    done

    if [ $seed_count -gt 0 ]; then
        echo -e "${GREEN}✓${NC} Loaded $seed_count seed file(s)"
    else
        echo -e "${YELLOW}⚠${NC}  No seed data loaded"
    fi
}

# Function to verify database
verify_database() {
    echo -e "\n${YELLOW}Verifying database...${NC}"

    # Check table count
    local table_count=$(PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")

    echo -e "  Tables created: ${GREEN}${table_count}${NC}"

    # List all tables
    echo -e "\n  ${YELLOW}Tables:${NC}"
    PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "\dt"

    echo -e "\n${GREEN}✓${NC} Database verification complete"
}

# Main execution
main() {
    wait_for_db
    create_database
    install_extensions
    apply_schemas
    load_seed_data
    verify_database

    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}Database Initialization Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "Connection string:"
    echo -e "${YELLOW}postgresql://${DB_USER}:***@${DB_HOST}:${DB_PORT}/${DB_NAME}${NC}"
    echo ""
}

# Run main
main
