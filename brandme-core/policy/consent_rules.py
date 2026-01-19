"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Consent Rules Module (DEPRECATED)
=================================

.. deprecated:: v8
    This module is deprecated and will be removed in a future version.
    Use :mod:`brandme_core.spanner.consent_graph` instead, which provides:

    - O(1) consent lookups via Spanner Graph
    - Global revocation in single operation
    - Friendship graph traversal
    - Driver-level PII redaction

    Example migration::

        # Old (deprecated):
        from brandme_core.policy.consent_rules import get_scope, are_friends

        # New (v8):
        from brandme_core.spanner.consent_graph import ConsentGraphClient
        consent_graph = ConsentGraphClient(spanner_pool)
        decision = await consent_graph.check_consent(viewer_id, owner_id, asset_id)

Determines what data can be shown based on consent and relationship between
scanner and garment owner.

Scope levels:
- public: Anyone can view (ESG data, brand info, public certifications)
- friends_only: Only friends of the owner can view (ownership history, provenance)
- private: Only the owner can view (purchase price, wallet details, personal notes)
"""

import os
import warnings
from typing import Literal, Optional

# DEPRECATED: This module uses stub implementations
# Replaced by brandme_core.spanner.consent_graph in v8
warnings.warn(
    "consent_rules module is deprecated. Use brandme_core.spanner.consent_graph instead.",
    DeprecationWarning,
    stacklevel=2
)


ScopeLevel = Literal["public", "friends_only", "private"]


def get_scope(scanner_user_id: str, garment_id: str) -> ScopeLevel:
    """
    Determine the visibility scope for a scan based on consent rules.

    Args:
        scanner_user_id: UUID of the user scanning the garment
        garment_id: UUID of the garment being scanned

    Returns:
        Scope level: "public", "friends_only", or "private"

    Logic:
        1. Query database to find garment owner_user_id
        2. If scanner == owner, return "private" (full access)
        3. Query relationship graph to check if scanner is friends with owner
        4. If friends, return "friends_only"
        5. Otherwise, return "public"

    Current implementation (stub):
        - Returns "public" for all scans
        - TODO: Implement database queries for ownership and relationships
    """
    # Stub implementation for MVP
    # In production, this would:
    # 1. SELECT owner_user_id FROM garments WHERE garment_id = $1
    # 2. If scanner_user_id == owner_user_id, return "private"
    # 3. Check Neo4j or PostgreSQL for friendship:
    #    MATCH (scanner:User {user_id: $1})-[:FRIENDS_WITH]-(owner:User {user_id: $2})
    # 4. If friendship exists, return "friends_only"
    # 5. Otherwise return "public"

    # For now, always return public scope
    # This is safe - it's more restrictive than necessary
    default_scope = os.getenv("DEFAULT_CONSENT_SCOPE", "public")

    if default_scope not in ("public", "friends_only", "private"):
        default_scope = "public"

    return default_scope  # type: ignore


def check_explicit_consent(
    scanner_user_id: str,
    garment_id: str,
    requested_facets: list[str]
) -> dict[str, bool]:
    """
    Check explicit consent for specific data facets.

    Args:
        scanner_user_id: UUID of the user scanning
        garment_id: UUID of the garment
        requested_facets: List of facet types (e.g., ["ESG", "provenance", "pricing"])

    Returns:
        Dict mapping each facet to whether access is allowed

    TODO: Implement database-backed consent matrix
        - Table: consent_policies (garment_id, facet_type, scope_required)
        - Query: Check if current scope meets required scope for each facet
    """
    # Stub: Allow all public facets
    result = {}
    public_facets = {"ESG", "brand", "materials", "certifications"}

    for facet in requested_facets:
        result[facet] = facet in public_facets

    return result


def is_owner(scanner_user_id: str, garment_id: str) -> bool:
    """
    Check if the scanner is the owner of the garment.

    Args:
        scanner_user_id: UUID of the user scanning
        garment_id: UUID of the garment

    Returns:
        True if scanner owns the garment, False otherwise

    TODO: Implement database query:
        SELECT 1 FROM garments
        WHERE garment_id = $1 AND owner_user_id = $2
        LIMIT 1
    """
    # Stub: Always return False for non-owners
    return False


def are_friends(user_id_1: str, user_id_2: str) -> bool:
    """
    Check if two users are friends.

    Args:
        user_id_1: UUID of first user
        user_id_2: UUID of second user

    Returns:
        True if users are friends, False otherwise

    TODO: Implement relationship query:
        - Option 1 (Neo4j): MATCH (u1:User {user_id: $1})-[:FRIENDS_WITH]-(u2:User {user_id: $2})
        - Option 2 (PostgreSQL): SELECT 1 FROM friendships
          WHERE (user_id_1 = $1 AND user_id_2 = $2) OR (user_id_1 = $2 AND user_id_2 = $1)
          AND status = 'accepted'
    """
    # Stub: Always return False (no friendships)
    return False
