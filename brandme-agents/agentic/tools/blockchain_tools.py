"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Blockchain Tools
================
LangChain tools for blockchain operations
"""

from langchain.tools import tool
from typing import Dict, Any, Literal
import logging
import requests
import os

logger = logging.getLogger(__name__)

CHAIN_SERVICE_URL = os.getenv("CHAIN_SERVICE_URL", "http://localhost:3001")


@tool
def build_cardano_tx_tool(scan_data: dict) -> str:
    """
    Build and submit Cardano transaction for garment scan.

    Use this to anchor public provenance data (creator, authenticity, ESG) to Cardano blockchain.

    Args:
        scan_data: dict with scan_id, garment_id, scope, facets

    Returns:
        Transaction hash (64 character hex string)
    """
    try:
        response = requests.post(
            f"{CHAIN_SERVICE_URL}/tx/cardano",
            json=scan_data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result.get("tx_hash", "")
    except Exception as e:
        logger.error(f"Cardano tx build failed: {e}")
        return f"Error: {e}"


@tool
def build_midnight_tx_tool(scan_data: dict) -> str:
    """
    Build and submit Midnight transaction for private data.

    Use this to anchor private ownership and pricing data to Midnight blockchain.

    Args:
        scan_data: dict with scan_id, garment_id, ownership, pricing, consent

    Returns:
        Transaction hash (64 character hex string)
    """
    try:
        response = requests.post(
            f"{CHAIN_SERVICE_URL}/tx/midnight",
            json=scan_data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result.get("tx_hash", "")
    except Exception as e:
        logger.error(f"Midnight tx build failed: {e}")
        return f"Error: {e}"


@tool
def verify_blockchain_tx_tool(tx_hash: str, chain: Literal["cardano", "midnight"]) -> bool:
    """
    Verify that a blockchain transaction is confirmed.

    Use this to check if a previous scan was properly anchored.

    Args:
        tx_hash: Transaction hash to verify
        chain: Which blockchain ("cardano" or "midnight")

    Returns:
        True if transaction is confirmed, False otherwise
    """
    try:
        response = requests.post(
            f"{CHAIN_SERVICE_URL}/tx/verify",
            json={"tx_hash": tx_hash, "chain": chain},
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        return result.get("is_valid", False)
    except Exception as e:
        logger.error(f"TX verification failed: {e}")
        return False


@tool
def compute_cross_chain_root_tool(cardano_tx: str, midnight_tx: str, scan_id: str) -> str:
    """
    Compute cross-chain root hash linking both blockchains.

    Use this to create cryptographic proof of dual-chain anchoring.

    Args:
        cardano_tx: Cardano transaction hash
        midnight_tx: Midnight transaction hash
        scan_id: Scan identifier

    Returns:
        SHA256 root hash (64 character hex string)
    """
    try:
        response = requests.post(
            f"{CHAIN_SERVICE_URL}/tx/compute-root",
            json={
                "cardano_tx": cardano_tx,
                "midnight_tx": midnight_tx,
                "scan_id": scan_id
            },
            timeout=5
        )
        response.raise_for_status()
        result = response.json()
        return result.get("root_hash", "")
    except Exception as e:
        logger.error(f"Root hash computation failed: {e}")
        return f"Error: {e}"


@tool
def get_blockchain_history_tool(garment_id: str) -> list:
    """
    Get all blockchain transactions for a garment.

    Use this to see complete on-chain history.

    Args:
        garment_id: Garment UUID

    Returns:
        List of transactions with timestamps and hashes
    """
    try:
        response = requests.get(
            f"{CHAIN_SERVICE_URL}/tx/history/{garment_id}",
            timeout=10
        )
        response.raise_for_status()
        return response.json().get("transactions", [])
    except Exception as e:
        logger.error(f"Blockchain history query failed: {e}")
        return []


@tool
def request_controlled_reveal_tool(midnight_tx_hash: str, requester_id: str, approvers: list[str]) -> dict:
    """
    Request controlled reveal of private Midnight data.

    Requires dual approval from governance and compliance.

    Args:
        midnight_tx_hash: Transaction containing private data
        requester_id: User requesting reveal
        approvers: List of 2+ approver IDs

    Returns:
        dict with reveal_id and status
    """
    try:
        response = requests.post(
            f"{CHAIN_SERVICE_URL}/reveal/request",
            json={
                "tx_hash": midnight_tx_hash,
                "requester_id": requester_id,
                "approvers": approvers
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Controlled reveal request failed: {e}")
        return {"error": str(e)}


# Export all tools
BLOCKCHAIN_TOOLS = [
    build_cardano_tx_tool,
    build_midnight_tx_tool,
    verify_blockchain_tx_tool,
    compute_cross_chain_root_tool,
    get_blockchain_history_tool,
    request_controlled_reveal_tool
]
