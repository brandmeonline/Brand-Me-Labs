# One-Click Production Deployment

**Copyright (c) Brand.Me, Inc. All rights reserved.**

## 🎯 Deploy Brand.Me Platform in 1 Day

Complete production deployment with automated agents handling infrastructure, services, testing, and validation.

---

## 📋 Human Checklist (15 Minutes)

### Step 1: Obtain API Keys (10 mins)

Create accounts and get API keys from these services:

1. **Anthropic API Key**
   - Go to: https://console.anthropic.com/
   - Create account
   - Generate API key
   - Copy: `sk-ant-api03-xxxxx`

2. **OpenAI API Key**
   - Go to: https://platform.openai.com/api-keys
   - Create account
   - Generate API key
   - Copy: `sk-xxxxx`

3. **Blockfrost API Key** (for Cardano)
   - Go to: https://blockfrost.io
   - Create free account
   - Create "Preprod" project
   - Copy project ID: `preprodXXXXXXXXXXXX`

4. **Google Cloud Platform**
   - Go to: https://console.cloud.google.com/
   - Create new project: `brandme-prod`
   - Enable billing
   - Create service account with Owner role
   - Download JSON key file
   - Copy: `brandme-prod-xxxxx.json`

### Step 2: Configure Deployment (5 mins)

Create `.env.deploy` file with your credentials:

```bash
# Copy template
cp .env.deploy.example .env.deploy

# Edit with your keys
nano .env.deploy
```

**Required variables:**
```bash
# AI/LLM
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
OPENAI_API_KEY=sk-xxxxx

# Blockchain
BLOCKFROST_API_KEY=preprodXXXXXXXXXXXX

# GCP
GCP_PROJECT_ID=brandme-prod
GCP_REGION=us-central1
GCP_CREDENTIALS_PATH=/path/to/brandme-prod-xxxxx.json

# Optional: Custom domain
DOMAIN_NAME=brandme.example.com  # Leave blank for IP-based
```

### Step 3: Review Estimated Costs

**GCP Monthly Costs (estimated):**
- GKE Cluster (3 nodes): ~$150/month
- Cloud SQL PostgreSQL: ~$50/month
- Cloud Storage: ~$5/month
- Load Balancer: ~$20/month
- **Total: ~$225/month**

**API Costs (estimated with 10K requests/day):**
- Anthropic Claude: ~$50/month
- OpenAI Embeddings: ~$20/month
- Blockfrost (free tier): $0
- **Total: ~$70/month**

**Grand Total: ~$295/month**

Type 'yes' to approve spending.

### Step 4: Run One-Click Deployment ⚡

```bash
./deploy-brandme.sh
```

That's it! The automated agents will handle everything else.

---

## 🤖 What the Agents Will Do (Automated)

### Infrastructure Agent (20 mins)
- ✅ Validate GCP credentials
- ✅ Create GKE cluster with autoscaling
- ✅ Set up Cloud SQL PostgreSQL
- ✅ Configure VPC networking
- ✅ Set up load balancer
- ✅ Configure DNS (if domain provided)
- ✅ Set up Cloud Storage buckets

### Database Agent (10 mins)
- ✅ Connect to PostgreSQL
- ✅ Run all migrations (7 tables)
- ✅ Deploy Neo4j on GKE
- ✅ Create graph constraints and indexes
- ✅ Deploy NATS JetStream
- ✅ Deploy Redis for Celery

### Service Agent (15 mins)
- ✅ Build Docker images for all 7 services
- ✅ Push to Google Container Registry
- ✅ Deploy via Helm charts
- ✅ Configure secrets and ConfigMaps
- ✅ Set up ingress rules
- ✅ Configure autoscaling

### Integration Agent (10 mins)
- ✅ Wire NATS event streams
- ✅ Connect services to PostgreSQL
- ✅ Link agents to knowledge graph
- ✅ Configure blockchain services
- ✅ Set up authentication flows
- ✅ Test service-to-service communication

### Data Agent (15 mins)
- ✅ Generate realistic test users (100)
- ✅ Create test garments (500)
- ✅ Establish social graph (1000 relationships)
- ✅ Generate scan history (2000 scans)
- ✅ Populate Neo4j knowledge graph
- ✅ Create embeddings for semantic search
- ✅ Import fashion industry data from web

### Testing Agent (20 mins)
- ✅ Health check all services
- ✅ Test API endpoints
- ✅ Run agent workflows
- ✅ Verify blockchain integration
- ✅ Test Graph RAG queries
- ✅ Validate human-in-the-loop
- ✅ Load testing (1000 requests)
- ✅ Security scan

### Validation Agent (5 mins)
- ✅ Generate deployment report
- ✅ Create admin credentials
- ✅ Display service URLs
- ✅ Show example commands
- ✅ Monitor health dashboard

**Total Automated Time: ~95 minutes**

---

## 🎯 After Deployment

You'll receive:

### 1. Service URLs
```
Gateway API:     https://api.brandme.example.com
Console:         https://console.brandme.example.com
Transparency:    https://proof.brandme.example.com
Neo4j Browser:   https://neo4j.brandme.example.com
Grafana:         https://metrics.brandme.example.com
```

### 2. Admin Credentials
```
Console Login:   admin@brandme.com / [auto-generated]
Neo4j Login:     neo4j / [auto-generated]
Grafana Login:   admin / [auto-generated]
```

### 3. Test Data Summary
```
Users:           100 (with social connections)
Garments:        500 (with embeddings)
Creators:        50 (with reputation scores)
Scans:           2000 (with blockchain anchors)
Knowledge Graph: 5000+ nodes, 10000+ relationships
```

### 4. Example Commands
```bash
# Test scan workflow
curl -X POST https://api.brandme.example.com/scan \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"garment_tag": "test-garment-001", "scanner_user_id": "test-user-001"}'

# Query knowledge graph
brandme graph query "Show me provenance for garment test-garment-001"

# View admin dashboard
open https://console.brandme.example.com
```

---

## 🔧 Troubleshooting

### If Deployment Fails

The orchestrator will:
1. Identify the failing component
2. Show detailed error logs
3. Suggest fixes
4. Offer to retry

**Common issues:**
- **GCP quota exceeded**: Request quota increase
- **API rate limits**: Wait 5 mins and retry
- **DNS propagation**: Wait 10-30 mins
- **Database connection**: Check firewall rules

### Manual Intervention

If needed, you can run individual agents:

```bash
# Infrastructure only
./agents/infrastructure-agent.sh

# Database setup only
./agents/database-agent.sh

# Services only
./agents/service-agent.sh

# Testing only
./agents/testing-agent.sh
```

---

## 📊 Monitoring

### Real-time Dashboard

During deployment, watch progress at:
```
http://localhost:8080/deployment-status
```

Shows:
- ✅ Completed tasks
- 🔄 In-progress tasks
- ⏳ Pending tasks
- ❌ Failed tasks
- 📊 Overall progress

### Post-Deployment

Access monitoring at:
- **Grafana**: System metrics, service health
- **Neo4j Browser**: Knowledge graph visualization
- **Logs**: Centralized logging with filtering

---

## 🎓 What You Can Do After Deployment

### 1. Test the System

```bash
# Scan a garment (triggers full agent workflow)
brandme scan --tag test-garment-001 --scanner-id test-user-001

# Query knowledge graph
brandme graph query "Find trust path between test-user-001 and test-user-050"

# View public proof
open https://proof.brandme.example.com/proof/[scan-id]

# Admin approval workflow
open https://console.brandme.example.com/dashboard/escalations
```

### 2. Load Real Data

```bash
# Import from CSV
brandme import users --file users.csv
brandme import garments --file garments.csv

# Sync from existing database
brandme sync --source postgresql://old-db --destination neo4j://new-graph
```

### 3. Customize

```bash
# Update policies
vim brandme-core/policies/region/us-east1.yaml
kubectl apply -f brandme-core/policies/

# Add new agent
# Edit: brandme-agents/agentic/orchestrator/agents.py
# Deploy: kubectl rollout restart deployment brandme-agents

# Adjust autoscaling
kubectl edit hpa brandme-gateway
```

### 4. Scale

```bash
# Scale manually
kubectl scale deployment brandme-gateway --replicas=10

# Configure autoscaling
kubectl autoscale deployment brandme-gateway --min=3 --max=20 --cpu-percent=70

# Add nodes to cluster
gcloud container clusters resize brandme-cluster --num-nodes=5
```

---

## 🚀 Production Readiness Checklist

After deployment, verify:

- [ ] All services healthy (check `/health` endpoints)
- [ ] Database migrations completed
- [ ] Knowledge graph populated
- [ ] NATS streams created
- [ ] Blockchain integration working
- [ ] Agent workflows executing
- [ ] Human-in-the-loop flows working
- [ ] SSL/TLS certificates valid
- [ ] Monitoring and alerts active
- [ ] Backup strategy configured
- [ ] Disaster recovery tested

---

## 📞 Support During Deployment

If you encounter issues:

1. **Check logs**: `./deployment-logs.txt`
2. **View detailed status**: `./check-status.sh`
3. **Retry**: `./deploy-brandme.sh --retry`
4. **Rollback**: `./deploy-brandme.sh --rollback`

---

## ⚡ Quick Start (TL;DR)

```bash
# 1. Get API keys (15 mins)
# - Anthropic, OpenAI, Blockfrost, GCP

# 2. Configure
cp .env.deploy.example .env.deploy
nano .env.deploy  # Add your keys

# 3. Deploy
./deploy-brandme.sh

# 4. Wait ~90 minutes

# 5. Access system
open https://console.brandme.example.com
```

**That's it! You're live in production! 🎉**

---

**Next**: Run `./deploy-brandme.sh` to begin automated deployment.
