#!/bin/bash
################################################################################
# Infrastructure Deployment Agent
# Provisions GCP infrastructure using Terraform
################################################################################

set -e
source .env.deploy
source agents/lib/common.sh

log_agent "Infrastructure Agent" "Starting infrastructure provisioning..."

# Authenticate with GCP
log_step "Authenticating with GCP..."
gcloud auth activate-service-account --key-file="$GCP_CREDENTIALS_PATH"
gcloud config set project "$GCP_PROJECT_ID"

# Enable required APIs
log_step "Enabling GCP APIs..."
gcloud services enable container.googleapis.com --quiet
gcloud services enable sql-component.googleapis.com --quiet
gcloud services enable compute.googleapis.com --quiet
gcloud services enable storage-api.googleapis.com --quiet
gcloud services enable servicenetworking.googleapis.com --quiet

# Initialize Terraform
log_step "Initializing Terraform..."
cd brandme-infra/terraform

# Create terraform.tfvars
cat > terraform.tfvars <<EOF
project_id = "$GCP_PROJECT_ID"
region = "$GCP_REGION"
cluster_name = "brandme-cluster"
node_count = 3
machine_type = "n1-standard-2"
db_tier = "${DB_TIER:-db-g1-small}"
enable_autoscaling = ${ENABLE_AUTOSCALING:-true}
EOF

terraform init
terraform validate

# Plan
log_step "Planning infrastructure..."
terraform plan -out=tfplan

# Apply
log_step "Deploying infrastructure (this may take 15-20 mins)..."
terraform apply tfplan

# Get outputs
CLUSTER_NAME=$(terraform output -raw cluster_name)
DB_IP=$(terraform output -raw db_private_ip)
BUCKET_NAME=$(terraform output -raw bucket_name)

# Configure kubectl
log_step "Configuring kubectl..."
gcloud container clusters get-credentials "$CLUSTER_NAME" \
    --region="$GCP_REGION" \
    --project="$GCP_PROJECT_ID"

# Verify cluster
kubectl cluster-info
kubectl get nodes

# Save outputs
mkdir -p ../../.deployment
cat > ../../.deployment/infrastructure.env <<EOF
CLUSTER_NAME=$CLUSTER_NAME
DB_IP=$DB_IP
BUCKET_NAME=$BUCKET_NAME
EOF

log_agent "Infrastructure Agent" "✅ Infrastructure provisioning complete!"
cd ../..
