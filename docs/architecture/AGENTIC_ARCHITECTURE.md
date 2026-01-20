# Brand.Me Agentic Architecture (v9)

**Copyright (c) Brand.Me, Inc. All rights reserved.**

## Vision: Agentic Company with Human-in-the-Loop

Transform Brand.Me into an AI-native company where intelligent agents handle operations with strategic human oversight. External agents access the Style Vault through Model Context Protocol (MCP).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Human-in-the-Loop Layer                      │
│          (Governance Console with Approval Workflows)            │
└─────────────────────────────────────────────────────────────────┘
                                ▲
                                │ Escalations & Approvals
                                │
┌─────────────────────────────────────────────────────────────────┐
│                  External Agent Layer (MCP)                      │
│         Claude, GPT, Gemini, Custom AI Assistants               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ MCP Tools (7 tools)
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Orchestration Layer                     │
│            (LangGraph Multi-Agent with ESG Verification)         │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Scan       │  │  Compliance  │  │  Blockchain  │          │
│  │   Agent      │  │  Agent       │  │  Agent       │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Identity    │  │   Policy     │  │  Knowledge   │          │
│  │  Agent       │  │   Agent      │  │  Agent       │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ Graph Queries + ESG Verification
                                │
┌─────────────────────────────────────────────────────────────────┐
│                   Data & Verification Layer                      │
│                                                                   │
│  ┌──────────────────────────┐  ┌──────────────────────────┐    │
│  │ Google Cloud Spanner     │  │ Cardano ESG Oracle       │    │
│  │ Native Property Graph    │  │ ESGVerifier              │    │
│  │ O(1) Consent Lookups     │  │                          │    │
│  └──────────────────────────┘  └──────────────────────────┘    │
│                                                                   │
│  ┌──────────────────────────┐  ┌──────────────────────────┐    │
│  │ Firestore Real-time      │  │ Midnight Burn Proofs     │    │
│  │ AR Glasses <100ms        │  │ BurnProofVerifier        │    │
│  └──────────────────────────┘  └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. MCP Integration Layer

### 1.1 Available Tools

External agents access Brand.Me through 7 MCP tools:

| Tool | Category | ESG Check | Description |
|------|----------|-----------|-------------|
| `search_wardrobe` | search | No | Search user's Style Vault |
| `get_cube_details` | view | No | Get Product Cube details |
| `suggest_outfit` | style | No | AI outfit suggestions |
| `initiate_rental` | transaction | Yes | Start rental process |
| `list_for_resale` | transaction | Yes | List item for resale |
| `request_repair` | lifecycle | No | Request repair service |
| `request_dissolve` | lifecycle | Yes | Request material dissolution |

### 1.2 Tool Definitions

```python
# brandme_core/mcp/tools.py

MCP_TOOLS = [
    {
        "name": "search_wardrobe",
        "description": "Search user's Style Vault by category, color, or brand",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "query": {"type": "string"},
                "filters": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "color": {"type": "string"},
                        "brand": {"type": "string"}
                    }
                }
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "initiate_rental",
        "description": "Initiate rental of an item (requires ESG verification)",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "asset_id": {"type": "string"},
                "rental_duration_days": {"type": "integer"},
                "price_per_day": {"type": "number"}
            },
            "required": ["user_id", "asset_id", "rental_duration_days"]
        }
    }
]
```

### 1.3 Transaction Requirements

All transaction tools enforce:

1. **User Consent**: Verified via `ConsentedByAgent` table
2. **ESG Verification**: Cardano oracle check via `ESGVerifier`
3. **Human Approval**: Optional for high-value transactions
4. **Audit Trail**: `AgentTransaction` record in Spanner

```python
# Transaction flow for MCP tools
async def handle_mcp_transaction(tool_name: str, params: dict):
    # 1. Verify agent has user consent
    consent = await check_agent_consent(params["user_id"], agent_id)
    if not consent.is_valid:
        return {"error": "Agent not authorized by user"}

    # 2. ESG verification for transaction tools
    if tool_name in ["initiate_rental", "list_for_resale", "request_dissolve"]:
        esg_result = await esg_verifier.verify_transaction(
            asset_id=params["asset_id"],
            material_id=asset.primary_material_id,
            transaction_type=tool_name,
            agent_id=agent_id
        )
        if not esg_result.is_approved:
            return {"error": esg_result.reason, "requires_human_review": True}

    # 3. Record transaction
    await record_agent_transaction(agent_id, params, esg_result)

    # 4. Execute action
    return await execute_tool(tool_name, params)
```

---

## 2. Agent System Architecture

### 2.1 Agent State Model

```python
# brandme-agents/agentic/orchestrator/agents.py

class AgentState(TypedDict):
    """State model for agent graph."""
    request_id: Optional[str]
    scan_id: Optional[str]
    scanner_user_id: Optional[str]
    garment_id: Optional[str]
    garment_tag: Optional[str]
    region_code: Optional[str]
    policy_decision: Optional[str]
    resolved_scope: Optional[str]
    policy_version: Optional[str]
    requires_human_approval: Optional[bool]
    facets: Optional[list]
    cardano_tx_hash: Optional[str]
    midnight_tx_hash: Optional[str]
    error: Optional[str]
    escalation_id: Optional[str]
```

### 2.2 Agent Workflow

```python
async def run_agent_workflow(
    initial_state: AgentState,
    http_client: Optional[httpx.AsyncClient] = None
) -> AgentState:
    """
    Execute agent workflow with proper escalation handling.

    Workflow:
    1. ScanAgent: Resolve asset_id from physical_tag_id
    2. IdentityAgent: Fetch user profile and consent graph
    3. PolicyAgent: Check consent and region policies
    4. ComplianceAgent: ESG verification, fetch facets, audit log
    """
    state = initial_state.copy()

    # Step 1: Scan Agent
    state = scan_agent(state)

    # Step 2: Identity Agent
    state = identity_agent(state)

    # Step 3: Policy Agent
    state = policy_agent(state)

    # Step 4: Check if escalation required
    if should_escalate(state) == "escalate":
        # Register escalation, halt automation
        state = await compliance_agent(state, http_client)
        return state  # Wait for human approval

    # Step 5: Compliance Agent (only if not escalated)
    state = await compliance_agent(state, http_client)

    return state
```

### 2.3 Escalation Logic

```python
def should_escalate(state: AgentState) -> str:
    """
    Conditional routing: determine if escalation is required.

    Escalate when:
    - policy_decision == "escalate"
    - requires_human_approval == True
    - Trust score below threshold
    - High-value transaction
    - Counterfeit detected
    """
    if state.get("requires_human_approval"):
        return "escalate"
    if state.get("policy_decision") == "escalate":
        return "escalate"
    return "continue"
```

---

## 3. Individual Agent Definitions

### 3.1 Scan Agent

**Purpose**: Resolve physical tag to asset ID

**Implementation**:
```python
def scan_agent(state: AgentState) -> AgentState:
    """Resolve garment_tag -> asset_id via Spanner."""
    # Query Spanner for asset by physical_tag_id
    asset_id = lookup_asset_by_tag(state.get("garment_tag"))
    state["garment_id"] = asset_id
    return state
```

**Tools**:
- `lookup_asset_by_tag(tag: str) -> str` - Spanner query
- `get_scan_history(asset_id: str) -> list` - Previous scans

---

### 3.2 Identity Agent

**Purpose**: User identity and relationship verification

**Implementation**:
```python
def identity_agent(state: AgentState) -> AgentState:
    """Fetch user profile and consent graph."""
    # O(1) Spanner graph query for relationships
    return state
```

**Tools**:
- `get_user_profile(user_id: str) -> User` - Spanner query
- `check_relationship(user1: str, user2: str) -> str` - Graph traversal
- `calculate_trust_score(user_id: str) -> float` - Trust calculation

---

### 3.3 Policy Agent

**Purpose**: Consent and policy enforcement

**Implementation**:
```python
def policy_agent(state: AgentState) -> AgentState:
    """Determine policy decision and resolved_scope."""
    # O(1) consent lookup via Spanner Graph
    # Check region-specific policies
    state["policy_decision"] = "allow"
    state["resolved_scope"] = "public"
    state["requires_human_approval"] = False
    return state
```

**Tools**:
- `evaluate_consent(scan_data: dict) -> str` - Graph query
- `check_regional_compliance(region: str) -> bool`
- `explain_policy_decision(decision: dict) -> str`

---

### 3.4 Compliance Agent

**Purpose**: ESG verification, audit logging, blockchain anchoring

**Implementation**:
```python
async def compliance_agent(
    state: AgentState,
    http_client: Optional[httpx.AsyncClient] = None
) -> AgentState:
    """Fetch facets, verify ESG, anchor, audit."""

    # Check if escalation required
    if state.get("requires_human_approval"):
        # Register escalation via compliance service
        await register_escalation(state, http_client)
        return state

    # Fetch facets (safe previews only)
    state["facets"] = await fetch_safe_facets(state, http_client)

    # Log compliance event
    await log_audit_event(state, http_client)

    return state
```

**Tools**:
- `verify_esg(material_id: str, tx_type: str) -> ESGResult` - Cardano oracle
- `verify_burn_proof(proof_hash: str, parent_id: str) -> bool` - Midnight
- `log_audit_event(scan_data: dict)` - Hash-chained audit

---

## 4. Graph Queries (Spanner)

### 4.1 O(1) Consent Check

```sql
GRAPH IntegritySpineGraph
MATCH (viewer:Users)-[:FRIENDS_WITH*0..1]-(owner:Users)-[:OWNS]->(asset:Assets)
WHERE asset.asset_id = @asset_id
  AND NOT EXISTS {
    MATCH (owner)-[:HAS_CONSENT]->(consent:ConsentPolicies)
    WHERE consent.is_revoked = true
  }
RETURN owner.user_id, viewer.user_id;
```

### 4.2 Trust Path Query

```sql
GRAPH IntegritySpineGraph
MATCH path = (user1:Users)-[:FRIENDS_WITH*1..3]-(user2:Users)
WHERE user1.user_id = @user1_id AND user2.user_id = @user2_id
RETURN path
ORDER BY LENGTH(path)
LIMIT 1;
```

### 4.3 Material Lineage Query

```sql
GRAPH IntegritySpineGraph
MATCH (child:Assets)-[:DERIVED_FROM]->(parent:Assets)
WHERE child.asset_id = @asset_id
RETURN parent.asset_id, child.burn_proof_tx_hash;
```

### 4.4 Asset Composition Query

```sql
GRAPH IntegritySpineGraph
MATCH (asset:Assets)-[:COMPOSED_OF]->(material:Materials)
WHERE asset.asset_id = @asset_id
RETURN material.material_id, material.esg_score, asset.weight_pct;
```

---

## 5. ESG & Burn Proof Verification

### 5.1 ESG Verifier

```python
class ESGVerifier:
    """Verify ESG scores from Cardano oracle."""

    THRESHOLDS = {
        "rental": 0.5,
        "resale": 0.6,
        "dissolve": 0.4,
        "reprint": 0.7
    }

    async def verify_transaction(
        self,
        asset_id: str,
        material_id: str,
        transaction_type: str,
        agent_id: Optional[str] = None
    ) -> ESGVerificationResult:
        """
        Verify ESG score for a transaction.

        Production mode: Requires Cardano oracle response
        Development mode: Falls back to stub if configured
        """
        threshold = self.THRESHOLDS.get(transaction_type, 0.5)
        esg_score = await self.get_material_esg(material_id)

        if esg_score is None:
            return ESGVerificationResult(
                is_approved=False,
                requires_human_review=True,
                reason="Could not retrieve ESG score"
            )

        return ESGVerificationResult(
            is_approved=esg_score.overall_score >= threshold,
            esg_score=esg_score,
            cardano_verified=esg_score.cardano_tx_hash is not None
        )
```

### 5.2 Burn Proof Verifier

```python
class BurnProofVerifier:
    """Verify Midnight burn proofs for circular economy."""

    async def verify_detailed(
        self,
        burn_proof_hash: str,
        parent_asset_id: str
    ) -> BurnProofVerificationResult:
        """
        Verify burn proof for DISSOLVE→REPRINT transition.

        Production mode: Requires Midnight confirmation
        Development mode: Falls back to stub if configured
        """
        # Query Midnight API
        response = await self._client.post(
            f"{self.midnight_api_url}/v1/verify-burn-proof",
            json={"proof_hash": burn_proof_hash, "asset_id": parent_asset_id}
        )

        if response.status_code == 200:
            data = response.json()
            return BurnProofVerificationResult(
                is_valid=data.get("valid", False),
                midnight_confirmed=True,
                material_recovery_pct=data.get("material_recovery_pct")
            )

        # Check Spanner cache if Midnight unavailable
        return await self._check_cached_verification(burn_proof_hash)
```

---

## 6. Human-in-the-Loop Integration

### 6.1 Escalation Triggers

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Policy escalate | `decision == "escalate"` | Queue for human review |
| Trust score | `trust_score < 0.3` | Require approval |
| High-value | `value_usd > 1000` | Require approval |
| Counterfeit | `authenticity_failed` | Block + alert |
| First-time user | `scan_count == 0` | Soft escalate |
| ESG failed | `esg_score < threshold` | Require approval |

### 6.2 Governance Console Integration

```python
# When escalation is triggered
async def register_escalation(state: AgentState, http_client):
    """Register escalation with compliance service."""
    await http_client.post(
        f"{COMPLIANCE_URL}/audit/escalate",
        json={
            "scan_id": state.get("scan_id"),
            "region_code": state.get("region_code"),
            "reason": "policy_escalate",
            "requires_human_approval": True
        }
    )
```

### 6.3 Approval Workflow

```
1. Agent workflow triggers escalation
2. Compliance service creates escalation record
3. Governance Console displays pending approvals
4. Human reviews agent reasoning + graph context
5. Human approves/denies with justification
6. Workflow resumes or terminates
7. Audit log records decision
```

---

## 7. Agent Performance Metrics

### 7.1 Operational Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| Scan latency | <200ms | End-to-end scan processing |
| ESG verification | <500ms | Cardano oracle round-trip |
| Burn proof verification | <1s | Midnight verification |
| Consent lookup | <50ms | Spanner graph query |
| Escalation rate | <5% | Human intervention needed |

### 7.2 Business Metrics

| Metric | Description |
|--------|-------------|
| Agent transactions/day | MCP tool invocations |
| ESG approval rate | % passing ESG threshold |
| Human approval rate | % escalations approved |
| Counterfeit detection | Blocked scans |

---

## 8. Technology Stack

### Core Technologies

| Component | Technology |
|-----------|------------|
| **Graph Database** | Google Cloud Spanner (Native Property Graph) |
| **Real-time State** | Firestore |
| **Agent Framework** | LangGraph + LangChain |
| **LLM Provider** | Anthropic Claude |
| **External Access** | Model Context Protocol (MCP) |
| **ESG Oracle** | Cardano |
| **Burn Proofs** | Midnight (ZK) |

### Agent Tools

| Tool Type | Implementation |
|-----------|----------------|
| Graph queries | Spanner GQL via `google-cloud-spanner` |
| ESG verification | `ESGVerifier` class |
| Burn proof verification | `BurnProofVerifier` class |
| Audit logging | Hash-chained `AuditLog` table |

---

## 9. Security Guarantees

1. **NEVER expose facet bodies, pricing history, or ownership lineage** in agent messages
2. **If policy_decision == "escalate" or requires_human_approval == True**:
   - STOP automation
   - Queue `/audit/escalate` via compliance
   - DO NOT anchor to chain
   - Wait for governance_console human approval
3. **All agent transactions require ESG verification** for ethical oversight
4. **Production mode** fails closed when oracles unavailable
5. **Audit trail** is hash-chained and tamper-evident

---

**Document Version**: 9.0.0
**Last Updated**: January 2026
**Maintained By**: Brand.Me Engineering
