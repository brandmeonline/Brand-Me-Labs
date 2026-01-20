"""
Brand.Me v9 — MCP Consent Verification
======================================

Verifies user consent for MCP tool access by external agents.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

from brandme_core.logging import get_logger

logger = get_logger("mcp.consent")


@dataclass
class ConsentResult:
    """Result of consent verification."""
    is_granted: bool
    user_id: str
    agent_id: str
    permission_scope: str
    reason: Optional[str] = None
    max_transaction_usd: Optional[float] = None
    daily_limit_usd: Optional[float] = None
    requires_human_approval: bool = True
    min_esg_score: float = 0.5
    expires_at: Optional[datetime] = None


class MCPConsentVerifier:
    """
    Verifies user consent for agent access to MCP tools.
    """

    def __init__(self, spanner_pool):
        """
        Initialize the consent verifier.

        Args:
            spanner_pool: Spanner connection pool
        """
        self.spanner_pool = spanner_pool

    async def verify(
        self,
        user_id: str,
        agent_id: str,
        permission_scope: str,
        tool_name: Optional[str] = None
    ) -> ConsentResult:
        """
        Verify user consent for agent access.

        Args:
            user_id: User granting consent
            agent_id: Agent requesting access
            permission_scope: Scope of permission requested
            tool_name: Specific tool being accessed (for logging)

        Returns:
            ConsentResult with consent details
        """
        from google.cloud.spanner_v1 import param_types

        def _check_consent(transaction):
            results = transaction.execute_sql(
                """
                SELECT
                    permission_scope,
                    max_transaction_usd,
                    daily_limit_usd,
                    requires_human_approval,
                    min_esg_score,
                    expires_at,
                    revoked_at
                FROM ConsentedByAgent
                WHERE user_id = @user_id
                    AND agent_id = @agent_id
                    AND permission_scope = @scope
                """,
                params={
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "scope": permission_scope
                },
                param_types={
                    "user_id": param_types.STRING,
                    "agent_id": param_types.STRING,
                    "scope": param_types.STRING
                }
            )
            for row in results:
                return row
            return None

        consent_row = self.spanner_pool.database.run_in_transaction(_check_consent)

        if consent_row is None:
            logger.info({
                "event": "mcp_consent_not_found",
                "user_id": user_id[:8] + "...",
                "agent_id": agent_id[:8] + "...",
                "permission_scope": permission_scope
            })
            return ConsentResult(
                is_granted=False,
                user_id=user_id,
                agent_id=agent_id,
                permission_scope=permission_scope,
                reason="No consent record found"
            )

        # Check if revoked
        revoked_at = consent_row[6]
        if revoked_at is not None:
            return ConsentResult(
                is_granted=False,
                user_id=user_id,
                agent_id=agent_id,
                permission_scope=permission_scope,
                reason="Consent has been revoked"
            )

        # Check expiration
        expires_at = consent_row[5]
        if expires_at and expires_at < datetime.utcnow():
            return ConsentResult(
                is_granted=False,
                user_id=user_id,
                agent_id=agent_id,
                permission_scope=permission_scope,
                reason="Consent has expired",
                expires_at=expires_at
            )

        logger.info({
            "event": "mcp_consent_verified",
            "user_id": user_id[:8] + "...",
            "agent_id": agent_id[:8] + "...",
            "permission_scope": permission_scope,
            "tool_name": tool_name
        })

        return ConsentResult(
            is_granted=True,
            user_id=user_id,
            agent_id=agent_id,
            permission_scope=permission_scope,
            max_transaction_usd=consent_row[1],
            daily_limit_usd=consent_row[2],
            requires_human_approval=consent_row[3] if consent_row[3] is not None else True,
            min_esg_score=consent_row[4] if consent_row[4] is not None else 0.5,
            expires_at=expires_at
        )

    async def get_all_consents(
        self,
        user_id: str
    ) -> list:
        """
        Get all agent consents for a user.

        Args:
            user_id: User ID

        Returns:
            List of consent records
        """
        from google.cloud.spanner_v1 import param_types

        def _get_consents(transaction):
            results = transaction.execute_sql(
                """
                SELECT
                    agent_id,
                    permission_scope,
                    max_transaction_usd,
                    daily_limit_usd,
                    requires_human_approval,
                    min_esg_score,
                    granted_at,
                    expires_at,
                    revoked_at
                FROM ConsentedByAgent
                WHERE user_id = @user_id
                    AND revoked_at IS NULL
                ORDER BY granted_at DESC
                """,
                params={"user_id": user_id},
                param_types={"user_id": param_types.STRING}
            )
            consents = []
            for row in results:
                consents.append({
                    "agent_id": row[0],
                    "permission_scope": row[1],
                    "max_transaction_usd": row[2],
                    "daily_limit_usd": row[3],
                    "requires_human_approval": row[4],
                    "min_esg_score": row[5],
                    "granted_at": row[6],
                    "expires_at": row[7],
                    "is_active": row[8] is None
                })
            return consents

        return self.spanner_pool.database.run_in_transaction(_get_consents)

    async def grant_consent(
        self,
        user_id: str,
        agent_id: str,
        permission_scope: str,
        max_transaction_usd: Optional[float] = None,
        daily_limit_usd: Optional[float] = None,
        requires_human_approval: bool = True,
        min_esg_score: float = 0.5,
        expires_at: Optional[datetime] = None
    ) -> bool:
        """
        Grant consent to an agent.

        Args:
            user_id: User granting consent
            agent_id: Agent receiving consent
            permission_scope: Scope of permission
            max_transaction_usd: Maximum single transaction
            daily_limit_usd: Daily spending limit
            requires_human_approval: Whether human approval needed
            min_esg_score: Minimum ESG score for transactions
            expires_at: When consent expires

        Returns:
            True if consent granted
        """
        from google.cloud import spanner

        def _grant(transaction):
            transaction.insert_or_update(
                table="ConsentedByAgent",
                columns=[
                    "user_id", "agent_id", "permission_scope",
                    "max_transaction_usd", "daily_limit_usd",
                    "requires_human_approval", "min_esg_score",
                    "granted_at", "expires_at", "revoked_at"
                ],
                values=[(
                    user_id, agent_id, permission_scope,
                    max_transaction_usd, daily_limit_usd,
                    requires_human_approval, min_esg_score,
                    spanner.COMMIT_TIMESTAMP, expires_at, None
                )]
            )

        self.spanner_pool.database.run_in_transaction(_grant)

        logger.info({
            "event": "mcp_consent_granted",
            "user_id": user_id[:8] + "...",
            "agent_id": agent_id[:8] + "...",
            "permission_scope": permission_scope
        })

        return True

    async def revoke_consent(
        self,
        user_id: str,
        agent_id: str,
        permission_scope: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Revoke consent from an agent.

        Args:
            user_id: User revoking consent
            agent_id: Agent losing consent
            permission_scope: Scope being revoked
            reason: Reason for revocation

        Returns:
            True if consent revoked
        """
        from google.cloud import spanner

        def _revoke(transaction):
            transaction.update(
                table="ConsentedByAgent",
                columns=[
                    "user_id", "agent_id", "permission_scope",
                    "revoked_at", "revoke_reason"
                ],
                values=[(
                    user_id, agent_id, permission_scope,
                    spanner.COMMIT_TIMESTAMP, reason
                )]
            )

        self.spanner_pool.database.run_in_transaction(_revoke)

        logger.info({
            "event": "mcp_consent_revoked",
            "user_id": user_id[:8] + "...",
            "agent_id": agent_id[:8] + "...",
            "permission_scope": permission_scope,
            "reason": reason
        })

        return True
