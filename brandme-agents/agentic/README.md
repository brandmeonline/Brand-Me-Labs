# Brand.Me Agentic System

**Copyright (c) Brand.Me, Inc. All rights reserved.**

AI-native agent framework with knowledge graphs, Graph RAG, and human-in-the-loop workflows.

---

## Overview

Transform Brand.Me into an agentic company where intelligent AI agents handle operations with strategic human oversight.

### Key Features

- **Knowledge Graph**: Neo4j-based graph database with vector embeddings
- **Graph RAG**: Natural language querying with LLM synthesis
- **Multi-Agent System**: LangGraph orchestration with specialized agents
- **Human-in-the-Loop**: Escalation workflows with governance approval
- **Agent Tools**: 15+ tools for graph queries, blockchain, policy evaluation
- **CLI**: Rich command-line interface for agent operations

---

## Architecture

```
┌─────────────────────────────────────┐
│   Human Governance Console          │
│   (Approvals & Oversight)           │
└─────────────────────────────────────┘
                 ▲
                 │ Escalations
                 │
┌─────────────────────────────────────┐
│   LangGraph Agent Orchestration     │
│   ┌───────┐ ┌───────┐ ┌───────┐   │
│   │ Scan  │ │Policy │ │ Block │   │
│   │ Agent │ │ Agent │ │ Agent │   │
│   └───────┘ └───────┘ └───────┘   │
└─────────────────────────────────────┘
                 ▲
                 │ Context & Tools
                 │
┌─────────────────────────────────────┐
│   Neo4j Knowledge Graph + RAG       │
│   (Entities, Relationships, Vectors)│
└─────────────────────────────────────┘
```

---

## Installation

### Prerequisites

- Python 3.11+
- Neo4j 5.16+ (with APOC and GDS plugins)
- Anthropic API key
- OpenAI API key (for embeddings)

### Setup

```bash
# Navigate to agentic directory
cd brandme-agents/agentic

# Install dependencies
pip install -r requirements.txt

# Or install as package
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your API keys and Neo4j credentials
```

### Neo4j Setup

```bash
# Run Neo4j with Docker
docker run \
    --name brandme-neo4j \
    -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH=neo4j/your-password \
    -e NEO4J_PLUGINS='["apoc", "graph-data-science"]' \
    neo4j:5.16-enterprise

# Or use Neo4j Desktop/AuraDB
```

---

## Quick Start

### 1. Initialize Knowledge Graph

```python
from brandme_agentic import get_knowledge_graph

# Connect to Neo4j
graph = get_knowledge_graph()

# Create sample data
graph.create_user({
    "user_id": "user-alice",
    "handle": "Alice",
    "did_cardano": "addr1...",
    "trust_score": 0.95,
    "persona_vector": [0.1, 0.2, ...]  # 512-dim vector
})

graph.create_garment({
    "garment_id": "garment-123",
    "garment_tag": "garment-tag-xyz",
    "creator_id": "creator-1",
    "authenticity_hash": "sha256...",
    "embedding": [0.3, 0.4, ...]  # 512-dim vector
})

graph.create_ownership("user-alice", "garment-123", "2025-01-01T00:00:00Z")
```

### 2. Query with Graph RAG

```python
from brandme_agentic import get_graph_rag

graph_rag = get_graph_rag()

# Natural language query
result = graph_rag.query(
    "Show me the provenance chain for garment-123",
    include_reasoning=True
)

print(result["answer"])
print(result["cypher_query"])  # See generated Cypher
```

### 3. Run Agent Workflow

```python
from brandme_agentic import run_scan_workflow

# Execute full scan workflow
result = run_scan_workflow(
    garment_tag="garment-tag-xyz",
    scanner_user_id="user-bob"
)

print(f"Decision: {result['decision']}")
print(f"Scope: {result['resolved_scope']}")
print(f"Reasoning: {result['policy_reasoning']}")
```

### 4. Use CLI

```bash
# Scan garment
brandme scan --tag garment-xyz --scanner-id user-123

# Query graph
brandme graph query "Find trust path between Alice and Bob"

# Find path
brandme graph path --from user-alice --to user-bob

# Get provenance
brandme graph provenance garment-123

# Verify blockchain
brandme blockchain verify --tx-hash abc123... --chain cardano

# Agent status
brandme agent status

# List approvals
brandme approval list --status pending
```

---

## Agent Types

### Scan Agent
- Resolves garment_tag → garment_id
- Initiates workflow
- Gathers initial context

### Identity Agent
- Analyzes user relationships
- Calculates trust scores
- Finds trust paths in social graph

### Knowledge Agent
- Retrieves garment data via Graph RAG
- Fetches provenance chains
- Finds similar garments

### Policy Agent
- Makes consent-driven decisions
- Evaluates regional compliance
- Generates explainable reasoning
- Escalates when uncertain

### Blockchain Agent
- Anchors to Cardano (public data)
- Anchors to Midnight (private data)
- Computes cross-chain root hash
- Verifies transactions

---

## Agent Tools

### Graph Tools
- `graph_query_tool()`: Natural language to Cypher
- `find_trust_path_tool()`: Social graph navigation
- `get_provenance_tool()`: Ownership history
- `find_similar_garments_tool()`: Vector similarity
- `get_user_social_graph_tool()`: Network analysis

### Blockchain Tools
- `build_cardano_tx_tool()`: Build Cardano transaction
- `build_midnight_tx_tool()`: Build Midnight transaction
- `verify_blockchain_tx_tool()`: Verify on-chain
- `compute_cross_chain_root_tool()`: Link both chains

### Policy Tools
- `evaluate_policy_tool()`: Policy decision
- `check_consent_tool()`: User consent check
- `check_regional_compliance_tool()`: GDPR/CCPA/etc.
- `explain_policy_decision_tool()`: Explainability
- `escalate_for_human_review_tool()`: Human-in-the-loop

---

## Human-in-the-Loop

Agents escalate to humans when:
1. Policy decision is "escalate"
2. Trust score below threshold
3. Counterfeit detected
4. High-value garment
5. First-time user
6. Anomaly detected

### Approval Workflow

```python
# Agent escalates
state["requires_human_approval"] = True
state["escalation_reason"] = "First-time scanner with high-value garment"

# Human reviews in console
# - See agent reasoning
# - View graph context
# - Make decision

# Workflow resumes
state["decision"] = "allow"  # or "deny"
```

---

## Configuration

### Environment Variables

```bash
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# LLMs
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Services
CHAIN_SERVICE_URL=http://localhost:3001
POLICY_SERVICE_URL=http://localhost:8103
```

### Agent Configuration

```python
# Custom LLM
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",
    temperature=0,
    max_tokens=4000
)

# Custom workflow
workflow = create_agent_workflow()
result = workflow.invoke(initial_state)
```

---

## Development

### Run Tests

```bash
pytest tests/
```

### Add New Agent

```python
# orchestrator/agents.py

class MyCustomAgent:
    def __init__(self, llm, graph_rag):
        self.llm = llm
        self.graph_rag = graph_rag

    def __call__(self, state: AgentState) -> AgentState:
        # Your logic here
        state["custom_field"] = "value"
        return state

# Add to workflow
workflow.add_node("my_agent", my_custom_agent)
```

### Add New Tool

```python
# tools/my_tools.py

from langchain.tools import tool

@tool
def my_custom_tool(param: str) -> dict:
    """
    Tool description for LLM.

    Args:
        param: Parameter description

    Returns:
        Result dictionary
    """
    # Your logic
    return {"result": "value"}
```

---

## Examples

See `AGENTIC_ARCHITECTURE.md` for:
- Complete architecture overview
- Detailed agent specifications
- Graph schema documentation
- Tool catalogs
- Implementation roadmap

---

## Performance

### Benchmarks
- Graph query: < 100ms
- Vector search: < 50ms
- Agent workflow: 2-5 seconds
- LLM reasoning: 1-2 seconds per agent

### Optimization
- Cache frequently queried paths
- Batch vector searches
- Use graph projections for analytics
- Implement result pagination

---

## Security

- **No PII in Logs**: All user data redacted
- **Encrypted Neo4j**: Use TLS for production
- **API Key Rotation**: Regular key updates
- **Audit Trail**: All decisions logged
- **Access Control**: RBAC for agent operations

---

## Troubleshooting

### Neo4j Connection Issues

```bash
# Check Neo4j is running
docker ps | grep neo4j

# Test connection
neo4j-admin status

# Check logs
docker logs brandme-neo4j
```

### LLM API Errors

```python
# Check API key
print(os.getenv("ANTHROPIC_API_KEY"))

# Test connection
from anthropic import Anthropic
client = Anthropic()
print(client.messages.create(...))
```

### Agent Workflow Failures

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check state
result = run_scan_workflow(...)
print(result["messages"])  # See all agent communications
```

---

## Roadmap

### Phase 1: Foundation ✅
- Neo4j integration
- Graph RAG
- Basic agents
- CLI

### Phase 2: Advanced (In Progress)
- Memory systems
- Multi-agent collaboration
- Advanced analytics
- Real-time updates

### Phase 3: Production
- Scalability improvements
- Performance optimization
- Security hardening
- Monitoring dashboard

---

## Support

- **Documentation**: See `AGENTIC_ARCHITECTURE.md`
- **Issues**: GitHub Issues
- **Slack**: #brandme-agentic

---

## License

Copyright (c) 2025 Brand.Me, Inc. All rights reserved.
