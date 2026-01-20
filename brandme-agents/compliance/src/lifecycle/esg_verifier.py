"""
Brand.Me v9 — Cardano ESG Score Verification
=============================================

Verifies material ESG scores from Cardano oracle for ethical oversight
of agentic transactions.

All agent-facilitated transactions (rental, resale) must pass ESG
verification before execution.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import httpx

from brandme_core.logging import get_logger

logger = get_logger("lifecycle.esg_verifier")


@dataclass
class ESGScore:
    """
    Environmental, Social, Governance score from Cardano oracle.
    """
    overall_score: float                        # 0.0-1.0 composite score
    environmental: float                        # 0.0-1.0 E score
    social: float                               # 0.0-1.0 S score
    governance: float                           # 0.0-1.0 G score
    carbon_footprint_kg: float                  # Per unit carbon
    water_usage_liters: float                   # Per unit water
    recyclability_pct: float                    # 0-100%
    certifications: List[str] = field(default_factory=list)
    cardano_tx_hash: Optional[str] = None
    oracle_timestamp: Optional[datetime] = None


@dataclass
class ESGVerificationResult:
    """Result of ESG verification for a transaction."""
    is_approved: bool
    asset_id: str
    esg_score: Optional[ESGScore] = None
    threshold: float = 0.5
    reason: Optional[str] = None
    requires_human_review: bool = False
    cardano_verified: bool = False
    verification_timestamp: Optional[datetime] = None


class ESGVerifier:
    """
    Verifies ESG scores from Cardano oracle.

    Used for ethical oversight of agentic transactions.
    """

    # ESG thresholds by transaction type
    THRESHOLDS = {
        "rental": 0.5,
        "resale": 0.6,
        "dissolve": 0.4,
        "reprint": 0.7,
        "default": 0.5
    }

    def __init__(
        self,
        cardano_node_url: str = "http://cardano-node:3001",
        cache_ttl_minutes: int = 60,
        timeout: int = 30,
        spanner_pool=None,
        allow_stub_fallback: bool = False,
        require_cardano: bool = True
    ):
        """
        Initialize the ESG verifier.

        Args:
            cardano_node_url: URL of Cardano node
            cache_ttl_minutes: Cache TTL for ESG scores
            timeout: Request timeout in seconds
            spanner_pool: Spanner connection pool for persistent caching
            allow_stub_fallback: If True, allow stub ESG when Cardano unavailable
            require_cardano: If True, fail when Cardano is unavailable (production mode)
        """
        self.cardano_node_url = cardano_node_url
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.timeout = timeout
        self.spanner_pool = spanner_pool
        self.allow_stub_fallback = allow_stub_fallback
        self.require_cardano = require_cardano
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, tuple] = {}  # asset_id -> (ESGScore, timestamp)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_cached(self, asset_id: str) -> Optional[ESGScore]:
        """Get cached ESG score if still valid."""
        if asset_id in self._cache:
            score, timestamp = self._cache[asset_id]
            if datetime.utcnow() - timestamp < self.cache_ttl:
                return score
            else:
                del self._cache[asset_id]
        return None

    def _set_cached(self, asset_id: str, score: ESGScore):
        """Cache an ESG score."""
        self._cache[asset_id] = (score, datetime.utcnow())

    async def get_material_esg(self, material_id: str) -> Optional[ESGScore]:
        """
        Get ESG score for a material from Cardano oracle.

        Args:
            material_id: Material ID to look up

        Returns:
            ESGScore if found, None otherwise
        """
        # Check cache first
        cached = self._get_cached(material_id)
        if cached:
            return cached

        try:
            client = await self._get_client()

            # Query Cardano oracle for ESG data
            response = await client.get(
                f"{self.cardano_node_url}/v1/oracle/esg/{material_id}"
            )

            if response.status_code == 200:
                data = response.json()
                score = ESGScore(
                    overall_score=data.get("overall_score", 0.5),
                    environmental=data.get("environmental", 0.5),
                    social=data.get("social", 0.5),
                    governance=data.get("governance", 0.5),
                    carbon_footprint_kg=data.get("carbon_footprint_kg", 0.0),
                    water_usage_liters=data.get("water_usage_liters", 0.0),
                    recyclability_pct=data.get("recyclability_pct", 0.0),
                    certifications=data.get("certifications", []),
                    cardano_tx_hash=data.get("tx_hash"),
                    oracle_timestamp=datetime.fromisoformat(data["timestamp"])
                    if data.get("timestamp") else None
                )
                self._set_cached(material_id, score)
                # Also persist to Spanner for resilience
                await self._cache_esg_to_spanner(material_id, score)
                return score
            else:
                logger.warning({
                    "event": "cardano_esg_lookup_failed",
                    "status_code": response.status_code,
                    "material_id": material_id[:8] + "..."
                })
                return None

        except httpx.ConnectError:
            logger.warning({
                "event": "cardano_unavailable",
                "material_id": material_id[:8] + "...",
                "require_cardano": self.require_cardano,
                "allow_stub": self.allow_stub_fallback
            })

            # Check Spanner cache for persisted ESG data
            cached_score = await self._get_spanner_cached_esg(material_id)
            if cached_score:
                logger.info({
                    "event": "esg_score_from_spanner_cache",
                    "material_id": material_id[:8] + "..."
                })
                return cached_score

            # Production mode: fail if Cardano is required
            if self.require_cardano and not self.allow_stub_fallback:
                logger.error({
                    "event": "cardano_required_but_unavailable",
                    "material_id": material_id[:8] + "..."
                })
                return None

            # Development mode: use stub ESG score
            if self.allow_stub_fallback:
                logger.warning({
                    "event": "cardano_unavailable_stub_esg",
                    "material_id": material_id[:8] + "..."
                })
                return self._stub_esg_score(material_id)

            return None

        except Exception as e:
            logger.error({
                "event": "esg_lookup_error",
                "error": str(e),
                "material_id": material_id[:8] + "..."
            })
            return None

    async def _get_spanner_cached_esg(self, material_id: str) -> Optional[ESGScore]:
        """Get cached ESG score from Spanner (persisted cache)."""
        if not self.spanner_pool:
            return None

        try:
            from google.cloud.spanner_v1 import param_types

            def _get_cached(transaction):
                results = transaction.execute_sql(
                    """
                    SELECT overall_score, environmental, social, governance,
                           carbon_footprint_kg, water_usage_liters, recyclability_pct,
                           certifications, cardano_tx_hash, oracle_timestamp
                    FROM MaterialESGCache
                    WHERE material_id = @material_id
                        AND oracle_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
                    LIMIT 1
                    """,
                    params={"material_id": material_id},
                    param_types={"material_id": param_types.STRING}
                )
                for row in results:
                    return {
                        "overall_score": row[0],
                        "environmental": row[1],
                        "social": row[2],
                        "governance": row[3],
                        "carbon_footprint_kg": row[4],
                        "water_usage_liters": row[5],
                        "recyclability_pct": row[6],
                        "certifications": row[7] if row[7] else [],
                        "cardano_tx_hash": row[8],
                        "oracle_timestamp": row[9]
                    }
                return None

            cached = self.spanner_pool.database.run_in_transaction(_get_cached)

            if cached:
                return ESGScore(
                    overall_score=cached["overall_score"],
                    environmental=cached["environmental"],
                    social=cached["social"],
                    governance=cached["governance"],
                    carbon_footprint_kg=cached["carbon_footprint_kg"],
                    water_usage_liters=cached["water_usage_liters"],
                    recyclability_pct=cached["recyclability_pct"],
                    certifications=cached["certifications"],
                    cardano_tx_hash=cached["cardano_tx_hash"],
                    oracle_timestamp=cached["oracle_timestamp"]
                )
            return None

        except Exception as e:
            logger.warning({
                "event": "esg_spanner_cache_check_failed",
                "error": str(e)
            })
            return None

    async def _cache_esg_to_spanner(self, material_id: str, score: ESGScore):
        """Cache ESG score to Spanner for persistence."""
        if not self.spanner_pool or not score.cardano_tx_hash:
            return

        try:
            from google.cloud import spanner
            import uuid

            def _cache(transaction):
                transaction.insert_or_update(
                    table="MaterialESGCache",
                    columns=[
                        "cache_id", "material_id", "overall_score",
                        "environmental", "social", "governance",
                        "carbon_footprint_kg", "water_usage_liters", "recyclability_pct",
                        "certifications", "cardano_tx_hash", "oracle_timestamp"
                    ],
                    values=[(
                        str(uuid.uuid4()),
                        material_id,
                        score.overall_score,
                        score.environmental,
                        score.social,
                        score.governance,
                        score.carbon_footprint_kg,
                        score.water_usage_liters,
                        score.recyclability_pct,
                        score.certifications,
                        score.cardano_tx_hash,
                        score.oracle_timestamp or spanner.COMMIT_TIMESTAMP
                    )]
                )

            self.spanner_pool.database.run_in_transaction(_cache)

        except Exception as e:
            logger.warning({
                "event": "esg_spanner_cache_write_failed",
                "error": str(e)
            })

    def _stub_esg_score(self, material_id: str) -> ESGScore:
        """
        Generate stub ESG score for development/testing.
        """
        # Generate deterministic score based on material_id
        hash_bytes = hashlib.sha256(material_id.encode()).digest()
        base_score = (hash_bytes[0] / 255) * 0.5 + 0.4  # 0.4-0.9 range

        return ESGScore(
            overall_score=base_score,
            environmental=base_score + 0.05,
            social=base_score,
            governance=base_score - 0.05,
            carbon_footprint_kg=5.0,
            water_usage_liters=100.0,
            recyclability_pct=85.0,
            certifications=["STUB_CERT"],
            oracle_timestamp=datetime.utcnow()
        )

    async def verify_transaction(
        self,
        asset_id: str,
        material_id: str,
        transaction_type: str,
        agent_id: Optional[str] = None,
        custom_threshold: Optional[float] = None
    ) -> ESGVerificationResult:
        """
        Verify ESG score for a transaction.

        Args:
            asset_id: Asset involved in transaction
            material_id: Primary material of the asset
            transaction_type: Type of transaction ("rental", "resale", etc.)
            agent_id: ID of agent facilitating transaction (if any)
            custom_threshold: Override default threshold

        Returns:
            ESGVerificationResult with approval status
        """
        threshold = custom_threshold or self.THRESHOLDS.get(
            transaction_type,
            self.THRESHOLDS["default"]
        )

        # Get ESG score
        esg_score = await self.get_material_esg(material_id)

        if esg_score is None:
            # Cannot verify - require human review
            return ESGVerificationResult(
                is_approved=False,
                asset_id=asset_id,
                threshold=threshold,
                reason="Could not retrieve ESG score from oracle",
                requires_human_review=True,
                verification_timestamp=datetime.utcnow()
            )

        # Check against threshold
        is_approved = esg_score.overall_score >= threshold

        # Log verification
        logger.info({
            "event": "esg_verification",
            "asset_id": asset_id[:8] + "...",
            "material_id": material_id[:8] + "...",
            "transaction_type": transaction_type,
            "esg_score": esg_score.overall_score,
            "threshold": threshold,
            "approved": is_approved,
            "agent_id": agent_id[:8] + "..." if agent_id else None
        })

        return ESGVerificationResult(
            is_approved=is_approved,
            asset_id=asset_id,
            esg_score=esg_score,
            threshold=threshold,
            reason=None if is_approved else f"ESG score {esg_score.overall_score:.2f} below threshold {threshold:.2f}",
            requires_human_review=not is_approved,
            cardano_verified=esg_score.cardano_tx_hash is not None,
            verification_timestamp=datetime.utcnow()
        )

    async def verify_agent_transaction(
        self,
        asset_id: str,
        material_id: str,
        agent_id: str,
        transaction_type: str,
        transaction_value_usd: float,
        user_consent: Dict[str, Any]
    ) -> ESGVerificationResult:
        """
        Verify ESG score for an agent-facilitated transaction.

        Implements ethical oversight for agentic transactions.

        Args:
            asset_id: Asset involved in transaction
            material_id: Primary material of the asset
            agent_id: ID of agent facilitating transaction
            transaction_type: Type of transaction
            transaction_value_usd: Value of transaction
            user_consent: User's consent settings for this agent

        Returns:
            ESGVerificationResult with detailed approval status
        """
        # Get user's minimum ESG requirement from consent
        user_min_esg = user_consent.get("min_esg_score", 0.5)

        # Use higher of user requirement and system threshold
        threshold = max(
            user_min_esg,
            self.THRESHOLDS.get(transaction_type, 0.5)
        )

        # Verify ESG
        result = await self.verify_transaction(
            asset_id=asset_id,
            material_id=material_id,
            transaction_type=transaction_type,
            agent_id=agent_id,
            custom_threshold=threshold
        )

        # Check if human approval required based on consent
        if user_consent.get("requires_human_approval", True):
            result.requires_human_review = True
            if result.reason:
                result.reason += " + User requires human approval"
            else:
                result.reason = "User requires human approval for agent transactions"

        # Check transaction limits
        max_tx = user_consent.get("max_transaction_usd")
        if max_tx and transaction_value_usd > max_tx:
            result.is_approved = False
            result.requires_human_review = True
            result.reason = f"Transaction ${transaction_value_usd:.2f} exceeds limit ${max_tx:.2f}"

        logger.info({
            "event": "agent_esg_verification",
            "asset_id": asset_id[:8] + "...",
            "agent_id": agent_id[:8] + "...",
            "transaction_type": transaction_type,
            "transaction_value": transaction_value_usd,
            "approved": result.is_approved,
            "requires_human_review": result.requires_human_review
        })

        return result
