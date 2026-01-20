"""
Personal Branding Agent Module.

This module provides a GraphRAG-powered personal branding recommendation system
using Neo4j for knowledge graph storage and LangGraph for state management.

Key Components:
- database.py: Async Neo4j driver with circuit breaker and RBAC
- schemas.py: Pydantic v2 models with validation and PII scrubbing
- graph_engine.py: LangGraph state machine with Cypher 25 hybrid queries

Usage:
    from brandme_agents.branding import get_branding_engine, GoalType

    engine = await get_branding_engine()
    result = await engine.process_request(
        user_input="I want to become a thought leader in AI",
        user_id="user_123",
        goals=[GoalType.THOUGHT_LEADERSHIP],
        current_skills=["python", "machine_learning"],
    )

Copyright (c) Brand.Me, Inc. All rights reserved.
"""

from .database import (
    CircuitBreakerConfig,
    Neo4jConfig,
    Neo4jConnectionPool,
    close_neo4j_pool,
    get_neo4j_pool,
)
from .graph_engine import (
    BrandingAgentEngine,
    build_branding_graph,
    get_branding_engine,
)
from .schemas import (
    APPROVED_PRODUCT_REGISTRY,
    BrandingQueryInput,
    BrandingRecommendationOutput,
    BrandingRequest,
    BrandingResponse,
    BrandingState,
    ClosedBookProduct,
    DynamicUserEntity,
    GoalType,
    PIIScrubber,
    ProductCategory,
    ProductRecommendation,
    SkillLevel,
    UserProfileInput,
)

__all__ = [
    # Database
    "Neo4jConfig",
    "Neo4jConnectionPool",
    "CircuitBreakerConfig",
    "get_neo4j_pool",
    "close_neo4j_pool",
    # Schemas
    "APPROVED_PRODUCT_REGISTRY",
    "PIIScrubber",
    "GoalType",
    "ProductCategory",
    "SkillLevel",
    "UserProfileInput",
    "BrandingQueryInput",
    "ClosedBookProduct",
    "ProductRecommendation",
    "BrandingRecommendationOutput",
    "DynamicUserEntity",
    "BrandingState",
    "BrandingRequest",
    "BrandingResponse",
    # Engine
    "BrandingAgentEngine",
    "build_branding_graph",
    "get_branding_engine",
]
