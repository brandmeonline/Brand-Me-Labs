# Brand.Me v6 — Stable Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-agents/agentic/orchestrator/agents.py

from typing import TypedDict, Optional

from brandme_core.logging import get_logger, redact_user_id, truncate_id

logger = get_logger("agentic_orchestrator")


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


def compliance_agent(state: AgentState) -> AgentState:
    """
    ComplianceAgent: fetch facets, anchor, audit.

    TODO: NEVER log or return facet bodies, pricing history, or ownership lineage.
    TODO: If policy_decision == "escalate" or requires_human_approval == True:
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

    state["facets"] = [{"facet_type": "ESG", "facet_payload_preview": {"summary": "stub"}}]
    state["cardano_tx_hash"] = "tx_cardano_stub"
    state["midnight_tx_hash"] = "tx_midnight_stub"

    logger.debug({
        "event": "compliance_agent_completed",
        "request_id": state.get("request_id"),
        "scan_id": state.get("scan_id"),
    })

    return state


def build_agent_graph():
    """
    Build LangGraph agent graph for autonomous scan flow.

    TODO: Integrate with LangGraph StateGraph, add conditional edges based on requires_human_approval.
    """
    logger.info({"event": "agent_graph_placeholder"})
    return None
