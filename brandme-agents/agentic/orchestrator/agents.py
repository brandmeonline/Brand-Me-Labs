# Brand.Me v9 — Agentic & Circular Economy
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-agents/agentic/orchestrator/agents.py

import os
from typing import TypedDict, Optional, Any, Callable
import httpx

from brandme_core.logging import get_logger, redact_user_id, truncate_id
from brandme_core.env import get_service_url

logger = get_logger("agentic_orchestrator")

# Service URLs
BRAIN_URL = os.getenv("BRAIN_URL", "http://brain:8000")
POLICY_URL = os.getenv("POLICY_URL", "http://policy:8001")
COMPLIANCE_URL = os.getenv("COMPLIANCE_URL", "http://compliance:8004")
KNOWLEDGE_URL = os.getenv("KNOWLEDGE_URL", "http://knowledge:8003")


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


def scan_agent(state: AgentState) -> AgentState:
    """
    ScanAgent: resolve garment_tag -> garment_id.
    """
    logger.debug({
        "event": "scan_agent_started",
        "request_id": state.get("request_id"),
        "scan_id": state.get("scan_id"),
        "scanner_user": redact_user_id(state.get("scanner_user_id", "")),
        "garment_partial": truncate_id(state.get("garment_id", "")),
        "policy_decision": state.get("policy_decision"),
        "requires_human_approval": state.get("requires_human_approval", False),
    })

    state["garment_id"] = "GRMT_" + str(state.get("garment_tag", "unknown"))[:8]

    logger.debug({
        "event": "scan_agent_completed",
        "request_id": state.get("request_id"),
        "garment_partial": truncate_id(state.get("garment_id", "")),
    })

    return state


def identity_agent(state: AgentState) -> AgentState:
    """
    IdentityAgent: fetch user profile and consent graph.
    """
    logger.debug({
        "event": "identity_agent_started",
        "request_id": state.get("request_id"),
        "scanner_user": redact_user_id(state.get("scanner_user_id", "")),
        "garment_partial": truncate_id(state.get("garment_id", "")),
        "policy_decision": state.get("policy_decision"),
        "requires_human_approval": state.get("requires_human_approval", False),
    })

    logger.debug({
        "event": "identity_agent_completed",
        "request_id": state.get("request_id"),
    })

    return state


def policy_agent(state: AgentState) -> AgentState:
    """
    PolicyAgent: determine policy decision and resolved_scope.

    TODO: NEVER expose facet bodies, pricing history, or ownership lineage in agent messages.
    TODO: If policy_decision == "escalate" OR requires_human_approval == True:
    - STOP automation,
    - queue /audit/escalate via compliance,
    - DO NOT anchor to chain,
    - wait for governance_console human approval.
    """
    logger.debug({
        "event": "policy_agent_started",
        "request_id": state.get("request_id"),
        "scanner_user": redact_user_id(state.get("scanner_user_id", "")),
        "garment_partial": truncate_id(state.get("garment_id", "")),
        "region_code": state.get("region_code"),
        "policy_decision": state.get("policy_decision"),
        "requires_human_approval": state.get("requires_human_approval", False),
    })

    state["policy_decision"] = "allow"
    state["resolved_scope"] = "public"
    state["policy_version"] = "policy_v1_us-east1"
    state["requires_human_approval"] = False

    logger.debug({
        "event": "policy_agent_completed",
        "request_id": state.get("request_id"),
        "policy_decision": state.get("policy_decision"),
        "requires_human_approval": state.get("requires_human_approval"),
    })

    if state.get("requires_human_approval"):
        logger.info({
            "event": "policy_agent_escalation_required",
            "request_id": state.get("request_id"),
            "scan_id": state.get("scan_id"),
            "policy_decision": state.get("policy_decision"),
        })
        return state

    return state


async def compliance_agent(state: AgentState, http_client: Optional[httpx.AsyncClient] = None) -> AgentState:
    """
    ComplianceAgent: fetch facets, anchor, audit.

    SECURITY: NEVER log or return facet bodies, pricing history, or ownership lineage.
    If policy_decision == "escalate" or requires_human_approval == True:
    - DO NOT call orchestrator anchoring automatically.
    - Human must approve in governance_console.
    """
    logger.debug({
        "event": "compliance_agent_started",
        "request_id": state.get("request_id"),
        "scan_id": state.get("scan_id"),
        "scanner_user": redact_user_id(state.get("scanner_user_id", "")),
        "garment_partial": truncate_id(state.get("garment_id", "")),
        "policy_decision": state.get("policy_decision"),
        "requires_human_approval": state.get("requires_human_approval", False),
    })

    # Check if escalation required - don't proceed with blockchain anchoring
    if state.get("requires_human_approval") or state.get("policy_decision") == "escalate":
        logger.info({
            "event": "compliance_agent_escalation_halt",
            "request_id": state.get("request_id"),
            "reason": "Human approval required before blockchain anchoring"
        })

        # Register escalation with compliance service
        if http_client:
            try:
                response = await http_client.post(
                    f"{COMPLIANCE_URL}/audit/escalate",
                    json={
                        "scan_id": state.get("scan_id"),
                        "region_code": state.get("region_code"),
                        "reason": "policy_escalate",
                        "requires_human_approval": True
                    },
                    headers={"X-Request-Id": state.get("request_id", "")},
                    timeout=10.0
                )
                if response.status_code == 200:
                    escalation_data = response.json()
                    state["escalation_id"] = escalation_data.get("escalation_id")
            except Exception as e:
                logger.error({
                    "event": "compliance_escalation_failed",
                    "error": str(e)
                })

        return state

    # Fetch facets from knowledge service (only public previews, no sensitive data)
    if http_client:
        try:
            response = await http_client.get(
                f"{KNOWLEDGE_URL}/garment/{state.get('garment_id')}/passport",
                params={"scope": state.get("resolved_scope", "public")},
                headers={"X-Request-Id": state.get("request_id", "")},
                timeout=10.0
            )
            if response.status_code == 200:
                facet_data = response.json()
                # Only store safe preview data, never full facet bodies
                state["facets"] = [
                    {
                        "facet_type": f.get("facet_type"),
                        "facet_payload_preview": {"summary": f.get("summary", "available")}
                    }
                    for f in facet_data.get("facets", [])
                ]
        except Exception as e:
            logger.error({
                "event": "facet_fetch_failed",
                "error": str(e)
            })
            state["facets"] = []

    # Log compliance event (blockchain anchoring is done by orchestrator service)
    if http_client:
        try:
            await http_client.post(
                f"{COMPLIANCE_URL}/audit/log",
                json={
                    "scan_id": state.get("scan_id"),
                    "action": "scan_processed",
                    "decision_summary": state.get("policy_decision"),
                    "risk_flagged": False,
                    "escalated_to_human": False
                },
                headers={"X-Request-Id": state.get("request_id", "")},
                timeout=10.0
            )
        except Exception as e:
            logger.warning({
                "event": "compliance_log_failed",
                "error": str(e)
            })

    logger.debug({
        "event": "compliance_agent_completed",
        "request_id": state.get("request_id"),
        "scan_id": state.get("scan_id"),
        "facet_count": len(state.get("facets", []))
    })

    return state


def should_escalate(state: AgentState) -> str:
    """
    Conditional routing: determine if escalation is required.

    Returns:
        "escalate" if human approval needed, "continue" otherwise
    """
    if state.get("requires_human_approval") or state.get("policy_decision") == "escalate":
        return "escalate"
    return "continue"


async def run_agent_workflow(
    initial_state: AgentState,
    http_client: Optional[httpx.AsyncClient] = None
) -> AgentState:
    """
    Execute the agent workflow with proper escalation handling.

    This is a sequential workflow that:
    1. Resolves garment tag to ID
    2. Fetches identity/consent info
    3. Checks policy
    4. If policy allows, proceeds to compliance
    5. If policy escalates, halts for human approval

    Args:
        initial_state: Initial agent state with scan details
        http_client: Optional HTTP client for service calls

    Returns:
        Final agent state with results
    """
    state = initial_state.copy()

    try:
        # Step 1: Scan Agent
        state = scan_agent(state)

        # Step 2: Identity Agent
        state = identity_agent(state)

        # Step 3: Policy Agent
        state = policy_agent(state)

        # Step 4: Check if escalation required
        routing = should_escalate(state)

        if routing == "escalate":
            logger.info({
                "event": "workflow_escalated",
                "request_id": state.get("request_id"),
                "policy_decision": state.get("policy_decision")
            })
            # Still call compliance to register escalation
            state = await compliance_agent(state, http_client)
            return state

        # Step 5: Compliance Agent (only if not escalated)
        state = await compliance_agent(state, http_client)

        logger.info({
            "event": "workflow_completed",
            "request_id": state.get("request_id"),
            "policy_decision": state.get("policy_decision"),
            "facet_count": len(state.get("facets", []))
        })

    except Exception as e:
        logger.error({
            "event": "workflow_error",
            "request_id": state.get("request_id"),
            "error": str(e)
        })
        state["error"] = str(e)

    return state


def build_agent_graph():
    """
    Build LangGraph-compatible agent graph for autonomous scan flow.

    Note: This returns a workflow configuration that can be used with
    LangGraph's StateGraph. For direct execution, use run_agent_workflow().
    """
    # Return workflow configuration
    return {
        "nodes": {
            "scan": scan_agent,
            "identity": identity_agent,
            "policy": policy_agent,
            "compliance": compliance_agent
        },
        "edges": [
            ("scan", "identity"),
            ("identity", "policy"),
            ("policy", "compliance", should_escalate)
        ],
        "entry": "scan",
        "finish": "compliance"
    }
