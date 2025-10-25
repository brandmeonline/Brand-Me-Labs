"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Policy Tools
============
LangChain tools for policy evaluation and compliance
"""

from langchain.tools import tool
from typing import Dict, Any, Literal
import logging
import requests
import os

logger = logging.getLogger(__name__)

POLICY_SERVICE_URL = os.getenv("POLICY_SERVICE_URL", "http://localhost:8103")


@tool
def evaluate_policy_tool(scan_context: dict) -> dict:
    """
    Evaluate policy and consent rules for a scan.

    Use this to determine if access should be allowed and what scope to use.

    Args:
        scan_context: dict with scanner_user_id, garment_id, owner_id, relationship, region_code

    Returns:
        dict with decision ("allow"/"deny"/"escalate"), scope, and reasoning
    """
    try:
        response = requests.post(
            f"{POLICY_SERVICE_URL}/policy/evaluate",
            json=scan_context,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Policy evaluation failed: {e}")
        return {
            "decision": "deny",
            "scope": "public",
            "reasoning": f"Error: {e}"
        }


@tool
def check_consent_tool(user_id: str, garment_id: str, requester_id: str) -> dict:
    """
    Check user's consent settings for garment visibility.

    Use this to respect user privacy preferences.

    Args:
        user_id: Garment owner ID
        garment_id: Garment ID
        requester_id: User requesting access

    Returns:
        dict with allowed: bool, scope: str, reason: str
    """
    try:
        response = requests.post(
            f"{POLICY_SERVICE_URL}/consent/check",
            json={
                "user_id": user_id,
                "garment_id": garment_id,
                "requester_id": requester_id
            },
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Consent check failed: {e}")
        return {
            "allowed": False,
            "scope": "public",
            "reason": f"Error: {e}"
        }


@tool
def check_regional_compliance_tool(region_code: str, action: str, data_types: list[str]) -> dict:
    """
    Check if action complies with regional regulations (GDPR, CCPA, etc.).

    Use this before any data processing or sharing.

    Args:
        region_code: ISO region code (e.g., "us-east1", "eu-west1")
        action: Type of action ("scan", "share", "export", "reveal")
        data_types: Types of data involved (e.g., ["pii", "financial", "biometric"])

    Returns:
        dict with compliant: bool, restrictions: list, explanation: str
    """
    try:
        response = requests.post(
            f"{POLICY_SERVICE_URL}/compliance/check",
            json={
                "region_code": region_code,
                "action": action,
                "data_types": data_types
            },
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Regional compliance check failed: {e}")
        return {
            "compliant": False,
            "restrictions": ["Unknown error"],
            "explanation": str(e)
        }


@tool
def explain_policy_decision_tool(decision_context: dict) -> str:
    """
    Get human-readable explanation of a policy decision.

    Use this to provide transparency about why access was allowed/denied.

    Args:
        decision_context: dict with decision, scope, rules applied, user context

    Returns:
        Natural language explanation
    """
    try:
        response = requests.post(
            f"{POLICY_SERVICE_URL}/policy/explain",
            json=decision_context,
            timeout=5
        )
        response.raise_for_status()
        return response.json().get("explanation", "")
    except Exception as e:
        logger.error(f"Policy explanation failed: {e}")
        return f"Unable to generate explanation: {e}"


@tool
def get_applicable_policies_tool(context: dict) -> list:
    """
    Get all policies that apply to a given context.

    Use this to understand what rules are in effect.

    Args:
        context: dict with region_code, user_type, action_type, garment_type

    Returns:
        List of applicable policy rules
    """
    try:
        response = requests.post(
            f"{POLICY_SERVICE_URL}/policy/applicable",
            json=context,
            timeout=5
        )
        response.raise_for_status()
        return response.json().get("policies", [])
    except Exception as e:
        logger.error(f"Policy query failed: {e}")
        return []


@tool
def escalate_for_human_review_tool(scan_id: str, reason: str, context: dict) -> dict:
    """
    Escalate a scan for human review.

    Use this when policy decision is unclear or high-risk.

    Args:
        scan_id: Scan identifier
        reason: Why escalation is needed
        context: Full context for human reviewer

    Returns:
        dict with escalation_id, status, and estimated review time
    """
    try:
        response = requests.post(
            f"{POLICY_SERVICE_URL}/escalate",
            json={
                "scan_id": scan_id,
                "reason": reason,
                "context": context
            },
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Escalation failed: {e}")
        return {
            "escalation_id": None,
            "status": "failed",
            "error": str(e)
        }


# Export all tools
POLICY_TOOLS = [
    evaluate_policy_tool,
    check_consent_tool,
    check_regional_compliance_tool,
    explain_policy_decision_tool,
    get_applicable_policies_tool,
    escalate_for_human_review_tool
]
