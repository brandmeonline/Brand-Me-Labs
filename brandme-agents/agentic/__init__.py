"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Brand.Me Agentic System
=======================
AI-native agent framework with knowledge graphs and human-in-the-loop
"""

from .graph_db import BrandMeKnowledgeGraph, get_knowledge_graph
from .graph_rag import GraphRAG, get_graph_rag
from .orchestrator.agents import run_scan_workflow, create_agent_workflow

__version__ = "1.0.0"

__all__ = [
    "BrandMeKnowledgeGraph",
    "get_knowledge_graph",
    "GraphRAG",
    "get_graph_rag",
    "run_scan_workflow",
    "create_agent_workflow",
]
