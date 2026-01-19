"""
Brand.Me Consent Graph Client
============================

Provides O(1) consent lookups and instant global revocation
using Spanner Graph queries.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import uuid

from google.cloud.spanner_v1 import param_types

from brandme_core.logging import get_logger

logger = get_logger("spanner.consent")


class ConsentScope(Enum):
    """Scope levels for consent policies."""
    GLOBAL = "global"
    ASSET_SPECIFIC = "asset_specific"
    FACET_SPECIFIC = "facet_specific"
    GRANTEE_SPECIFIC = "grantee_specific"


class Visibility(Enum):
    """Visibility levels for consent."""
    PUBLIC = "public"
    FRIENDS_ONLY = "friends_only"
    PRIVATE = "private"
    CUSTOM = "custom"


@dataclass
class ConsentDecision:
    """Result of a consent check."""
    allowed: bool
    visibility: str
    scope: str
    consent_id: Optional[str] = None
    policy_version: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class FriendshipStatus:
    """Status of friendship between two users."""
    are_friends: bool
    status: Optional[str] = None
    since: Optional[datetime] = None


class ConsentGraphClient:
    """
    Consent Graph operations using Spanner.

    Provides:
    - O(1) consent lookups via indexed queries
    - Instant global revocation
    - Friend relationship checks
    - Hierarchical consent resolution
    """

    def __init__(self, pool_manager):
        self.pool = pool_manager

    async def check_consent(
        self,
        viewer_id: str,
        owner_id: str,
        asset_id: Optional[str] = None,
        facet_type: Optional[str] = None
    ) -> ConsentDecision:
        """
        Check if viewer has consent to access owner's data.

        Resolution order (most specific wins):
        1. Grantee-specific consent for this viewer
        2. Facet-specific consent
        3. Asset-specific consent
        4. Global consent

        Returns ConsentDecision with allowed status and visibility.
        """
        logger.info({
            "event": "consent_check",
            "viewer_id": viewer_id[:8] + "...",
            "owner_id": owner_id[:8] + "...",
            "asset_id": asset_id[:8] + "..." if asset_id else None,
            "facet_type": facet_type
        })

        # Same user always has full access
        if viewer_id == owner_id:
            return ConsentDecision(
                allowed=True,
                visibility="private",
                scope="owner",
                reason="viewer_is_owner"
            )

        # Check friendship status
        friendship = await self.check_friendship(viewer_id, owner_id)

        # Build consent query with hierarchy
        sql = """
        SELECT
            consent_id,
            scope,
            visibility,
            policy_version,
            is_revoked,
            grantee_user_id
        FROM ConsentPolicies
        WHERE user_id = @owner_id
            AND is_revoked = false
            AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP())
            AND (
                -- Global consent
                (scope = 'global' AND asset_id IS NULL)
                -- Asset-specific consent
                OR (scope = 'asset_specific' AND asset_id = @asset_id)
                -- Facet-specific consent
                OR (scope = 'facet_specific' AND asset_id = @asset_id AND facet_type = @facet_type)
                -- Grantee-specific consent
                OR (scope = 'grantee_specific' AND grantee_user_id = @viewer_id)
            )
        ORDER BY
            CASE scope
                WHEN 'grantee_specific' THEN 1
                WHEN 'facet_specific' THEN 2
                WHEN 'asset_specific' THEN 3
                WHEN 'global' THEN 4
            END
        LIMIT 1
        """

        async with self.pool.session() as snapshot:
            result = snapshot.execute_sql(
                sql,
                params={
                    'owner_id': owner_id,
                    'viewer_id': viewer_id,
                    'asset_id': asset_id or '',
                    'facet_type': facet_type or ''
                },
                param_types={
                    'owner_id': param_types.STRING,
                    'viewer_id': param_types.STRING,
                    'asset_id': param_types.STRING,
                    'facet_type': param_types.STRING
                }
            )

            rows = list(result)

        if not rows:
            # No explicit consent found, use defaults
            if friendship.are_friends:
                return ConsentDecision(
                    allowed=True,
                    visibility="friends_only",
                    scope="default_friends",
                    reason="friends_default_access"
                )
            else:
                return ConsentDecision(
                    allowed=True,
                    visibility="public",
                    scope="default_public",
                    reason="public_default_access"
                )

        row = rows[0]
        consent_id, scope, visibility, policy_version, is_revoked, grantee_id = row

        # Check if viewer meets visibility requirements
        allowed = False
        if visibility == "public":
            allowed = True
        elif visibility == "friends_only":
            allowed = friendship.are_friends
        elif visibility == "private":
            allowed = False  # Only owner, checked above
        elif visibility == "custom":
            # Custom means grantee-specific
            allowed = grantee_id == viewer_id

        return ConsentDecision(
            allowed=allowed,
            visibility=visibility,
            scope=scope,
            consent_id=consent_id,
            policy_version=policy_version,
            reason=f"consent_{scope}"
        )

    async def check_friendship(
        self,
        user_id_1: str,
        user_id_2: str
    ) -> FriendshipStatus:
        """
        Check if two users are friends.

        Uses canonical ordering (user_id_a < user_id_b) for consistent lookups.
        """
        # Ensure canonical order
        if user_id_1 > user_id_2:
            user_id_1, user_id_2 = user_id_2, user_id_1

        sql = """
        SELECT status, accepted_at
        FROM FriendsWith
        WHERE user_id_a = @user_a AND user_id_b = @user_b
        """

        async with self.pool.session() as snapshot:
            result = snapshot.execute_sql(
                sql,
                params={'user_a': user_id_1, 'user_b': user_id_2},
                param_types={
                    'user_a': param_types.STRING,
                    'user_b': param_types.STRING
                }
            )
            rows = list(result)

        if not rows:
            return FriendshipStatus(are_friends=False)

        status, accepted_at = rows[0]
        return FriendshipStatus(
            are_friends=(status == 'accepted'),
            status=status,
            since=accepted_at
        )

    async def get_friends_list(self, user_id: str) -> List[str]:
        """Get list of friend user IDs."""
        sql = """
        SELECT
            CASE
                WHEN user_id_a = @user_id THEN user_id_b
                ELSE user_id_a
            END as friend_id
        FROM FriendsWith
        WHERE (user_id_a = @user_id OR user_id_b = @user_id)
            AND status = 'accepted'
        """

        async with self.pool.session() as snapshot:
            result = snapshot.execute_sql(
                sql,
                params={'user_id': user_id},
                param_types={'user_id': param_types.STRING}
            )
            return [row[0] for row in result]

    async def grant_consent(
        self,
        user_id: str,
        scope: ConsentScope,
        visibility: Visibility,
        asset_id: Optional[str] = None,
        facet_type: Optional[str] = None,
        grantee_user_id: Optional[str] = None,
        policy_version: str = "v1"
    ) -> str:
        """
        Grant consent with specified scope and visibility.

        Returns consent_id.
        """
        from google.cloud import spanner

        consent_id = str(uuid.uuid4())

        def _insert(transaction):
            transaction.insert(
                table='ConsentPolicies',
                columns=[
                    'consent_id', 'user_id', 'scope', 'visibility',
                    'asset_id', 'facet_type', 'grantee_user_id',
                    'policy_version', 'is_revoked', 'created_at', 'updated_at'
                ],
                values=[(
                    consent_id,
                    user_id,
                    scope.value,
                    visibility.value,
                    asset_id,
                    facet_type,
                    grantee_user_id,
                    policy_version,
                    False,
                    spanner.COMMIT_TIMESTAMP,
                    spanner.COMMIT_TIMESTAMP
                )]
            )
            return consent_id

        self.pool.run_in_transaction(_insert)

        logger.info({
            "event": "consent_granted",
            "consent_id": consent_id,
            "user_id": user_id[:8] + "...",
            "scope": scope.value,
            "visibility": visibility.value
        })

        return consent_id

    async def revoke_global_consent(
        self,
        user_id: str,
        reason: Optional[str] = None
    ) -> int:
        """
        Instantly revoke ALL consent for a user (global revocation).

        This is O(1) for the write, affecting all owned assets at once.
        Returns number of policies revoked.
        """
        from google.cloud import spanner

        def _revoke(transaction):
            # Update all non-revoked consent policies for this user
            result = transaction.execute_sql(
                """
                SELECT COUNT(*)
                FROM ConsentPolicies
                WHERE user_id = @user_id AND is_revoked = false
                """,
                params={'user_id': user_id},
                param_types={'user_id': param_types.STRING}
            )
            count = list(result)[0][0]

            # Batch update
            transaction.execute_update(
                """
                UPDATE ConsentPolicies
                SET is_revoked = true,
                    revoked_at = PENDING_COMMIT_TIMESTAMP(),
                    revocation_reason = @reason,
                    updated_at = PENDING_COMMIT_TIMESTAMP()
                WHERE user_id = @user_id AND is_revoked = false
                """,
                params={
                    'user_id': user_id,
                    'reason': reason or 'global_revocation'
                },
                param_types={
                    'user_id': param_types.STRING,
                    'reason': param_types.STRING
                }
            )

            return count

        count = self.pool.run_in_transaction(_revoke)

        logger.info({
            "event": "global_consent_revoked",
            "user_id": user_id[:8] + "...",
            "policies_revoked": count,
            "reason": reason
        })

        return count

    async def revoke_asset_consent(
        self,
        user_id: str,
        asset_id: str,
        reason: Optional[str] = None
    ) -> int:
        """Revoke consent for a specific asset."""
        def _revoke(transaction):
            result = transaction.execute_sql(
                """
                SELECT COUNT(*)
                FROM ConsentPolicies
                WHERE user_id = @user_id
                    AND asset_id = @asset_id
                    AND is_revoked = false
                """,
                params={'user_id': user_id, 'asset_id': asset_id},
                param_types={
                    'user_id': param_types.STRING,
                    'asset_id': param_types.STRING
                }
            )
            count = list(result)[0][0]

            transaction.execute_update(
                """
                UPDATE ConsentPolicies
                SET is_revoked = true,
                    revoked_at = PENDING_COMMIT_TIMESTAMP(),
                    revocation_reason = @reason,
                    updated_at = PENDING_COMMIT_TIMESTAMP()
                WHERE user_id = @user_id
                    AND asset_id = @asset_id
                    AND is_revoked = false
                """,
                params={
                    'user_id': user_id,
                    'asset_id': asset_id,
                    'reason': reason or 'asset_revocation'
                },
                param_types={
                    'user_id': param_types.STRING,
                    'asset_id': param_types.STRING,
                    'reason': param_types.STRING
                }
            )

            return count

        count = self.pool.run_in_transaction(_revoke)

        logger.info({
            "event": "asset_consent_revoked",
            "user_id": user_id[:8] + "...",
            "asset_id": asset_id[:8] + "...",
            "policies_revoked": count
        })

        return count

    async def add_friend(
        self,
        user_id_1: str,
        user_id_2: str,
        initiated_by: str
    ) -> bool:
        """Add a friendship between two users."""
        from google.cloud import spanner

        # Ensure canonical order
        if user_id_1 > user_id_2:
            user_id_1, user_id_2 = user_id_2, user_id_1

        def _add(transaction):
            transaction.insert(
                table='FriendsWith',
                columns=['user_id_a', 'user_id_b', 'status', 'initiated_by', 'created_at'],
                values=[(user_id_1, user_id_2, 'pending', initiated_by, spanner.COMMIT_TIMESTAMP)]
            )

        try:
            self.pool.run_in_transaction(_add)
            return True
        except Exception as e:
            logger.error({"event": "add_friend_failed", "error": str(e)})
            return False

    async def accept_friend(self, user_id_1: str, user_id_2: str) -> bool:
        """Accept a pending friend request."""
        from google.cloud import spanner

        if user_id_1 > user_id_2:
            user_id_1, user_id_2 = user_id_2, user_id_1

        def _accept(transaction):
            transaction.execute_update(
                """
                UPDATE FriendsWith
                SET status = 'accepted',
                    accepted_at = PENDING_COMMIT_TIMESTAMP()
                WHERE user_id_a = @user_a
                    AND user_id_b = @user_b
                    AND status = 'pending'
                """,
                params={'user_a': user_id_1, 'user_b': user_id_2},
                param_types={
                    'user_a': param_types.STRING,
                    'user_b': param_types.STRING
                }
            )

        try:
            self.pool.run_in_transaction(_accept)
            return True
        except Exception as e:
            logger.error({"event": "accept_friend_failed", "error": str(e)})
            return False
