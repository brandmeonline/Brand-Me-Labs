# Brand.Me Agentic Architecture

**Copyright (c) Brand.Me, Inc. All rights reserved.**

## Vision: Agentic Company with Human-in-the-Loop

Transform Brand.Me into an AI-native company where intelligent agents handle operations with strategic human oversight.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Human-in-the-Loop Layer                      │
│  (Governance Console with Approval Workflows & Oversight)        │
└─────────────────────────────────────────────────────────────────┘
                                ▲
                                │ Escalations & Approvals
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Orchestration Layer                     │
│  (LangGraph Multi-Agent System with Tool Calling)                │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Scan       │  │  Compliance  │  │  Blockchain  │          │
│  │   Agent      │  │  Agent       │  │  Agent       │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Identity    │  │  Knowledge   │  │  Analytics   │          │
│  │  Agent       │  │  Agent       │  │  Agent       │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                ▲
                                │ Context & Tools
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    Knowledge Graph Layer                         │
│  (Neo4j Graph Database + Vector Embeddings)                      │
│                                                                   │
│  Entities: Users, Garments, Creators, Brands, Scans,            │
│           Relationships, Policies, Transactions                  │
│                                                                   │
│  Graph RAG: Semantic search + Graph traversal + LLM synthesis    │
└─────────────────────────────────────────────────────────────────┘
                                ▲
                                │ Data Integration
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    Existing Services Layer                       │
│  (PostgreSQL, NATS, Cardano, Midnight)                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Knowledge Graph Layer

### 1.1 Graph Schema

**Entities (Nodes):**
```
User {
  user_id: UUID
  handle: string
  did_cardano: string
  trust_score: float
  persona_vector: vector(512)  // Embedding for semantic search
}

Garment {
  garment_id: UUID
  garment_tag: string
  creator_id: UUID
  authenticity_hash: string
  embedding: vector(512)  // Visual + text embedding
}

Creator {
  creator_id: UUID
  creator_name: string
  brand: string
  reputation_score: float
  style_embedding: vector(512)
}

Brand {
  brand_id: UUID
  brand_name: string
  esg_score: string
  region_codes: [string]
}

Scan {
  scan_id: UUID
  timestamp: datetime
  decision: string
  policy_version: string
  cardano_tx_hash: string
}

Policy {
  policy_id: UUID
  version: string
  region_code: string
  rules_embedding: vector(512)
}
```

**Relationships (Edges):**
```
(User)-[:OWNS]->(Garment)
(User)-[:SCANNED]->(Garment)
(User)-[:FRIENDS_WITH]->(User)
(Garment)-[:CREATED_BY]->(Creator)
(Creator)-[:WORKS_FOR]->(Brand)
(Garment)-[:VERIFIED_BY]->(Scan)
(Scan)-[:ANCHORED_TO]->(BlockchainTx)
(Scan)-[:ENFORCED_BY]->(Policy)
(User)-[:TRUSTS]->(User) {trust_weight: float}
(Garment)-[:SIMILAR_TO]->(Garment) {similarity: float}
```

### 1.2 Graph RAG Implementation

**Query Pipeline:**
1. **Natural Language → Cypher**: LLM converts questions to graph queries
2. **Vector Search**: Find semantically similar entities
3. **Graph Traversal**: Navigate relationships
4. **Context Assembly**: Gather relevant subgraph
5. **LLM Synthesis**: Generate answer from graph context

**Example Queries:**
- "Show me all garments by creators the user trusts"
- "Find similar garments with better ESG scores"
- "What's the provenance chain for this garment?"
- "Which policies apply to this scan in EU region?"

---

## 2. Agent System Architecture

### 2.1 Agent Orchestration (LangGraph)

**Core Framework:**
```python
# brandme-agents/agentic/orchestrator.py

from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from typing import TypedDict, Annotated, Sequence
import operator

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    scan_id: str
    garment_id: str
    user_id: str
    decision: str
    escalation_reason: str | None
    requires_human_approval: bool
    graph_context: dict

# Define agent workflow
workflow = StateGraph(AgentState)

workflow.add_node("scan_agent", scan_agent_node)
workflow.add_node("identity_agent", identity_agent_node)
workflow.add_node("policy_agent", policy_agent_node)
workflow.add_node("knowledge_agent", knowledge_agent_node)
workflow.add_node("blockchain_agent", blockchain_agent_node)
workflow.add_node("human_approval", human_approval_node)

# Define edges (workflow)
workflow.set_entry_point("scan_agent")
workflow.add_edge("scan_agent", "identity_agent")
workflow.add_edge("identity_agent", "knowledge_agent")
workflow.add_edge("knowledge_agent", "policy_agent")

# Conditional routing
workflow.add_conditional_edges(
    "policy_agent",
    should_escalate,  # Function that checks if human approval needed
    {
        True: "human_approval",
        False: "blockchain_agent"
    }
)
```

### 2.2 Individual Agent Definitions

#### Scan Agent
**Purpose**: Coordinate garment scan workflow
**Tools**:
- `lookup_garment_by_tag(tag: str) -> UUID`
- `get_scan_history(garment_id: UUID) -> list[Scan]`
- `create_scan_event(data: dict) -> UUID`

**Behavior**: Orchestrates scan initiation and context gathering

---

#### Identity Agent
**Purpose**: User identity and relationship verification
**Tools**:
- `get_user_profile(user_id: UUID) -> User`
- `check_relationship(user1: UUID, user2: UUID) -> Relationship`
- `calculate_trust_score(user_id: UUID) -> float`
- `query_social_graph(user_id: UUID, depth: int) -> Graph`

**Behavior**: Determines scanner's relationship to garment owner

---

#### Knowledge Agent
**Purpose**: Garment information retrieval with Graph RAG
**Tools**:
- `graph_rag_query(question: str) -> dict`
- `get_garment_passport(garment_id: UUID, scope: str) -> dict`
- `find_similar_garments(garment_id: UUID, threshold: float) -> list`
- `get_creator_attribution(creator_id: UUID) -> dict`
- `get_provenance_chain(garment_id: UUID) -> list[dict]`

**Behavior**: Intelligent information retrieval using knowledge graph

---

#### Policy Agent
**Purpose**: Compliance and policy enforcement with reasoning
**Tools**:
- `evaluate_policy(scan_data: dict) -> PolicyDecision`
- `explain_policy_decision(decision: dict) -> str`
- `check_regional_compliance(region: str, action: str) -> bool`
- `graph_query_applicable_policies(context: dict) -> list[Policy]`

**Behavior**: Makes policy decisions with explainability

---

#### Blockchain Agent
**Purpose**: Transaction building and verification
**Tools**:
- `build_cardano_tx(data: dict) -> str`
- `build_midnight_tx(data: dict) -> str`
- `verify_tx(tx_hash: str, chain: str) -> bool`
- `compute_cross_chain_hash(cardano_tx: str, midnight_tx: str) -> str`
- `query_blockchain_history(garment_id: UUID) -> list[Tx]`

**Behavior**: Anchors data to blockchain with verification

---

#### Analytics Agent
**Purpose**: Pattern detection and insights
**Tools**:
- `detect_counterfeit_patterns() -> list[Alert]`
- `analyze_esg_trends(timeframe: str) -> dict`
- `identify_trust_network_anomalies() -> list[Anomaly]`
- `generate_compliance_report(period: str) -> Report`

**Behavior**: Proactive monitoring and insights

---

### 2.3 Human-in-the-Loop Integration

**Approval Workflows:**

```python
# When to escalate to human:
1. Policy decision is "escalate"
2. Trust score below threshold
3. Counterfeit detected
4. Controlled reveal requested
5. High-value garment (above $X)
6. First-time user
7. Anomaly detected by analytics agent
```

**Approval UI:**
- Show agent's reasoning
- Display graph context (related entities)
- Present recommendations
- Allow override with justification
- Log decision to audit trail

---

## 3. Agent Tools & Capabilities

### 3.1 Tool Definitions

```python
# brandme-agents/agentic/tools/graph_tools.py

from langchain.tools import tool

@tool
def graph_rag_query(question: str) -> dict:
    """
    Answer questions using the knowledge graph with RAG.

    Args:
        question: Natural language question about garments, users, or relationships

    Returns:
        dict with answer, context, and source entities
    """
    # 1. Generate embedding for question
    # 2. Vector search for relevant entities
    # 3. Expand to subgraph
    # 4. Synthesize answer with LLM
    pass

@tool
def find_trust_path(user1: str, user2: str) -> list[dict]:
    """
    Find trust path between two users in social graph.

    Args:
        user1: First user ID
        user2: Second user ID

    Returns:
        Shortest path with trust scores
    """
    # Use graph algorithms (Dijkstra, etc.)
    pass

@tool
def get_provenance_chain(garment_id: str) -> list[dict]:
    """
    Get full provenance chain from creator to current owner.

    Args:
        garment_id: Garment UUID

    Returns:
        Ordered list of ownership events with blockchain proofs
    """
    # Traverse ownership relationships
    pass
```

### 3.2 Tool Categories

**Graph Query Tools:**
- `graph_rag_query()`: Natural language to graph query
- `find_trust_path()`: Social graph navigation
- `get_provenance_chain()`: Ownership history
- `find_similar_entities()`: Semantic similarity search

**Blockchain Tools:**
- `verify_cardano_tx()`: Verify Cardano transaction
- `verify_midnight_tx()`: Verify Midnight transaction
- `compute_merkle_proof()`: Generate cryptographic proof
- `anchor_to_chains()`: Dual-chain anchoring

**Policy Tools:**
- `evaluate_consent()`: Check user consent policies
- `check_regional_law()`: Verify regional compliance
- `explain_decision()`: Policy explainability
- `suggest_policy_update()`: Recommend policy changes

**Analytics Tools:**
- `detect_anomalies()`: Pattern detection
- `predict_counterfeit_risk()`: Risk scoring
- `analyze_trust_network()`: Graph analysis
- `generate_insights()`: Business intelligence

---

## 4. Agent Commands & CLI

### 4.1 Command System

```bash
# brandme-agents/agentic/cli.py

# Scan workflow
brandme scan --tag "garment-xyz" --scanner-id "user-123"

# Policy evaluation
brandme policy evaluate --scan-id "scan-456" --explain

# Graph queries
brandme graph query "Show me all garments by creators Alice trusts"
brandme graph path --from user-1 --to user-2 --type trust

# Blockchain operations
brandme blockchain verify --tx-hash "abc123..." --chain cardano
brandme blockchain anchor --scan-id "scan-789"

# Analytics
brandme analytics detect-counterfeits --timeframe "7d"
brandme analytics trust-network --user-id "user-123" --depth 3

# Human approval
brandme approval list --status pending
brandme approval approve --scan-id "scan-456" --approver-id "gov-1"

# Agent management
brandme agent status  # Show all agents
brandme agent logs --agent scan_agent --tail 100
brandme agent restart --agent policy_agent
```

### 4.2 Agent API Endpoints

```typescript
// brandme-gateway/src/routes/agent.ts

// Trigger agent workflow
POST /agent/workflow/scan
{
  "garment_tag": "garment-xyz",
  "scanner_user_id": "user-123",
  "context": {...}
}

// Query via Graph RAG
POST /agent/query
{
  "question": "Show me the provenance chain for garment-xyz",
  "include_reasoning": true
}

// Human approval
POST /agent/approval/request
{
  "scan_id": "scan-456",
  "reason": "Policy escalation",
  "agent_reasoning": "..."
}

POST /agent/approval/respond
{
  "approval_id": "approval-789",
  "decision": "approve",
  "justification": "..."
}
```

---

## 5. Memory Systems

### 5.1 Agent Memory Architecture

```python
# Short-term Memory (per conversation)
class ConversationMemory:
    messages: list[Message]
    context: dict
    entities_mentioned: set[str]

# Long-term Memory (persistent)
class LongTermMemory:
    user_preferences: dict
    historical_decisions: list[Decision]
    learned_patterns: dict

# Graph Memory (knowledge graph)
class GraphMemory:
    entity_embeddings: dict[str, vector]
    relationship_weights: dict[tuple, float]
    pattern_templates: list[Pattern]
```

### 5.2 Memory Integration

**Per-Agent Memory:**
- Scan Agent: Recent scans, common patterns
- Policy Agent: Historical decisions, regional nuances
- Knowledge Agent: Frequently queried entities
- Blockchain Agent: Transaction patterns

**Shared Memory:**
- Cross-agent learnings
- User interaction patterns
- System-wide insights

---

## 6. Implementation Roadmap

### Phase 1: Knowledge Graph Foundation (Week 1-2)
- [ ] Set up Neo4j database
- [ ] Define graph schema
- [ ] Build data pipeline from PostgreSQL → Neo4j
- [ ] Implement vector embeddings
- [ ] Create basic Cypher queries

### Phase 2: Graph RAG (Week 2-3)
- [ ] Implement vector search
- [ ] Build NL → Cypher translation
- [ ] Create graph traversal algorithms
- [ ] Implement RAG pipeline
- [ ] Test with example queries

### Phase 3: Agent Framework (Week 3-4)
- [ ] Set up LangGraph orchestration
- [ ] Define agent state machines
- [ ] Implement individual agents
- [ ] Create tool functions
- [ ] Build agent communication

### Phase 4: Human-in-the-Loop (Week 4-5)
- [ ] Design approval workflows
- [ ] Build approval UI in console
- [ ] Implement escalation logic
- [ ] Add audit logging
- [ ] Test approval flows

### Phase 5: CLI & Commands (Week 5-6)
- [ ] Create CLI framework
- [ ] Implement commands
- [ ] Add agent management
- [ ] Build monitoring dashboard
- [ ] Documentation

### Phase 6: Memory & Learning (Week 6-7)
- [ ] Implement memory systems
- [ ] Add pattern learning
- [ ] Build feedback loops
- [ ] Create analytics
- [ ] Performance optimization

---

## 7. Technology Stack

### LLM & Agents
- **LangChain**: Agent framework and tools
- **LangGraph**: Multi-agent orchestration
- **Anthropic Claude**: Primary LLM (supports tool use)
- **OpenAI GPT-4**: Alternative LLM

### Knowledge Graph
- **Neo4j**: Graph database
- **neo4j-python-driver**: Python integration
- **GDS Library**: Graph data science algorithms

### Vector Search
- **OpenAI Embeddings**: Text embeddings
- **CLIP**: Image + text embeddings
- **Neo4j Vector Index**: Native vector search

### Agent Tools
- **LangChain Tools**: Standard tool interfaces
- **Custom Tools**: Brand.Me-specific operations

---

## 8. Example: Complete Agentic Scan Workflow

```
1. User scans garment tag
   └─> Scan Agent receives request

2. Scan Agent queries knowledge graph
   └─> Graph RAG: "What do we know about this garment?"
   └─> Returns: Creator, previous scans, ownership history

3. Identity Agent evaluates scanner
   └─> Checks trust score
   └─> Finds trust path to owner via social graph
   └─> Returns: relationship="friend", trust_score=0.85

4. Knowledge Agent gathers context
   └─> Graph query: Find similar garments, ESG data
   └─> Returns: Full passport with consent-filtered data

5. Policy Agent makes decision
   └─> Evaluates regional policies
   └─> Checks consent rules
   └─> LLM reasons about edge cases
   └─> Decision: "allow" with scope="friends_only"

6. Blockchain Agent anchors data
   └─> Builds Cardano tx with metadata
   └─> Builds Midnight tx with private data
   └─> Submits to chains
   └─> Returns: tx hashes

7. Analytics Agent learns
   └─> Updates trust network weights
   └─> Records scan pattern
   └─> Checks for anomalies
   └─> Returns: no_anomalies_detected

8. Response to user
   └─> Allowed facets returned
   └─> Blockchain proof provided
   └─> Agent reasoning logged
```

**If Escalation Needed:**
```
5a. Policy Agent escalates
    └─> Reason: "High-value garment + first-time scanner"
    └─> Creates approval request

5b. Human approver notified
    └─> Console shows: Agent reasoning, graph context, recommendation
    └─> Human decides: Approve/Deny/Request more info

5c. Workflow resumes
    └─> Continue to step 6 if approved
```

---

## 9. Governance & Oversight

### Human-in-the-Loop Principles
1. **Transparent Reasoning**: Always show agent logic
2. **Explainable Decisions**: Natural language explanations
3. **Audit Trail**: Every agent action logged
4. **Override Capability**: Humans can override any decision
5. **Feedback Loop**: Human decisions improve agent learning

### Governance Roles
- **Governance Team**: Strategic oversight, policy updates
- **Compliance Team**: Approve escalations, audit reviews
- **Operations Team**: Monitor agents, handle exceptions
- **Data Team**: Improve graph, tune embeddings

---

## 10. Metrics & Monitoring

### Agent Performance
- Decision accuracy
- Escalation rate
- Response time
- Graph query efficiency
- Human approval rate

### Business Metrics
- Scans per day
- Counterfeit detection rate
- User trust score trends
- ESG compliance rate
- Blockchain verification success

### Agent Health
- Memory usage
- Graph query latency
- LLM token usage
- Tool execution time
- Error rates

---

**Next Steps**: Begin Phase 1 implementation of Knowledge Graph foundation.
