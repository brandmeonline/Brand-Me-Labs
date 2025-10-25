# Brand.Me - Quick Start Guide

**Deploy Complete AI-Native Platform in 1 Day**

---

## 🎯 What You're Deploying

A production-ready, AI-native garment provenance platform with:

✅ **7 Microservices** (Gateway, Chain, Core, Agents, Console)
✅ **Knowledge Graph** (Neo4j with Graph RAG)
✅ **AI Agents** (LangGraph multi-agent orchestration)
✅ **Dual Blockchain** (Cardano public + Midnight private)
✅ **Human-in-the-Loop** (Governance approval workflows)
✅ **Auto-Scaling Infrastructure** (GKE on Google Cloud)

**Total Implementation**: 8 commits, 10,000+ lines of code, production-ready

---

## ⚡ One-Click Deployment (Your Part: 15 Minutes)

### Step 1: Get API Keys (10 minutes)

Visit these sites and get your API keys:

1. **Anthropic Claude** → https://console.anthropic.com/
   - Create account
   - Get API key: `sk-ant-api03-xxxxx`

2. **OpenAI** → https://platform.openai.com/api-keys
   - Create account
   - Get API key: `sk-xxxxx`

3. **Blockfrost (Cardano)** → https://blockfrost.io
   - Create free account
   - Create "Preprod" project
   - Copy project ID: `preprodXXXXXXXXXXXX`

4. **Google Cloud Platform** → https://console.cloud.google.com/
   - Create project: `brandme-prod`
   - Enable billing
   - Create service account (Owner role)
   - Download JSON key: `brandme-prod-xxxxx.json`

### Step 2: Configure Deployment (5 minutes)

```bash
# Navigate to project
cd Brand-Me-Labs

# Copy configuration template
cp .env.deploy.example .env.deploy

# Edit with your API keys
nano .env.deploy

# Required variables:
# - ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
# - OPENAI_API_KEY=sk-xxxxx
# - BLOCKFROST_API_KEY=preprodXXXXXXXXXXXX
# - GCP_PROJECT_ID=brandme-prod
# - GCP_REGION=us-central1
# - GCP_CREDENTIALS_PATH=/path/to/brandme-prod-xxxxx.json
```

### Step 3: Deploy! 🚀

```bash
./deploy-brandme.sh
```

**That's it!** The automated agents will handle everything else.

---

## 🤖 What Happens Automatically (90 Minutes)

While you wait, the system will:

### Infrastructure Agent (20 mins)
- ✅ Create GKE cluster (3 nodes)
- ✅ Deploy Cloud SQL PostgreSQL
- ✅ Set up networking and load balancer
- ✅ Configure storage buckets

### Database Agent (10 mins)
- ✅ Run PostgreSQL migrations
- ✅ Deploy Neo4j knowledge graph
- ✅ Set up NATS event streaming
- ✅ Deploy Redis for task queues

### Service Agent (15 mins)
- ✅ Build Docker images for all 7 services
- ✅ Push to Google Container Registry
- ✅ Deploy via Helm charts
- ✅ Configure autoscaling

### Integration Agent (10 mins)
- ✅ Wire up event-driven communication
- ✅ Test service connectivity
- ✅ Validate database connections

### Data Agent (15 mins)
- ✅ Generate 100 test users
- ✅ Create 500 garments with brands
- ✅ Build social graph (1000 relationships)
- ✅ Populate knowledge graph
- ✅ Generate 2000 scan events

### Testing Agent (20 mins)
- ✅ Health check all services
- ✅ Test API endpoints
- ✅ Run agent workflows
- ✅ Validate blockchain integration
- ✅ Load testing

### Validation Agent (5 mins)
- ✅ Generate admin credentials
- ✅ Create deployment report
- ✅ Show access information

**Progress displayed in real-time!**

---

## 🎉 After Deployment

You'll see:

```
╔══════════════════════════════════════════════════════════════╗
║              ✅ DEPLOYMENT SUCCESSFUL! ✅                    ║
╚══════════════════════════════════════════════════════════════╝

📍 Service URLs:
   Gateway API:      http://[YOUR-IP]
   Console:          http://[YOUR-IP]:3002
   Neo4j Browser:    http://[YOUR-IP]:7474

🔑 Credentials saved to: .deployment/credentials.txt

🧪 Test the system:
   curl -X POST http://[YOUR-IP]/scan \
     -d '{"garment_tag":"test-001","scanner_user_id":"user-001"}'
```

---

## 🧪 Test It Out

### 1. Access the Console

```bash
# Open in browser
open http://[YOUR-IP]:3002

# Login with credentials from .deployment/credentials.txt
```

### 2. Run Your First Scan

```bash
# Using curl
curl -X POST http://[YOUR-IP]/scan \
  -H "Content-Type: application/json" \
  -d '{"garment_tag":"TAG-000001","scanner_user_id":"[user-id]"}'

# Using CLI
brandme scan --tag TAG-000001 --scanner-id [user-id]
```

### 3. Query the Knowledge Graph

```bash
# Find trust path between users
brandme graph path --from alice0 --to bob10

# Query provenance
brandme graph query "Show me the provenance chain for garment TAG-000001"

# Get creator info
brandme graph query "Who created garment TAG-000001?"
```

### 4. View in Neo4j Browser

```bash
# Open Neo4j
open http://[YOUR-IP]:7474

# Login with credentials
# Run Cypher query:
MATCH (u:User)-[:OWNS]->(g:Garment) RETURN u, g LIMIT 50
```

---

## 💰 Costs

**Monthly estimate** (with default settings):

- GCP Infrastructure: ~$225/month
  - GKE cluster (3 nodes): ~$150
  - Cloud SQL: ~$50
  - Storage & networking: ~$25

- API Usage: ~$70/month
  - Claude API: ~$50
  - OpenAI embeddings: ~$20
  - Blockfrost: $0 (free tier)

**Total: ~$295/month**

To reduce costs:
- Use smaller cluster: `CLUSTER_SIZE=small` in `.env.deploy`
- Reduce test data: `TEST_DATA_SIZE=small`
- Scale down after testing: `kubectl scale deployment --replicas=1`

---

## 📚 What's Included

### Services Deployed

1. **brandme-gateway**: API Gateway with auth and rate limiting
2. **brandme-chain**: Cardano + Midnight blockchain integration
3. **brandme-core**: AI Brain, Policy Engine, Orchestrator
4. **brandme-agents**: Identity, Knowledge, Compliance agents
5. **brandme-console**: Web UI (Governance + Transparency)
6. **Neo4j**: Knowledge graph database
7. **PostgreSQL**: Relational database

### AI Agents

- **Scan Agent**: Resolves garment identifiers
- **Identity Agent**: Analyzes trust relationships
- **Knowledge Agent**: Queries knowledge graph
- **Policy Agent**: Makes consent-driven decisions
- **Blockchain Agent**: Anchors to dual chains

### Features

- ✅ **Graph RAG**: Natural language queries on knowledge graph
- ✅ **Multi-Agent Orchestration**: LangGraph workflows
- ✅ **Human-in-the-Loop**: Governance approval for edge cases
- ✅ **Blockchain Verification**: Cardano + Midnight anchoring
- ✅ **Event-Driven**: NATS JetStream messaging
- ✅ **Autoscaling**: HPA based on CPU/memory
- ✅ **Monitoring**: Built-in health checks
- ✅ **Secure**: Auto-generated passwords, secret management

---

## 📖 Documentation

**Quick Reference:**
- **DEPLOYMENT.md**: Detailed deployment guide
- **ARCHITECTURE.md**: Technical architecture
- **AGENTIC_ARCHITECTURE.md**: AI agent system
- **PROJECT_STATUS.md**: Complete implementation status
- **README.md**: Platform overview

**API Documentation:**
- Gateway: `http://[YOUR-IP]/docs`
- Compliance: `http://[YOUR-IP]:8102/docs`

---

## 🔧 Common Commands

```bash
# Check deployment status
kubectl get all -n brandme

# View logs
kubectl logs -n brandme -l app=brandme-gateway --tail=100

# Scale services
kubectl scale deployment brandme-gateway --replicas=5 -n brandme

# Restart service
kubectl rollout restart deployment/brandme-gateway -n brandme

# View credentials
cat .deployment/credentials.txt

# Check deployment report
cat .deployment/DEPLOYMENT_REPORT.md

# Re-run specific agent
./agents/testing-agent.sh
```

---

## 🆘 Troubleshooting

### Deployment Failed?

```bash
# Check logs
cat deployment-[timestamp].log

# View deployment state
ls -la .deployment/

# Retry specific agent
./agents/infrastructure-agent.sh
```

### Service Not Responding?

```bash
# Check pod status
kubectl get pods -n brandme

# View pod logs
kubectl logs -n brandme [pod-name]

# Describe pod
kubectl describe pod -n brandme [pod-name]
```

### Need to Rollback?

```bash
# Delete namespace (removes all services)
kubectl delete namespace brandme

# Destroy infrastructure
cd brandme-infra/terraform
terraform destroy
```

---

## 🚀 Next Steps

### 1. Customize

- Edit policies: `brandme-core/policies/region/*.yaml`
- Add agents: `brandme-agents/agentic/orchestrator/agents.py`
- Customize UI: `brandme-console/app/`

### 2. Import Real Data

```bash
# Import users from CSV
brandme import users --file users.csv

# Sync from existing database
brandme sync --source postgresql://old-db
```

### 3. Set Up Domain

```bash
# Point DNS to load balancer IP
# A record: brandme.example.com → [YOUR-IP]

# Enable SSL
# Edit .env.deploy: SSL_MODE=auto
# Re-run: ./agents/service-agent.sh
```

### 4. Monitor

```bash
# View Grafana dashboards
open http://[YOUR-IP]:3000

# Set up alerts
kubectl apply -f monitoring/alerts.yaml
```

---

## 💡 Tips

**Development:**
- Use `kubectl port-forward` for local access
- Enable debug logging: `LOG_LEVEL=DEBUG`
- Use `brandme-console` for visual debugging

**Production:**
- Enable backups: `ENABLE_BACKUPS=true`
- Set up monitoring alerts
- Use separate projects for dev/staging/prod
- Rotate API keys regularly

**Cost Optimization:**
- Use preemptible nodes for non-critical workloads
- Schedule scale-down during off-hours
- Use committed use discounts on GCP

---

## 📞 Support

**Issues?**
- Check logs first: `kubectl logs -n brandme -l app=brandme-gateway`
- Review documentation: See README.md, ARCHITECTURE.md
- GitHub Issues: https://github.com/brandmeonline/Brand-Me-Labs/issues

**Want to contribute?**
- Read ARCHITECTURE.md for technical details
- Check PROJECT_STATUS.md for current state
- Submit PRs with clear descriptions

---

## ✅ Success Checklist

After deployment, verify:

- [ ] All services healthy: `kubectl get pods -n brandme`
- [ ] Database accessible: Check credentials.txt
- [ ] API responding: `curl http://[YOUR-IP]/health`
- [ ] Console accessible: Open in browser
- [ ] Neo4j populated: Check browser at :7474
- [ ] Test scan works: Run example curl command
- [ ] Agents working: Check logs for agent activity
- [ ] Blockchain integration: Verify tx hashes in logs

**All checks passed?** 🎉 **You're live in production!**

---

**Ready to deploy? Run:**

```bash
./deploy-brandme.sh
```

**Questions?** See DEPLOYMENT.md for detailed documentation.

---

**Generated**: 2025-10-25
**Branch**: `claude/init-brandme-architecture-011CUUTWSZ2w2Q6fWXQFjVrJ`
