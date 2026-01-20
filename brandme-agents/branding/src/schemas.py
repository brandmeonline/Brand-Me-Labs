"""
Pydantic v2 Schemas for the Personal Branding Agent.

Architecture Notes:
-------------------
This module provides strict validation for all data flowing through the
branding agent, including:
- Closed-Book product validation against approved registry
- PII scrubbing middleware for input sanitization
- Structured output schemas for LLM responses

Security Features:
- All product recommendations cross-referenced against APPROVED_PRODUCT_REGISTRY
- PII (names, emails, phone numbers) stripped before LLM context injection
- Strict model validation with Pydantic v2

Copyright (c) Brand.Me, Inc. All rights reserved.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# -----------------------------------------------------------------------------
# Approved Product Registry (Closed-Book Constraint)
# -----------------------------------------------------------------------------

# Hardcoded registry of approved product IDs that the LLM can recommend.
# This ensures the agent ONLY suggests products from our verified catalog.
APPROVED_PRODUCT_REGISTRY: frozenset[str] = frozenset({
    # Branding Packages
    "PKG-PERSONAL-001",
    "PKG-PERSONAL-002",
    "PKG-PERSONAL-003",
    "PKG-EXECUTIVE-001",
    "PKG-EXECUTIVE-002",
    "PKG-CREATOR-001",
    "PKG-CREATOR-002",
    "PKG-CREATOR-003",
    # Individual Services
    "SVC-HEADSHOT-001",
    "SVC-HEADSHOT-002",
    "SVC-STYLING-001",
    "SVC-STYLING-002",
    "SVC-COACHING-001",
    "SVC-COACHING-002",
    "SVC-LINKEDIN-001",
    "SVC-PORTFOLIO-001",
    "SVC-BIO-001",
    # Digital Products
    "DIG-TEMPLATE-001",
    "DIG-TEMPLATE-002",
    "DIG-COURSE-001",
    "DIG-COURSE-002",
    "DIG-EBOOK-001",
    # Subscription Tiers
    "SUB-STARTER-001",
    "SUB-PRO-001",
    "SUB-ENTERPRISE-001",
})


# -----------------------------------------------------------------------------
# PII Scrubber
# -----------------------------------------------------------------------------

class PIIScrubber:
    """
    Middleware for scrubbing PII from user input before LLM processing.

    Removes:
    - Email addresses
    - Phone numbers (various formats)
    - Names (when following common patterns like "I'm [Name]" or "My name is [Name]")
    - Social Security Numbers (US format)
    - Credit card numbers

    This is a defense-in-depth measure. PII should also be filtered at
    the API gateway level.
    """

    # Email pattern
    EMAIL_PATTERN = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    )

    # Phone patterns (US and international)
    PHONE_PATTERNS = [
        re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'),  # US: 123-456-7890
        re.compile(r'\b\(\d{3}\)\s*\d{3}[-.\s]?\d{4}\b'),  # US: (123) 456-7890
        re.compile(r'\b\+\d{1,3}[-.\s]?\d{3,14}\b'),       # International
    ]

    # Name extraction patterns
    NAME_PATTERNS = [
        re.compile(r"\b(?:I'm|I am|my name is|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.IGNORECASE),
        re.compile(r"\b(?:this is|it's)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:here|speaking)", re.IGNORECASE),
    ]

    # SSN pattern (US)
    SSN_PATTERN = re.compile(r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b')

    # Credit card patterns (basic)
    CC_PATTERNS = [
        re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),  # 1234-5678-9012-3456
        re.compile(r'\b\d{16}\b'),                    # 16 consecutive digits
    ]

    # Replacement tokens
    REDACTED_EMAIL = "[EMAIL_REDACTED]"
    REDACTED_PHONE = "[PHONE_REDACTED]"
    REDACTED_NAME = "[NAME_REDACTED]"
    REDACTED_SSN = "[SSN_REDACTED]"
    REDACTED_CC = "[CC_REDACTED]"

    @classmethod
    def scrub(cls, text: str) -> tuple[str, dict[str, int]]:
        """
        Scrub PII from text.

        Args:
            text: Input text potentially containing PII

        Returns:
            Tuple of (scrubbed_text, redaction_counts)
        """
        redaction_counts: dict[str, int] = {
            "emails": 0,
            "phones": 0,
            "names": 0,
            "ssns": 0,
            "credit_cards": 0,
        }

        # Scrub emails
        text, count = cls.EMAIL_PATTERN.subn(cls.REDACTED_EMAIL, text)
        redaction_counts["emails"] = count

        # Scrub phone numbers
        for pattern in cls.PHONE_PATTERNS:
            text, count = pattern.subn(cls.REDACTED_PHONE, text)
            redaction_counts["phones"] += count

        # Scrub names (careful - this can be overly aggressive)
        for pattern in cls.NAME_PATTERNS:
            matches = pattern.findall(text)
            for match in matches:
                text = text.replace(match, cls.REDACTED_NAME)
                redaction_counts["names"] += 1

        # Scrub SSNs
        text, count = cls.SSN_PATTERN.subn(cls.REDACTED_SSN, text)
        redaction_counts["ssns"] = count

        # Scrub credit cards
        for pattern in cls.CC_PATTERNS:
            text, count = pattern.subn(cls.REDACTED_CC, text)
            redaction_counts["credit_cards"] += count

        return text, redaction_counts

    @classmethod
    def contains_pii(cls, text: str) -> bool:
        """Check if text contains any detectable PII."""
        if cls.EMAIL_PATTERN.search(text):
            return True
        for pattern in cls.PHONE_PATTERNS:
            if pattern.search(text):
                return True
        if cls.SSN_PATTERN.search(text):
            return True
        for pattern in cls.CC_PATTERNS:
            if pattern.search(text):
                return True
        return False


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------

class ProductCategory(str, Enum):
    """Product categories in the closed-book catalog."""
    BRANDING_PACKAGE = "branding_package"
    INDIVIDUAL_SERVICE = "individual_service"
    DIGITAL_PRODUCT = "digital_product"
    SUBSCRIPTION = "subscription"


class SkillLevel(str, Enum):
    """Skill proficiency levels."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class GoalType(str, Enum):
    """Types of branding goals."""
    CAREER_TRANSITION = "career_transition"
    THOUGHT_LEADERSHIP = "thought_leadership"
    ENTREPRENEURSHIP = "entrepreneurship"
    EXECUTIVE_PRESENCE = "executive_presence"
    CONTENT_CREATION = "content_creation"
    NETWORKING = "networking"


# -----------------------------------------------------------------------------
# Input Schemas
# -----------------------------------------------------------------------------

class UserProfileInput(BaseModel):
    """
    User profile input for branding agent.

    PII is automatically scrubbed before processing.
    """
    model_config = ConfigDict(
        strict=True,
        str_strip_whitespace=True,
    )

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique user identifier (not PII)",
    )

    raw_input: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="User's raw input describing their branding goals",
    )

    # Scrubbed version populated by validator
    scrubbed_input: str = Field(
        default="",
        description="PII-scrubbed version of raw_input",
    )

    pii_redacted: dict[str, int] = Field(
        default_factory=dict,
        description="Count of PII elements redacted",
    )

    industry: str | None = Field(
        default=None,
        max_length=100,
        description="User's industry or field",
    )

    years_experience: int | None = Field(
        default=None,
        ge=0,
        le=60,
        description="Years of professional experience",
    )

    @model_validator(mode="after")
    def scrub_pii(self) -> Self:
        """Scrub PII from raw input after validation."""
        if self.raw_input:
            self.scrubbed_input, self.pii_redacted = PIIScrubber.scrub(self.raw_input)

            # Log if PII was found
            total_redacted = sum(self.pii_redacted.values())
            if total_redacted > 0:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"PII scrubbed from user input: {self.pii_redacted}"
                )
        return self


class BrandingQueryInput(BaseModel):
    """Input for a branding query/search."""
    model_config = ConfigDict(strict=True)

    profile: UserProfileInput
    goals: list[GoalType] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="User's branding goals",
    )
    current_skills: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="User's current skills",
    )
    target_skills: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Skills user wants to develop",
    )
    budget_range: tuple[float, float] | None = Field(
        default=None,
        description="Budget range (min, max) in USD",
    )

    @field_validator("budget_range")
    @classmethod
    def validate_budget_range(cls, v: tuple[float, float] | None) -> tuple[float, float] | None:
        if v is not None:
            min_budget, max_budget = v
            if min_budget < 0 or max_budget < 0:
                raise ValueError("Budget values must be non-negative")
            if min_budget > max_budget:
                raise ValueError("Minimum budget cannot exceed maximum budget")
        return v


# -----------------------------------------------------------------------------
# Product Output Schemas (Closed-Book)
# -----------------------------------------------------------------------------

class ClosedBookProduct(BaseModel):
    """
    Strict Pydantic model for Closed-Book product output.

    All products MUST be validated against APPROVED_PRODUCT_REGISTRY.
    This ensures the LLM can only recommend verified products.
    """
    model_config = ConfigDict(
        strict=True,
        str_strip_whitespace=True,
        frozen=True,  # Immutable after creation
    )

    product_id: str = Field(
        ...,
        min_length=5,
        max_length=50,
        pattern=r'^[A-Z]{3}-[A-Z]+-\d{3}$',
        description="Product ID in format: CAT-NAME-###",
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Product display name",
    )

    category: ProductCategory = Field(
        ...,
        description="Product category",
    )

    description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Product description",
    )

    price_usd: float = Field(
        ...,
        ge=0,
        le=100000,
        description="Price in USD",
    )

    required_skills: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Skills required to benefit from this product",
    )

    develops_skills: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Skills this product helps develop",
    )

    ideal_for_goals: list[GoalType] = Field(
        default_factory=list,
        max_length=5,
        description="Goals this product is ideal for",
    )

    @field_validator("product_id")
    @classmethod
    def validate_product_in_registry(cls, v: str) -> str:
        """
        CRITICAL: Cross-reference product_id against approved registry.

        This prevents the LLM from hallucinating product IDs.
        """
        if v not in APPROVED_PRODUCT_REGISTRY:
            raise ValueError(
                f"Product ID '{v}' is not in APPROVED_PRODUCT_REGISTRY. "
                f"Only verified products can be recommended."
            )
        return v


class ProductRecommendation(BaseModel):
    """A single product recommendation with reasoning."""
    model_config = ConfigDict(strict=True)

    product: ClosedBookProduct
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How relevant this product is (0-1)",
    )
    vector_similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Vector similarity score for aspirational goal match",
    )
    path_traversal_depth: int = Field(
        ...,
        ge=0,
        le=10,
        description="Graph traversal depth for skill requirement match",
    )
    reasoning: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Explanation of why this product is recommended",
    )


class BrandingRecommendationOutput(BaseModel):
    """
    Complete branding recommendation output (Structured Output for LLM).

    This schema is used with JSON Mode to ensure the LLM returns
    properly structured recommendations.
    """
    model_config = ConfigDict(strict=True)

    request_id: str = Field(
        ...,
        description="Unique request identifier for tracing",
    )

    user_id: str = Field(
        ...,
        description="User identifier",
    )

    recommendations: list[ProductRecommendation] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Ordered list of product recommendations",
    )

    reasoning_summary: str = Field(
        ...,
        min_length=50,
        max_length=2000,
        description="Overall reasoning for the recommendations",
    )

    skill_gap_analysis: dict[str, SkillLevel] = Field(
        default_factory=dict,
        description="Analysis of skill gaps to address",
    )

    next_steps: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Suggested next steps for the user",
    )

    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of recommendation generation",
    )

    @model_validator(mode="after")
    def validate_all_products_approved(self) -> Self:
        """Ensure all recommended products are in the approved registry."""
        for rec in self.recommendations:
            if rec.product.product_id not in APPROVED_PRODUCT_REGISTRY:
                raise ValueError(
                    f"Recommendation contains unapproved product: {rec.product.product_id}"
                )
        return self


# -----------------------------------------------------------------------------
# Graph Entity Schemas
# -----------------------------------------------------------------------------

class DynamicUserEntity(BaseModel):
    """
    Schema for user entities stored in Neo4j.

    These are WRITABLE by the branding agent (RBAC: WRITE access).
    """
    model_config = ConfigDict(strict=True)

    entity_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
    )

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
    )

    entity_type: str = Field(
        ...,
        description="Type of entity (skill, goal, achievement, etc.)",
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional entity properties",
    )

    # Embedding for vector search
    embedding: list[float] | None = Field(
        default=None,
        description="Vector embedding for similarity search",
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
    )

    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
    )

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimension(cls, v: list[float] | None) -> list[float] | None:
        """Validate embedding has correct dimensions."""
        if v is not None:
            expected_dim = 1536  # OpenAI ada-002 dimension
            if len(v) != expected_dim:
                raise ValueError(
                    f"Embedding must have {expected_dim} dimensions, got {len(v)}"
                )
        return v


class ClosedBookProductEntity(BaseModel):
    """
    Schema for closed-book product entities in Neo4j.

    These are READ-ONLY for the branding agent (RBAC: READ_ONLY access).
    """
    model_config = ConfigDict(
        strict=True,
        frozen=True,  # Immutable - represents read-only data
    )

    product_id: str
    name: str
    category: ProductCategory
    description: str
    price_usd: float
    embedding: list[float] | None = None

    # Graph relationships
    requires_skills: list[str] = Field(default_factory=list)
    develops_skills: list[str] = Field(default_factory=list)
    ideal_for_goals: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# LangGraph State Schema
# -----------------------------------------------------------------------------

class BrandingState(BaseModel):
    """
    State model for LangGraph workflow.

    This is passed between nodes in the branding agent graph.
    """
    model_config = ConfigDict(strict=True)

    # Request metadata
    request_id: str = Field(
        ...,
        description="Unique request identifier",
    )

    # Input (after PII scrubbing)
    query: BrandingQueryInput | None = None

    # Extracted entities from user input
    extracted_entities: list[DynamicUserEntity] = Field(
        default_factory=list,
        description="Entities extracted from user input",
    )

    # Search results
    vector_search_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Results from vector similarity search",
    )

    graph_traversal_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Results from graph traversal",
    )

    # Validated products
    validated_products: list[ClosedBookProduct] = Field(
        default_factory=list,
        description="Products validated against registry",
    )

    # Final output
    output: BrandingRecommendationOutput | None = None

    # Error tracking
    errors: list[str] = Field(
        default_factory=list,
        description="Errors encountered during processing",
    )

    # Metrics for observability
    metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Performance metrics for each step",
    )


# -----------------------------------------------------------------------------
# API Request/Response Schemas
# -----------------------------------------------------------------------------

class BrandingRequest(BaseModel):
    """API request for branding recommendations."""
    model_config = ConfigDict(strict=True)

    user_input: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="User's description of their branding needs",
    )

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
    )

    goals: list[GoalType] = Field(
        default_factory=list,
        max_length=5,
    )

    current_skills: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    budget_max: float | None = Field(
        default=None,
        ge=0,
    )


class BrandingResponse(BaseModel):
    """API response for branding recommendations."""
    model_config = ConfigDict(strict=True)

    request_id: str
    recommendations: list[ProductRecommendation]
    reasoning: str
    skill_gaps: dict[str, str]
    next_steps: list[str]
    processing_time_ms: float
    pii_redacted: bool = False
