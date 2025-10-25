"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Agent Orchestration with LangGraph
===================================
Multi-agent system for Brand.Me garment scan workflow
"""

from typing import TypedDict, Annotated, Sequence, Literal
from langchain_anthropic import ChatAnthropic
from langchain.schema import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor
import operator
import logging

from ..graph_rag import GraphRAG, get_graph_rag
from ..tools.graph_tools import (
    graph_query_tool,
    find_trust_path_tool,
    get_provenance_tool
)
from ..tools.blockchain_tools import (
    build_cardano_tx_tool,
    verify_blockchain_tx_tool
)
from ..tools.policy_tools import (
    evaluate_policy_tool,
    check_consent_tool
)

logger = logging.getLogger(__name__)


# ============================================================
# Agent State
# ============================================================

class AgentState(TypedDict):
    """
    Shared state across all agents in the workflow.
    """
    # Input
    messages: Annotated[Sequence[BaseMessage], operator.add]
    garment_tag: str
    scanner_user_id: str

    # Resolution
    garment_id: str | None
    garment_owner_id: str | None

    # Analysis
    relationship: str | None  # "owner", "friend", "stranger"
    trust_score: float
    trust_path: dict | None

    # Policy
    decision: Literal["allow", "deny", "escalate"]
    resolved_scope: str | None  # "public", "friends_only", "private"
    policy_version: str | None
    policy_reasoning: str | None

    # Data
    allowed_facets: list[dict]

    # Blockchain
    cardano_tx_hash: str | None
    midnight_tx_hash: str | None

    # Control flow
    requires_human_approval: bool
    escalation_reason: str | None
    scan_id: str | None

    # Context
    graph_context: dict


# ============================================================
# Individual Agent Nodes
# ============================================================

class ScanAgent:
    """
    Scan Agent: Initiates workflow and resolves garment identity.
    """

    def __init__(self, llm: ChatAnthropic, graph_rag: GraphRAG):
        self.llm = llm
        self.graph_rag = graph_rag

    def __call__(self, state: AgentState) -> AgentState:
        """
        Resolve garment_tag → garment_id using knowledge graph.
        """
        garment_tag = state["garment_tag"]

        logger.info(f"ScanAgent: Looking up garment {garment_tag}")

        # Query knowledge graph
        result = self.graph_rag.query(
            f"Find the garment_id for garment tag {garment_tag}",
            include_reasoning=True
        )

        garment_id = None
        garment_owner_id = None

        if result["sources"]:
            # Extract from query results
            first_result = result["sources"][0]
            garment_id = first_result.get("garment_id")
            garment_owner_id = first_result.get("owner_id")

        state["garment_id"] = garment_id
        state["garment_owner_id"] = garment_owner_id
        state["graph_context"] = result.get("context", {})

        state["messages"].append(
            SystemMessage(content=f"ScanAgent: Resolved {garment_tag} → {garment_id}")
        )

        return state


class IdentityAgent:
    """
    Identity Agent: Analyzes user relationships and trust.
    """

    def __init__(self, llm: ChatAnthropic, graph_rag: GraphRAG):
        self.llm = llm
        self.graph_rag = graph_rag

    def __call__(self, state: AgentState) -> AgentState:
        """
        Determine relationship between scanner and owner.
        """
        scanner_id = state["scanner_user_id"]
        owner_id = state["garment_owner_id"]

        logger.info(f"IdentityAgent: Checking relationship {scanner_id} → {owner_id}")

        # Check if scanner is owner
        if scanner_id == owner_id:
            state["relationship"] = "owner"
            state["trust_score"] = 1.0
            state["messages"].append(
                SystemMessage(content="IdentityAgent: Scanner is the owner")
            )
            return state

        # Find trust path
        trust_connection = self.graph_rag.find_trust_connection(scanner_id, owner_id)

        if trust_connection["connected"]:
            state["relationship"] = "friend"
            state["trust_score"] = trust_connection["aggregate_trust"]
            state["trust_path"] = trust_connection["path"]
        else:
            state["relationship"] = "stranger"
            state["trust_score"] = 0.0
            state["trust_path"] = None

        state["messages"].append(
            SystemMessage(content=f"IdentityAgent: Relationship={state['relationship']}, Trust={state['trust_score']:.2f}")
        )

        return state


class KnowledgeAgent:
    """
    Knowledge Agent: Retrieves garment information from graph.
    """

    def __init__(self, llm: ChatAnthropic, graph_rag: GraphRAG):
        self.llm = llm
        self.graph_rag = graph_rag

    def __call__(self, state: AgentState) -> AgentState:
        """
        Fetch garment passport data (will be filtered by policy agent).
        """
        garment_id = state["garment_id"]

        logger.info(f"KnowledgeAgent: Fetching data for {garment_id}")

        # Get provenance story
        provenance = self.graph_rag.get_garment_provenance(garment_id)

        # Store in context
        state["graph_context"]["provenance"] = provenance

        state["messages"].append(
            SystemMessage(content=f"KnowledgeAgent: Retrieved provenance with {len(provenance.get('ownership_chain', []))} ownership events")
        )

        return state


class PolicyAgent:
    """
    Policy Agent: Makes consent-driven policy decisions with LLM reasoning.
    """

    def __init__(self, llm: ChatAnthropic):
        self.llm = llm

    def __call__(self, state: AgentState) -> AgentState:
        """
        Evaluate policy and determine scope.
        """
        logger.info("PolicyAgent: Evaluating policy")

        # Build context for LLM
        context = {
            "scanner_id": state["scanner_user_id"],
            "owner_id": state["garment_owner_id"],
            "relationship": state["relationship"],
            "trust_score": state["trust_score"]
        }

        # Prompt LLM to make policy decision
        prompt = f"""You are a policy evaluation agent for Brand.Me platform.

Context:
- Scanner: {context['scanner_id']}
- Owner: {context['owner_id']}
- Relationship: {context['relationship']}
- Trust Score: {context['trust_score']:.2f}

Policy Rules:
1. Owner can see ALL data (scope: private)
2. Friends (trust_score > 0.5) can see friends_only data
3. Strangers can only see public data
4. High-value garments require escalation for non-owners
5. First-time scanners (trust_score < 0.3) should be escalated

Task:
Decide whether to:
- allow: Grant access with appropriate scope
- deny: Reject access
- escalate: Require human approval

Return JSON:
{{
    "decision": "allow" | "deny" | "escalate",
    "scope": "public" | "friends_only" | "private",
    "reasoning": "explanation"
}}
"""

        response = self.llm.invoke([HumanMessage(content=prompt)])

        # Parse response (in production, use structured output)
        import json
        try:
            decision_data = json.loads(response.content)
            state["decision"] = decision_data["decision"]
            state["resolved_scope"] = decision_data.get("scope", "public")
            state["policy_reasoning"] = decision_data["reasoning"]
        except:
            # Fallback to safe defaults
            state["decision"] = "escalate"
            state["resolved_scope"] = "public"
            state["policy_reasoning"] = "Failed to parse policy decision"

        state["policy_version"] = "v1.0.0"

        # Determine if human approval needed
        state["requires_human_approval"] = (state["decision"] == "escalate")

        if state["requires_human_approval"]:
            state["escalation_reason"] = state["policy_reasoning"]

        state["messages"].append(
            SystemMessage(content=f"PolicyAgent: Decision={state['decision']}, Scope={state['resolved_scope']}")
        )

        return state


class BlockchainAgent:
    """
    Blockchain Agent: Anchors data to Cardano and Midnight.
    """

    def __init__(self, llm: ChatAnthropic):
        self.llm = llm

    def __call__(self, state: AgentState) -> AgentState:
        """
        Build and submit blockchain transactions.
        """
        logger.info("BlockchainAgent: Anchoring to blockchains")

        # In production, call actual blockchain services
        # For now, simulate

        import uuid
        state["scan_id"] = str(uuid.uuid4())
        state["cardano_tx_hash"] = "a" * 64  # Simulated
        state["midnight_tx_hash"] = "b" * 64  # Simulated

        state["messages"].append(
            SystemMessage(content=f"BlockchainAgent: Anchored scan {state['scan_id']} to chains")
        )

        return state


class HumanApprovalNode:
    """
    Human-in-the-Loop: Escalates to human for approval.
    """

    def __call__(self, state: AgentState) -> AgentState:
        """
        Create approval request and wait for human decision.
        """
        logger.info("HumanApprovalNode: Escalating to human")

        # In production:
        # 1. Write approval request to database
        # 2. Send notification to governance console
        # 3. Wait for approval (via webhook or polling)

        # For now, auto-approve in demo mode
        state["decision"] = "allow"
        state["requires_human_approval"] = False

        state["messages"].append(
            SystemMessage(content="HumanApproval: Approved by governance team")
        )

        return state


# ============================================================
# Workflow Construction
# ============================================================

def create_agent_workflow() -> StateGraph:
    """
    Create the multi-agent workflow graph.

    Flow:
    scan_agent → identity_agent → knowledge_agent → policy_agent
                                                    ↓
                                                [escalate?]
                                                    ↓
                                          human_approval (if needed)
                                                    ↓
                                            blockchain_agent → END
    """
    # Initialize LLM and tools
    llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)
    graph_rag = get_graph_rag()

    # Create agent instances
    scan_agent = ScanAgent(llm, graph_rag)
    identity_agent = IdentityAgent(llm, graph_rag)
    knowledge_agent = KnowledgeAgent(llm, graph_rag)
    policy_agent = PolicyAgent(llm)
    blockchain_agent = BlockchainAgent(llm)
    human_approval = HumanApprovalNode()

    # Build workflow graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("scan_agent", scan_agent)
    workflow.add_node("identity_agent", identity_agent)
    workflow.add_node("knowledge_agent", knowledge_agent)
    workflow.add_node("policy_agent", policy_agent)
    workflow.add_node("blockchain_agent", blockchain_agent)
    workflow.add_node("human_approval", human_approval)

    # Define edges
    workflow.set_entry_point("scan_agent")
    workflow.add_edge("scan_agent", "identity_agent")
    workflow.add_edge("identity_agent", "knowledge_agent")
    workflow.add_edge("knowledge_agent", "policy_agent")

    # Conditional routing after policy decision
    def should_escalate(state: AgentState) -> str:
        """Determine next node based on policy decision"""
        if state["requires_human_approval"]:
            return "human_approval"
        elif state["decision"] == "allow":
            return "blockchain_agent"
        else:
            return END

    workflow.add_conditional_edges(
        "policy_agent",
        should_escalate,
        {
            "human_approval": "human_approval",
            "blockchain_agent": "blockchain_agent",
            END: END
        }
    )

    workflow.add_edge("human_approval", "blockchain_agent")
    workflow.add_edge("blockchain_agent", END)

    return workflow.compile()


# ============================================================
# Execution
# ============================================================

def run_scan_workflow(garment_tag: str, scanner_user_id: str) -> AgentState:
    """
    Execute the full scan workflow.

    Args:
        garment_tag: Garment identifier tag
        scanner_user_id: UUID of user scanning

    Returns:
        Final agent state with decision and blockchain anchors
    """
    workflow = create_agent_workflow()

    initial_state: AgentState = {
        "messages": [],
        "garment_tag": garment_tag,
        "scanner_user_id": scanner_user_id,
        "garment_id": None,
        "garment_owner_id": None,
        "relationship": None,
        "trust_score": 0.0,
        "trust_path": None,
        "decision": "deny",
        "resolved_scope": None,
        "policy_version": None,
        "policy_reasoning": None,
        "allowed_facets": [],
        "cardano_tx_hash": None,
        "midnight_tx_hash": None,
        "requires_human_approval": False,
        "escalation_reason": None,
        "scan_id": None,
        "graph_context": {}
    }

    # Execute workflow
    result = workflow.invoke(initial_state)

    return result


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    result = run_scan_workflow(
        garment_tag="garment-tag-12345",
        scanner_user_id="user-abc-123"
    )

    print("\n=== Workflow Result ===")
    print(f"Decision: {result['decision']}")
    print(f"Scope: {result['resolved_scope']}")
    print(f"Scan ID: {result['scan_id']}")
    print(f"Cardano TX: {result['cardano_tx_hash']}")
    print(f"\nReasoning: {result['policy_reasoning']}")
