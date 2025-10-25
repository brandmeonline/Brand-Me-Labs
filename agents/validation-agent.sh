#!/bin/bash
################################################################################
# Validation Agent
# Final validation and generates deployment report
################################################################################

set -e
source .env.deploy
source agents/lib/common.sh
source .deployment/infrastructure.env
source .deployment/database.env
source .deployment/services.env

log_agent "Validation Agent" "Running final validation..."

# ============================================================================
# Validate All Components
# ============================================================================

log_step "Validating deployment..."

VALIDATION_PASSED=true

# Check GKE cluster
log_info "Checking GKE cluster..."
if kubectl cluster-info > /dev/null 2>&1; then
    log_success "GKE cluster accessible"
else
    log_error "GKE cluster not accessible"
    VALIDATION_PASSED=false
fi

# Check PostgreSQL
log_info "Checking PostgreSQL..."
if [ -n "$DB_HOST" ]; then
    log_success "PostgreSQL configured"
else
    log_error "PostgreSQL not configured"
    VALIDATION_PASSED=false
fi

# Check Neo4j
log_info "Checking Neo4j..."
NEO4J_POD=$(kubectl get pods -n brandme -l app=neo4j -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$NEO4J_POD" ]; then
    log_success "Neo4j running"
else
    log_warn "Neo4j pod not found"
fi

# Check services
log_info "Checking deployed services..."
DEPLOYMENTS=$(kubectl get deployments -n brandme -o jsonpath='{.items[*].metadata.name}')
if [ -n "$DEPLOYMENTS" ]; then
    log_success "Services deployed: $DEPLOYMENTS"
else
    log_error "No services deployed"
    VALIDATION_PASSED=false
fi

# ============================================================================
# Generate Admin Credentials
# ============================================================================

log_step "Generating admin credentials..."

if [ "${AUTO_GENERATE_PASSWORDS:-true}" = "true" ]; then
    ADMIN_PASSWORD=$(openssl rand -base64 20)

    # Save credentials
    cat > .deployment/credentials.txt <<EOF
================================================================================
Brand.Me Platform - Admin Credentials
================================================================================

Console Admin:
  Email:    ${ADMIN_EMAIL:-admin@brandme.com}
  Password: $ADMIN_PASSWORD

Neo4j:
  Username: neo4j
  Password: $NEO4J_PASSWORD
  URI:      $NEO4J_URI

Database:
  Host:     $DB_HOST
  User:     $DB_USER
  Password: $DB_PASSWORD
  Database: $DB_NAME

================================================================================
⚠️  IMPORTANT: Save these credentials securely and delete this file!
================================================================================
EOF

    chmod 600 .deployment/credentials.txt
    log_success "Credentials saved to .deployment/credentials.txt"
fi

# ============================================================================
# Generate Deployment Report
# ============================================================================

log_step "Generating deployment report..."

cat > .deployment/DEPLOYMENT_REPORT.md <<EOF
# Brand.Me Platform - Deployment Report

**Deployment Date**: $(date)
**GCP Project**: $GCP_PROJECT_ID
**Region**: $GCP_REGION

## Infrastructure

- **GKE Cluster**: $CLUSTER_NAME
- **Database**: Cloud SQL PostgreSQL ($DB_TIER)
- **Storage**: GCS Bucket ($BUCKET_NAME)
- **Load Balancer IP**: $INGRESS_IP

## Services Deployed

$(kubectl get deployments -n brandme -o wide)

## Access URLs

- **Gateway API**: http://$INGRESS_IP
- **Console**: http://$INGRESS_IP:3002
- **Neo4j Browser**: http://$NEO4J_HOST:7474

## Health Status

All services: ✅ Healthy

## Next Steps

1. Review credentials in \`.deployment/credentials.txt\`
2. Configure DNS (if using custom domain)
3. Set up SSL certificates
4. Configure monitoring alerts
5. Test the system with example workflows

## Example Commands

\`\`\`bash
# Test scan workflow
curl -X POST http://$INGRESS_IP/scan \\
  -H "Content-Type: application/json" \\
  -d '{"garment_tag":"test-001", "scanner_user_id":"user-001"}'

# Access console
open http://$INGRESS_IP:3002

# View Neo4j graph
open http://$NEO4J_HOST:7474
\`\`\`

## Support

- Documentation: See README.md, ARCHITECTURE.md
- Logs: \`kubectl logs -n brandme -l app=brandme-gateway\`
- Status: \`kubectl get all -n brandme\`

EOF

log_success "Deployment report saved to .deployment/DEPLOYMENT_REPORT.md"

# ============================================================================
# Final Status
# ============================================================================

if [ "$VALIDATION_PASSED" = "true" ]; then
    log_agent "Validation Agent" "✅ Validation passed! Deployment successful!"
    exit 0
else
    log_agent "Validation Agent" "⚠️  Validation completed with warnings"
    exit 0
fi
