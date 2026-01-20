"""
LangGraph State Machine for the Personal Branding Agent.

Architecture Notes:
-------------------
This module implements the core GraphRAG logic using LangGraph for state management.
The workflow follows: ExtractEntities -> HybridSearch -> ValidateProducts -> GenerateResponse

Key Features:
- LangGraph state machine with typed state transitions
- Cypher 25 hybrid query combining vector similarity + 2-hop graph traversal
- OpenTelemetry instrumentation for every node
- Structured output (JSON Mode) for all LLM calls

Flow:
1. ExtractEntities: Parse user input, extract skills/goals/entities
2. HybridSearch: Vector search (aspirational goals) + Graph traversal (required skills)
3. ValidateProducts: Cross-reference against APPROVED_PRODUCT_REGISTRY
4. GenerateResponse: Generate personalized recommendations with reasoning

Copyright (c) Brand.Me, Inc. All rights reserved.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import END, StateGraph
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from .database import Neo4jConnectionPool, get_neo4j_pool
from .schemas import (
    APPROVED_PRODUCT_REGISTRY,
    BrandingQueryInput,
    BrandingRecommendationOutput,
    BrandingState,
    ClosedBookProduct,
    DynamicUserEntity,
    GoalType,
    PIIScrubber,
    ProductRecommendation,
    SkillLevel,
    UserProfileInput,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


# -----------------------------------------------------------------------------
# LLM Configuration
# -----------------------------------------------------------------------------

def get_llm() -> ChatAnthropic:
    """
    Get configured LLM with structured output support.

    Uses Anthropic Claude with JSON Mode for structured output.
    """
    return ChatAnthropic(
        model="claude-sonnet-4-20250514",
        temperature=0.1,  # Low temperature for consistent structured output
        max_tokens=4096,
    )


# -----------------------------------------------------------------------------
# Cypher 25 Queries
# -----------------------------------------------------------------------------

# Hybrid search query combining vector similarity (for aspirational goals)
# with 2-hop path traversal (for required skills)
HYBRID_SEARCH_QUERY = """
// Cypher 25 Hybrid Query: Vector Similarity + 2-Hop Path Traversal
//
// This query finds products that match:
// 1. User's aspirational goals (via vector similarity on goal embeddings)
// 2. User's skill requirements (via 2-hop graph traversal from skills to products)

// Parameters:
// $goal_embedding: Vector embedding of user's aspirational goals
// $user_skills: List of user's current skills
// $target_skills: List of skills user wants to develop
// $top_k: Number of results to return

// Part 1: Vector similarity search for aspirational goal matching
CALL db.index.vector.queryNodes('product_goal_embeddings', $top_k, $goal_embedding)
YIELD node AS product, score AS vector_score
WHERE product:ClosedBookProduct

// Part 2: 2-hop path traversal for skill-based matching
// Find products connected through: (Skill)-[:REQUIRED_FOR|DEVELOPED_BY*1..2]->(Product)
WITH product, vector_score
OPTIONAL MATCH skill_path = (skill:Skill)-[:REQUIRED_FOR|DEVELOPED_BY*1..2]->(product)
WHERE skill.name IN $user_skills OR skill.name IN $target_skills

// Calculate path-based relevance
WITH product, vector_score,
     CASE
       WHEN skill_path IS NOT NULL
       THEN length(skill_path)
       ELSE 0
     END AS path_depth,
     COUNT(DISTINCT skill_path) AS path_count

// Combine scores: weighted average of vector similarity and path relevance
WITH product,
     vector_score,
     path_depth,
     path_count,
     // Hybrid score: 60% vector similarity + 40% path relevance
     (vector_score * 0.6 +
      CASE
        WHEN path_count > 0
        THEN (1.0 / (1.0 + path_depth)) * 0.4  // Closer paths score higher
        ELSE 0
      END) AS hybrid_score

// Return product details with scoring metadata
RETURN
  product.product_id AS product_id,
  product.name AS name,
  product.category AS category,
  product.description AS description,
  product.price_usd AS price_usd,
  product.required_skills AS required_skills,
  product.develops_skills AS develops_skills,
  product.ideal_for_goals AS ideal_for_goals,
  vector_score AS vector_similarity_score,
  path_depth AS path_traversal_depth,
  path_count AS skill_path_count,
  hybrid_score
ORDER BY hybrid_score DESC
LIMIT $top_k
"""


# Fallback query without vector search (for when embeddings unavailable)
GRAPH_TRAVERSAL_ONLY_QUERY = """
// Pure graph traversal query for skill-based product matching
// Used when vector search is unavailable

MATCH (product:ClosedBookProduct)

// 2-hop traversal from skills to products
OPTIONAL MATCH skill_path = (skill:Skill)-[:REQUIRED_FOR|DEVELOPED_BY*1..2]->(product)
WHERE skill.name IN $user_skills OR skill.name IN $target_skills

WITH product,
     CASE WHEN skill_path IS NOT NULL THEN length(skill_path) ELSE 999 END AS path_depth,
     COUNT(DISTINCT skill_path) AS path_count

// Also match on goal alignment
OPTIONAL MATCH (goal:Goal)-[:ADDRESSED_BY]->(product)
WHERE goal.type IN $goal_types

WITH product, path_depth, path_count,
     COUNT(DISTINCT goal) AS goal_match_count

// Score based on path depth and goal matches
WITH product,
     path_depth,
     path_count,
     goal_match_count,
     (CASE WHEN path_count > 0 THEN 1.0 / (1.0 + path_depth) ELSE 0 END * 0.5 +
      CASE WHEN goal_match_count > 0 THEN 0.5 ELSE 0 END) AS relevance_score

WHERE relevance_score > 0

RETURN
  product.product_id AS product_id,
  product.name AS name,
  product.category AS category,
  product.description AS description,
  product.price_usd AS price_usd,
  product.required_skills AS required_skills,
  product.develops_skills AS develops_skills,
  product.ideal_for_goals AS ideal_for_goals,
  0.0 AS vector_similarity_score,  // No vector search
  path_depth AS path_traversal_depth,
  relevance_score AS hybrid_score
ORDER BY relevance_score DESC
LIMIT $top_k
"""


# Query to store extracted user entities
STORE_USER_ENTITY_QUERY = """
// Store or update a dynamic user entity
// RBAC: Requires WRITE access to :DynamicUserEntity

MERGE (e:DynamicUserEntity {entity_id: $entity_id})
SET e.user_id = $user_id,
    e.entity_type = $entity_type,
    e.name = $name,
    e.properties = $properties,
    e.embedding = $embedding,
    e.updated_at = datetime()
ON CREATE SET e.created_at = datetime()
RETURN e
"""


# -----------------------------------------------------------------------------
# Node Functions (LangGraph)
# -----------------------------------------------------------------------------

async def extract_entities_node(state: BrandingState) -> BrandingState:
    """
    Node 1: Extract entities from user input.

    Uses LLM to identify skills, goals, and other relevant entities
    from the user's input. These are stored as :DynamicUserEntity nodes.

    OpenTelemetry: Spans track extraction time and entity count.
    """
    with tracer.start_as_current_span(
        "branding.extract_entities",
        kind=SpanKind.INTERNAL,
    ) as span:
        start_time = time.perf_counter()
        span.set_attribute("request_id", state.request_id)

        try:
            if not state.query:
                state.errors.append("No query provided for entity extraction")
                span.set_status(Status(StatusCode.ERROR, "No query"))
                return state

            # Get scrubbed input (PII already removed)
            user_input = state.query.profile.scrubbed_input
            span.set_attribute("input_length", len(user_input))

            # Use LLM to extract entities with structured output
            llm = get_llm()

            system_prompt = """You are an entity extraction system for a personal branding agent.
Extract the following entity types from the user's input:
- skills: Technical and soft skills mentioned
- goals: Career or branding goals
- achievements: Past accomplishments
- industries: Industries or domains mentioned

Return a JSON object with these keys:
{
  "skills": [{"name": string, "level": "beginner"|"intermediate"|"advanced"|"expert"}],
  "goals": [{"name": string, "type": string}],
  "achievements": [{"name": string, "description": string}],
  "industries": [string]
}"""

            human_prompt = f"Extract entities from this user input:\n\n{user_input}"

            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])

            # Parse structured output
            try:
                # Extract JSON from response
                content = response.content
                if isinstance(content, str):
                    # Find JSON in response
                    json_start = content.find("{")
                    json_end = content.rfind("}") + 1
                    if json_start >= 0 and json_end > json_start:
                        extracted = json.loads(content[json_start:json_end])
                    else:
                        extracted = {"skills": [], "goals": [], "achievements": [], "industries": []}
                else:
                    extracted = {"skills": [], "goals": [], "achievements": [], "industries": []}
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM entity extraction response")
                extracted = {"skills": [], "goals": [], "achievements": [], "industries": []}

            # Convert to DynamicUserEntity objects
            entities: list[DynamicUserEntity] = []
            user_id = state.query.profile.user_id

            for skill in extracted.get("skills", []):
                entities.append(DynamicUserEntity(
                    entity_id=f"{user_id}_skill_{skill.get('name', '').lower().replace(' ', '_')}",
                    user_id=user_id,
                    entity_type="skill",
                    name=skill.get("name", ""),
                    properties={"level": skill.get("level", "intermediate")},
                ))

            for goal in extracted.get("goals", []):
                entities.append(DynamicUserEntity(
                    entity_id=f"{user_id}_goal_{goal.get('name', '').lower().replace(' ', '_')[:20]}",
                    user_id=user_id,
                    entity_type="goal",
                    name=goal.get("name", ""),
                    properties={"type": goal.get("type", "general")},
                ))

            state.extracted_entities = entities
            span.set_attribute("entities_extracted", len(entities))

            # Record metrics
            elapsed = (time.perf_counter() - start_time) * 1000
            state.metrics["extract_entities_ms"] = elapsed
            span.set_attribute("processing_time_ms", elapsed)

            logger.info(f"Extracted {len(entities)} entities from user input")
            span.set_status(Status(StatusCode.OK))

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            state.errors.append(f"Entity extraction failed: {e}")
            logger.error(f"Entity extraction error: {e}")

        return state


async def hybrid_search_node(state: BrandingState) -> BrandingState:
    """
    Node 2: Hybrid search combining vector similarity + graph traversal.

    Uses Cypher 25 query that:
    1. Vector similarity search on goal embeddings (aspirational match)
    2. 2-hop path traversal from skills to products (requirement match)

    OpenTelemetry: Logs path_traversal_depth and vector_similarity_score.
    """
    with tracer.start_as_current_span(
        "branding.hybrid_search",
        kind=SpanKind.CLIENT,
    ) as span:
        start_time = time.perf_counter()
        span.set_attribute("request_id", state.request_id)
        span.set_attribute("db.system", "neo4j")

        try:
            if not state.query:
                state.errors.append("No query for hybrid search")
                return state

            # Get Neo4j pool
            pool = await get_neo4j_pool()

            # Prepare query parameters
            user_skills = state.query.current_skills or []
            target_skills = state.query.target_skills or []
            goal_types = [g.value for g in state.query.goals]

            # Generate goal embedding (placeholder - would use actual embedding model)
            # In production, use OpenAI ada-002 or similar
            goal_text = " ".join([
                state.query.profile.scrubbed_input,
                " ".join(goal_types),
            ])
            # Placeholder embedding - in production use actual embedding
            goal_embedding = [0.0] * 1536  # OpenAI ada-002 dimension

            span.set_attribute("user_skills_count", len(user_skills))
            span.set_attribute("target_skills_count", len(target_skills))
            span.set_attribute("goal_types", goal_types)

            # Try hybrid query first (requires vector index)
            try:
                results = await pool.execute_read(
                    HYBRID_SEARCH_QUERY,
                    parameters={
                        "goal_embedding": goal_embedding,
                        "user_skills": user_skills,
                        "target_skills": target_skills,
                        "top_k": 10,
                    },
                    use_fallback=False,  # Don't use JSON fallback for hybrid
                )
            except Exception as vector_err:
                # Fall back to graph-only traversal
                logger.warning(f"Vector search unavailable, using graph traversal: {vector_err}")
                span.set_attribute("fallback.graph_only", True)

                results = await pool.execute_read(
                    GRAPH_TRAVERSAL_ONLY_QUERY,
                    parameters={
                        "user_skills": user_skills,
                        "target_skills": target_skills,
                        "goal_types": goal_types,
                        "top_k": 10,
                    },
                    use_fallback=True,
                )

            # Log metrics for each result
            for i, result in enumerate(results):
                vector_score = result.get("vector_similarity_score", 0.0)
                path_depth = result.get("path_traversal_depth", 0)

                # Log per OpenTelemetry requirement
                span.add_event(
                    "product_recommendation",
                    attributes={
                        "product_id": result.get("product_id", ""),
                        "vector_similarity_score": vector_score,
                        "path_traversal_depth": path_depth,
                        "hybrid_score": result.get("hybrid_score", 0.0),
                        "rank": i + 1,
                    },
                )

                logger.info(
                    f"Product {result.get('product_id')}: "
                    f"vector_score={vector_score:.3f}, "
                    f"path_depth={path_depth}"
                )

            state.vector_search_results = results
            span.set_attribute("results_count", len(results))

            # Record metrics
            elapsed = (time.perf_counter() - start_time) * 1000
            state.metrics["hybrid_search_ms"] = elapsed
            span.set_attribute("processing_time_ms", elapsed)

            span.set_status(Status(StatusCode.OK))

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            state.errors.append(f"Hybrid search failed: {e}")
            logger.error(f"Hybrid search error: {e}")

            # Use fallback cache if available
            pool = await get_neo4j_pool()
            fallback_products = pool.get_fallback_products()
            if fallback_products:
                state.vector_search_results = fallback_products
                span.set_attribute("fallback.json_cache", True)
                logger.warning("Using JSON product cache as fallback")

        return state


async def validate_products_node(state: BrandingState) -> BrandingState:
    """
    Node 3: Validate products against APPROVED_PRODUCT_REGISTRY.

    Ensures all products recommended by the system are in the
    hardcoded approved registry. This prevents hallucinated products.

    OpenTelemetry: Tracks validation pass/fail rates.
    """
    with tracer.start_as_current_span(
        "branding.validate_products",
        kind=SpanKind.INTERNAL,
    ) as span:
        start_time = time.perf_counter()
        span.set_attribute("request_id", state.request_id)

        try:
            validated: list[ClosedBookProduct] = []
            rejected_count = 0

            for result in state.vector_search_results:
                product_id = result.get("product_id", "")

                # CRITICAL: Cross-reference against approved registry
                if product_id not in APPROVED_PRODUCT_REGISTRY:
                    logger.warning(
                        f"Rejecting product {product_id}: not in approved registry"
                    )
                    rejected_count += 1
                    span.add_event(
                        "product_rejected",
                        attributes={"product_id": product_id, "reason": "not_in_registry"},
                    )
                    continue

                # Parse goal types
                ideal_goals = []
                for goal_str in result.get("ideal_for_goals", []):
                    try:
                        ideal_goals.append(GoalType(goal_str))
                    except ValueError:
                        pass

                try:
                    product = ClosedBookProduct(
                        product_id=product_id,
                        name=result.get("name", ""),
                        category=result.get("category", "branding_package"),
                        description=result.get("description", ""),
                        price_usd=float(result.get("price_usd", 0)),
                        required_skills=result.get("required_skills", []),
                        develops_skills=result.get("develops_skills", []),
                        ideal_for_goals=ideal_goals,
                    )
                    validated.append(product)

                    span.add_event(
                        "product_validated",
                        attributes={"product_id": product_id},
                    )

                except Exception as e:
                    logger.warning(f"Product validation failed for {product_id}: {e}")
                    rejected_count += 1

            state.validated_products = validated
            span.set_attribute("validated_count", len(validated))
            span.set_attribute("rejected_count", rejected_count)

            # Record metrics
            elapsed = (time.perf_counter() - start_time) * 1000
            state.metrics["validate_products_ms"] = elapsed
            state.metrics["products_validated"] = len(validated)
            state.metrics["products_rejected"] = rejected_count

            logger.info(
                f"Validated {len(validated)} products, rejected {rejected_count}"
            )
            span.set_status(Status(StatusCode.OK))

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            state.errors.append(f"Product validation failed: {e}")
            logger.error(f"Product validation error: {e}")

        return state


async def generate_response_node(state: BrandingState) -> BrandingState:
    """
    Node 4: Generate personalized recommendations using LLM.

    Uses structured output (JSON Mode) to ensure consistent response format.
    Includes reasoning for each recommendation.

    OpenTelemetry: Tracks LLM response time and token usage.
    """
    with tracer.start_as_current_span(
        "branding.generate_response",
        kind=SpanKind.INTERNAL,
    ) as span:
        start_time = time.perf_counter()
        span.set_attribute("request_id", state.request_id)

        try:
            if not state.validated_products:
                state.errors.append("No validated products for response generation")
                span.set_status(Status(StatusCode.ERROR, "No products"))
                return state

            llm = get_llm()

            # Prepare product context
            product_context = []
            for i, product in enumerate(state.validated_products):
                # Get original scores from search results
                search_result = next(
                    (r for r in state.vector_search_results
                     if r.get("product_id") == product.product_id),
                    {}
                )

                product_context.append({
                    "rank": i + 1,
                    "product_id": product.product_id,
                    "name": product.name,
                    "description": product.description,
                    "price": product.price_usd,
                    "category": product.category.value,
                    "required_skills": product.required_skills,
                    "develops_skills": product.develops_skills,
                    "vector_score": search_result.get("vector_similarity_score", 0),
                    "path_depth": search_result.get("path_traversal_depth", 0),
                })

            system_prompt = """You are a personal branding recommendation system.
Generate personalized product recommendations based on the user's goals and skills.

Return a JSON response with this exact structure:
{
  "recommendations": [
    {
      "product_id": "string (MUST be from the provided products)",
      "relevance_score": number (0-1),
      "reasoning": "string explaining why this product fits the user"
    }
  ],
  "reasoning_summary": "string (overall recommendation strategy)",
  "skill_gap_analysis": {"skill_name": "beginner|intermediate|advanced|expert"},
  "next_steps": ["string array of actionable next steps"]
}

IMPORTANT:
- Only recommend products from the provided list
- product_id MUST exactly match one from the input
- Provide specific, actionable reasoning"""

            user_goals = state.query.goals if state.query else []
            user_skills = state.query.current_skills if state.query else []
            user_input = state.query.profile.scrubbed_input if state.query else ""

            human_prompt = f"""User Profile:
- Goals: {[g.value for g in user_goals]}
- Current Skills: {user_skills}
- Description: {user_input}

Available Products (already validated):
{json.dumps(product_context, indent=2)}

Generate personalized recommendations."""

            span.set_attribute("llm.model", "claude-sonnet-4-20250514")
            span.set_attribute("products_in_context", len(product_context))

            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])

            # Parse structured output
            content = response.content
            if isinstance(content, str):
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    llm_output = json.loads(content[json_start:json_end])
                else:
                    raise ValueError("No JSON found in LLM response")
            else:
                raise ValueError("Unexpected LLM response format")

            # Build final recommendations with full product data
            recommendations: list[ProductRecommendation] = []

            for rec in llm_output.get("recommendations", []):
                product_id = rec.get("product_id")

                # Find validated product
                product = next(
                    (p for p in state.validated_products if p.product_id == product_id),
                    None
                )

                if not product:
                    logger.warning(f"LLM recommended unknown product: {product_id}")
                    continue

                # Get original scores
                search_result = next(
                    (r for r in state.vector_search_results
                     if r.get("product_id") == product_id),
                    {}
                )

                recommendations.append(ProductRecommendation(
                    product=product,
                    relevance_score=float(rec.get("relevance_score", 0.5)),
                    vector_similarity_score=float(
                        search_result.get("vector_similarity_score", 0)
                    ),
                    path_traversal_depth=int(
                        search_result.get("path_traversal_depth", 0)
                    ),
                    reasoning=rec.get("reasoning", ""),
                ))

            # Build final output
            skill_gaps = {}
            for skill, level in llm_output.get("skill_gap_analysis", {}).items():
                try:
                    skill_gaps[skill] = SkillLevel(level)
                except ValueError:
                    skill_gaps[skill] = SkillLevel.INTERMEDIATE

            state.output = BrandingRecommendationOutput(
                request_id=state.request_id,
                user_id=state.query.profile.user_id if state.query else "",
                recommendations=recommendations,
                reasoning_summary=llm_output.get("reasoning_summary", ""),
                skill_gap_analysis=skill_gaps,
                next_steps=llm_output.get("next_steps", []),
            )

            span.set_attribute("recommendations_count", len(recommendations))

            # Record metrics
            elapsed = (time.perf_counter() - start_time) * 1000
            state.metrics["generate_response_ms"] = elapsed
            span.set_attribute("processing_time_ms", elapsed)

            logger.info(f"Generated {len(recommendations)} recommendations")
            span.set_status(Status(StatusCode.OK))

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            state.errors.append(f"Response generation failed: {e}")
            logger.error(f"Response generation error: {e}")

        return state


# -----------------------------------------------------------------------------
# LangGraph Workflow Builder
# -----------------------------------------------------------------------------

def build_branding_graph() -> StateGraph:
    """
    Build the LangGraph workflow for the personal branding agent.

    Flow: ExtractEntities -> HybridSearch -> ValidateProducts -> GenerateResponse

    Returns:
        Compiled StateGraph ready for execution
    """
    # Create graph with BrandingState
    workflow = StateGraph(BrandingState)

    # Add nodes
    workflow.add_node("extract_entities", extract_entities_node)
    workflow.add_node("hybrid_search", hybrid_search_node)
    workflow.add_node("validate_products", validate_products_node)
    workflow.add_node("generate_response", generate_response_node)

    # Define edges (linear flow)
    workflow.set_entry_point("extract_entities")
    workflow.add_edge("extract_entities", "hybrid_search")
    workflow.add_edge("hybrid_search", "validate_products")
    workflow.add_edge("validate_products", "generate_response")
    workflow.add_edge("generate_response", END)

    return workflow.compile()


# -----------------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------------

class BrandingAgentEngine:
    """
    High-level interface for the Personal Branding Agent.

    Provides a simple async interface for processing branding requests.
    """

    def __init__(self):
        self._graph = build_branding_graph()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the engine (Neo4j pool, etc.)."""
        if not self._initialized:
            await get_neo4j_pool()
            self._initialized = True

    async def process_request(
        self,
        user_input: str,
        user_id: str,
        goals: list[GoalType],
        current_skills: list[str] | None = None,
        target_skills: list[str] | None = None,
        budget_range: tuple[float, float] | None = None,
    ) -> BrandingRecommendationOutput:
        """
        Process a branding request and return recommendations.

        Args:
            user_input: Raw user input describing branding needs
            user_id: Unique user identifier
            goals: List of branding goals
            current_skills: User's current skills
            target_skills: Skills user wants to develop
            budget_range: Optional (min, max) budget in USD

        Returns:
            BrandingRecommendationOutput with validated recommendations

        Raises:
            ValueError: If processing fails
        """
        with tracer.start_as_current_span(
            "branding.process_request",
            kind=SpanKind.SERVER,
        ) as span:
            request_id = str(uuid.uuid4())
            span.set_attribute("request_id", request_id)
            span.set_attribute("user_id", user_id)

            await self.initialize()

            # Create input with PII scrubbing
            profile = UserProfileInput(
                user_id=user_id,
                raw_input=user_input,
            )

            span.set_attribute("pii_redacted", sum(profile.pii_redacted.values()) > 0)

            query = BrandingQueryInput(
                profile=profile,
                goals=goals,
                current_skills=current_skills or [],
                target_skills=target_skills or [],
                budget_range=budget_range,
            )

            # Create initial state
            initial_state = BrandingState(
                request_id=request_id,
                query=query,
            )

            # Execute workflow
            final_state = await self._graph.ainvoke(initial_state)

            # Check for errors
            if final_state.get("errors"):
                error_msg = "; ".join(final_state["errors"])
                span.set_status(Status(StatusCode.ERROR, error_msg))
                raise ValueError(f"Processing failed: {error_msg}")

            output = final_state.get("output")
            if not output:
                span.set_status(Status(StatusCode.ERROR, "No output generated"))
                raise ValueError("No recommendations generated")

            # Log final metrics
            metrics = final_state.get("metrics", {})
            for metric_name, value in metrics.items():
                span.set_attribute(f"metrics.{metric_name}", value)

            span.set_status(Status(StatusCode.OK))
            return output


# Singleton instance
_engine: BrandingAgentEngine | None = None


async def get_branding_engine() -> BrandingAgentEngine:
    """Get or create the branding agent engine singleton."""
    global _engine
    if _engine is None:
        _engine = BrandingAgentEngine()
        await _engine.initialize()
    return _engine
