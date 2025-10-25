"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Graph Tools
===========
LangChain tools for knowledge graph operations
"""

from langchain.tools import tool
from typing import Optional, List, Dict, Any
import logging

from ..graph_db import get_knowledge_graph
from ..graph_rag import get_graph_rag

logger = logging.getLogger(__name__)


@tool
def graph_query_tool(question: str) -> dict:
    """
    Answer questions using the knowledge graph with RAG.

    Use this for ANY question about garments, users, relationships, or provenance.

    Args:
        question: Natural language question
            Examples:
            - "Find the garment_id for garment tag garment-xyz"
            - "Who owns garment-123?"
            - "Show me the creator of this garment"

    Returns:
        dict with answer, context, and source data
    """
    try:
        graph_rag = get_graph_rag()
        result = graph_rag.query(question, include_reasoning=True)
        return result
    except Exception as e:
        logger.error(f"Graph query failed: {e}")
        return {"answer": f"Error: {e}", "sources": []}


@tool
def find_trust_path_tool(user_id1: str, user_id2: str) -> dict:
    """
    Find trust path between two users in social graph.

    Use this to determine relationship and trust level.

    Args:
        user_id1: First user ID
        user_id2: Second user ID

    Returns:
        dict with path, aggregate_trust, and connected status
    """
    try:
        graph = get_knowledge_graph()
        path = graph.find_trust_path(user_id1, user_id2)

        if not path:
            return {"connected": False, "aggregate_trust": 0.0}

        import numpy as np
        aggregate_trust = np.prod(path["trust_weights"]) if path.get("trust_weights") else 0.0

        return {
            "connected": True,
            "path": path,
            "aggregate_trust": aggregate_trust
        }
    except Exception as e:
        logger.error(f"Trust path query failed: {e}")
        return {"connected": False, "error": str(e)}
    finally:
        graph.close()


@tool
def get_provenance_tool(garment_id: str) -> dict:
    """
    Get full provenance chain from creator to current owner.

    Use this to understand garment history and ownership transfers.

    Args:
        garment_id: Garment UUID

    Returns:
        dict with ownership chain, creator info, and blockchain proofs
    """
    try:
        graph_rag = get_graph_rag()
        provenance = graph_rag.get_garment_provenance(garment_id)
        return provenance
    except Exception as e:
        logger.error(f"Provenance query failed: {e}")
        return {"error": str(e), "ownership_chain": []}


@tool
def find_similar_garments_tool(garment_id: str, limit: int = 10) -> list:
    """
    Find similar garments using vector similarity search.

    Use this for recommendations or detecting counterfeits.

    Args:
        garment_id: Source garment ID
        limit: Max number of results (default 10)

    Returns:
        List of similar garments with similarity scores
    """
    try:
        graph = get_knowledge_graph()
        similar = graph.find_similar_garments(garment_id, limit)
        return similar
    except Exception as e:
        logger.error(f"Similarity search failed: {e}")
        return []
    finally:
        graph.close()


@tool
def get_user_social_graph_tool(user_id: str, depth: int = 2) -> dict:
    """
    Get user's social network up to specified depth.

    Use this to understand user's trusted network.

    Args:
        user_id: User UUID
        depth: How many hops to traverse (1-3 recommended)

    Returns:
        Subgraph with nodes and relationships
    """
    try:
        graph = get_knowledge_graph()
        social_graph = graph.get_user_social_graph(user_id, depth)
        return social_graph
    except Exception as e:
        logger.error(f"Social graph query failed: {e}")
        return {}
    finally:
        graph.close()


@tool
def execute_custom_cypher_tool(cypher_query: str, params: Optional[Dict[str, Any]] = None) -> list:
    """
    Execute a custom Cypher query on the knowledge graph.

    CAUTION: Only use for advanced queries not covered by other tools.

    Args:
        cypher_query: Valid Cypher query
        params: Query parameters (optional)

    Returns:
        List of query results
    """
    try:
        graph = get_knowledge_graph()
        results = graph.execute_cypher(cypher_query, params or {})
        return results
    except Exception as e:
        logger.error(f"Custom Cypher query failed: {e}")
        return []
    finally:
        graph.close()


# Export all tools
GRAPH_TOOLS = [
    graph_query_tool,
    find_trust_path_tool,
    get_provenance_tool,
    find_similar_garments_tool,
    get_user_social_graph_tool,
    execute_custom_cypher_tool
]
