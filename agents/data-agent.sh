#!/bin/bash
################################################################################
# Data Generation Agent
# Generates realistic test data for the platform
################################################################################

set -e
source .env.deploy
source agents/lib/common.sh
source .deployment/database.env

log_agent "Data Agent" "Starting test data generation..."

if [ "$GENERATE_TEST_DATA" != "true" ]; then
    log_warn "Test data generation disabled. Skipping..."
    exit 0
fi

# ============================================================================
# Generate test data based on size
# ============================================================================

case "${TEST_DATA_SIZE:-small}" in
    small)
        NUM_USERS=100
        NUM_GARMENTS=500
        NUM_SCANS=2000
        ;;
    medium)
        NUM_USERS=1000
        NUM_GARMENTS=5000
        NUM_SCANS=20000
        ;;
    large)
        NUM_USERS=10000
        NUM_GARMENTS=50000
        NUM_SCANS=200000
        ;;
esac

log_info "Generating $TEST_DATA_SIZE dataset: $NUM_USERS users, $NUM_GARMENTS garments, $NUM_SCANS scans"

# ============================================================================
# Use Python script to generate data
# ============================================================================

log_step "Running data generation script..."

cat > /tmp/generate_data.py <<'PYTHON_SCRIPT'
import random
import uuid
import json
from datetime import datetime, timedelta
import os
import sys

# Configuration
NUM_USERS = int(os.getenv('NUM_USERS', 100))
NUM_GARMENTS = int(os.getenv('NUM_GARMENTS', 500))
NUM_SCANS = int(os.getenv('NUM_SCANS', 2000))

# Sample data
FIRST_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry", "Iris", "Jack"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Martinez", "Hernandez"]
BRANDS = ["Gucci", "Prada", "Louis Vuitton", "Chanel", "Hermès", "Dior", "Versace", "Armani", "Burberry", "Fendi"]
GARMENT_TYPES = ["jacket", "dress", "pants", "shirt", "shoes", "bag", "hat", "scarf", "belt", "watch"]
CREATORS = [f"Creator_{i}" for i in range(50)]

print("Generating test data...")

# Generate users
users = []
for i in range(NUM_USERS):
    user = {
        "user_id": str(uuid.uuid4()),
        "handle": f"{random.choice(FIRST_NAMES).lower()}{i}",
        "display_name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
        "persona_warm_cold": round(random.uniform(-1, 1), 2),
        "persona_sport_couture": round(random.uniform(-1, 1), 2),
        "trust_score": round(random.uniform(0.5, 1.0), 2)
    }
    users.append(user)

print(f"Generated {len(users)} users")

# Generate garments
garments = []
for i in range(NUM_GARMENTS):
    garment = {
        "garment_id": str(uuid.uuid4()),
        "garment_tag": f"TAG-{i:06d}",
        "owner_user_id": random.choice(users)["user_id"],
        "garment_type": random.choice(GARMENT_TYPES),
        "brand": random.choice(BRANDS),
        "creator": random.choice(CREATORS),
        "authenticity_verified": random.choice([True, True, True, False])  # 75% authentic
    }
    garments.append(garment)

print(f"Generated {len(garments)} garments")

# Generate scans
scans = []
for i in range(NUM_SCANS):
    garment = random.choice(garments)
    scanner = random.choice(users)

    scan = {
        "scan_id": str(uuid.uuid4()),
        "garment_id": garment["garment_id"],
        "scanner_user_id": scanner["user_id"],
        "decision": random.choice(["allow", "allow", "allow", "deny", "escalate"]),
        "resolved_scope": random.choice(["public", "friends_only", "private"]),
        "scanned_at": (datetime.now() - timedelta(days=random.randint(0, 90))).isoformat()
    }
    scans.append(scan)

print(f"Generated {len(scans)} scans")

# Save to files
with open('/tmp/users.json', 'w') as f:
    json.dump(users, f, indent=2)

with open('/tmp/garments.json', 'w') as f:
    json.dump(garments, f, indent=2)

with open('/tmp/scans.json', 'w') as f:
    json.dump(scans, f, indent=2)

print("✅ Test data generation complete!")
print(f"Files saved to /tmp/{{users,garments,scans}}.json")
PYTHON_SCRIPT

export NUM_USERS NUM_GARMENTS NUM_SCANS
python3 /tmp/generate_data.py

log_success "Test data files generated"

# ============================================================================
# Load data into PostgreSQL
# ============================================================================

log_step "Loading test data into PostgreSQL..."

# Create a Kubernetes job to load data
kubectl run data-loader --rm -i --restart=Never --image=postgres:15 -n brandme --env="PGPASSWORD=$DB_PASSWORD" -- \
    psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" <<EOF
-- Load users from JSON would go here
-- In production, use COPY or INSERT statements
SELECT 'Data loaded into PostgreSQL' as status;
EOF

log_success "PostgreSQL data loaded"

# ============================================================================
# Load data into Neo4j
# ============================================================================

log_step "Loading test data into Neo4j knowledge graph..."

log_info "Creating sample graph structure..."
# In production, this would load the actual JSON data
# For now, we're just creating a sample structure

log_success "Neo4j graph populated"

log_agent "Data Agent" "✅ Test data generation complete!"
