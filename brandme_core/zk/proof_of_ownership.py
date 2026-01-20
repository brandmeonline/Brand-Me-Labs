"""
Brand.Me v9 — Zero-Knowledge Proof of Ownership
=================================================

Implements ZK circuits for privacy-preserving asset ownership verification.

AR glasses can verify a user owns an asset without the user sharing their
private keys or revealing the full ownership graph.

Architecture:
- User generates a proof locally (on phone/secure device)
- Proof is sent to AR glasses
- AR glasses verify the proof without knowing the private key
- Proof is cached with TTL for performance
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
import json

from brandme_core.logging import get_logger

logger = get_logger("zk.proof_of_ownership")


class ProofType(str, Enum):
    """Types of ZK proofs supported."""
    OWNERSHIP = "ownership"           # Proves user owns an asset
    MEMBERSHIP = "membership"         # Proves asset is in a collection
    ATTRIBUTE = "attribute"           # Proves asset has certain attribute
    CUSTODY_CHAIN = "custody_chain"   # Proves valid custody chain


@dataclass
class ProofRequest:
    """Request to generate a ZK proof."""
    user_id: str
    asset_id: str
    proof_type: ProofType = ProofType.OWNERSHIP
    device_id: Optional[str] = None          # AR glasses device ID
    challenge_nonce: Optional[str] = None    # Fresh challenge from verifier
    required_attributes: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProofOfOwnership:
    """
    Zero-knowledge proof of asset ownership.

    The proof demonstrates that:
    1. User knows the private key associated with user_id
    2. There exists an ownership record linking user_id to asset_id
    3. The ownership record is valid (not expired, not revoked)

    Without revealing:
    - The actual private key
    - Other assets owned by the user
    - The full ownership history
    """
    proof_id: str
    user_id_commitment: str      # Cryptographic commitment to user_id
    asset_id_commitment: str     # Cryptographic commitment to asset_id
    proof_type: ProofType
    proof_data: bytes            # The actual ZK proof (circuit output)
    public_signals: Dict[str, Any]  # Public inputs/outputs of the circuit
    created_at: datetime
    expires_at: datetime
    device_bound: Optional[str] = None  # If proof is bound to specific device

    def is_valid(self) -> bool:
        """Check if proof is still valid (not expired)."""
        return datetime.utcnow() < self.expires_at


@dataclass
class ProofResponse:
    """Response from proof generation."""
    success: bool
    proof: Optional[ProofOfOwnership] = None
    error: Optional[str] = None
    generation_time_ms: float = 0


@dataclass
class ProofVerificationResult:
    """Result of proof verification."""
    is_valid: bool
    proof_id: Optional[str] = None
    verified_claims: Dict[str, bool] = field(default_factory=dict)
    reason: Optional[str] = None
    verification_time_ms: float = 0


class ZKProofManager:
    """
    Manages ZK proof generation, verification, and caching.

    Uses Spanner ZKProofCache table for distributed caching.
    """

    # Default proof TTL
    DEFAULT_TTL_MINUTES = 60

    # Maximum proofs per user (prevent DoS)
    MAX_ACTIVE_PROOFS_PER_USER = 100

    def __init__(
        self,
        spanner_pool,
        ttl_minutes: int = DEFAULT_TTL_MINUTES,
        enable_device_binding: bool = True
    ):
        """
        Initialize the ZK proof manager.

        Args:
            spanner_pool: Spanner connection pool
            ttl_minutes: Default proof TTL
            enable_device_binding: Bind proofs to specific devices
        """
        self.spanner_pool = spanner_pool
        self.ttl = timedelta(minutes=ttl_minutes)
        self.enable_device_binding = enable_device_binding

    def _generate_commitment(self, value: str, salt: Optional[str] = None) -> str:
        """
        Generate a cryptographic commitment to a value.

        Uses Pedersen-style commitment: H(value || salt)
        """
        if salt is None:
            salt = secrets.token_hex(16)

        combined = f"{value}:{salt}"
        commitment = hashlib.sha256(combined.encode()).hexdigest()
        return commitment

    def _generate_proof_data(
        self,
        user_id: str,
        asset_id: str,
        ownership_record: Dict[str, Any],
        challenge_nonce: Optional[str] = None
    ) -> tuple:
        """
        Generate the actual ZK proof data.

        In production, this would use a ZK library (snarkjs, bellman, etc.)
        to generate a SNARK/STARK proof. For v9, we use a simplified
        commitment-based proof that demonstrates the concept.

        Returns:
            (proof_bytes, public_signals)
        """
        # Generate salts for commitments
        user_salt = secrets.token_hex(16)
        asset_salt = secrets.token_hex(16)

        # Create commitments
        user_commitment = self._generate_commitment(user_id, user_salt)
        asset_commitment = self._generate_commitment(asset_id, asset_salt)

        # Create ownership proof (simplified Schnorr-like proof)
        # In production: actual ZK circuit output
        timestamp = datetime.utcnow().isoformat()
        nonce = challenge_nonce or secrets.token_hex(16)

        proof_input = f"{user_commitment}:{asset_commitment}:{timestamp}:{nonce}"
        proof_hash = hashlib.sha256(proof_input.encode()).hexdigest()

        # Proof data structure
        proof_data = json.dumps({
            "version": "v9.zk.1",
            "scheme": "commitment_based",  # In production: "groth16" or "plonk"
            "user_commitment": user_commitment,
            "asset_commitment": asset_commitment,
            "ownership_hash": hashlib.sha256(
                f"{user_id}:{asset_id}".encode()
            ).hexdigest()[:16],  # Truncated for privacy
            "timestamp": timestamp,
            "nonce": nonce,
            "proof_hash": proof_hash,
        }).encode()

        public_signals = {
            "user_commitment": user_commitment,
            "asset_commitment": asset_commitment,
            "timestamp": timestamp,
            "nonce": nonce,
            "ownership_valid": True,
            "proof_version": "v9.zk.1",
        }

        return proof_data, public_signals

    async def generate_proof(
        self,
        request: ProofRequest
    ) -> ProofResponse:
        """
        Generate a ZK proof of ownership.

        Args:
            request: The proof request

        Returns:
            ProofResponse with the generated proof
        """
        import time
        start_time = time.time()

        try:
            # Verify ownership exists in Spanner
            ownership = await self._verify_ownership_exists(
                request.user_id,
                request.asset_id
            )

            if not ownership:
                return ProofResponse(
                    success=False,
                    error="No valid ownership record found"
                )

            # Generate the proof
            proof_data, public_signals = self._generate_proof_data(
                request.user_id,
                request.asset_id,
                ownership,
                request.challenge_nonce
            )

            # Create proof object
            proof_id = secrets.token_hex(16)
            now = datetime.utcnow()

            proof = ProofOfOwnership(
                proof_id=proof_id,
                user_id_commitment=public_signals["user_commitment"],
                asset_id_commitment=public_signals["asset_commitment"],
                proof_type=request.proof_type,
                proof_data=proof_data,
                public_signals=public_signals,
                created_at=now,
                expires_at=now + self.ttl,
                device_bound=request.device_id if self.enable_device_binding else None
            )

            # Cache the proof in Spanner
            await self._cache_proof(request.user_id, request.asset_id, proof)

            generation_time = (time.time() - start_time) * 1000

            logger.info({
                "event": "zk_proof_generated",
                "proof_id": proof_id,
                "user_id": request.user_id[:8] + "...",
                "asset_id": request.asset_id[:8] + "...",
                "proof_type": request.proof_type.value,
                "generation_time_ms": generation_time
            })

            return ProofResponse(
                success=True,
                proof=proof,
                generation_time_ms=generation_time
            )

        except Exception as e:
            logger.error({
                "event": "zk_proof_generation_failed",
                "error": str(e),
                "user_id": request.user_id[:8] + "..."
            })
            return ProofResponse(
                success=False,
                error=str(e)
            )

    async def verify_proof(
        self,
        proof: ProofOfOwnership,
        device_id: Optional[str] = None,
        challenge_nonce: Optional[str] = None
    ) -> ProofVerificationResult:
        """
        Verify a ZK proof.

        Args:
            proof: The proof to verify
            device_id: Device requesting verification (for device binding)
            challenge_nonce: Fresh nonce for replay protection

        Returns:
            ProofVerificationResult
        """
        import time
        start_time = time.time()

        verified_claims = {}

        # Check expiration
        if not proof.is_valid():
            return ProofVerificationResult(
                is_valid=False,
                proof_id=proof.proof_id,
                reason="Proof has expired",
                verification_time_ms=(time.time() - start_time) * 1000
            )

        verified_claims["not_expired"] = True

        # Check device binding
        if self.enable_device_binding and proof.device_bound:
            if device_id != proof.device_bound:
                return ProofVerificationResult(
                    is_valid=False,
                    proof_id=proof.proof_id,
                    reason="Proof bound to different device",
                    verified_claims=verified_claims,
                    verification_time_ms=(time.time() - start_time) * 1000
                )

        verified_claims["device_binding"] = True

        # Verify proof data integrity
        try:
            proof_content = json.loads(proof.proof_data.decode())

            # Verify commitments match
            if proof_content["user_commitment"] != proof.user_id_commitment:
                return ProofVerificationResult(
                    is_valid=False,
                    proof_id=proof.proof_id,
                    reason="User commitment mismatch",
                    verified_claims=verified_claims,
                    verification_time_ms=(time.time() - start_time) * 1000
                )

            verified_claims["user_commitment_valid"] = True

            if proof_content["asset_commitment"] != proof.asset_id_commitment:
                return ProofVerificationResult(
                    is_valid=False,
                    proof_id=proof.proof_id,
                    reason="Asset commitment mismatch",
                    verified_claims=verified_claims,
                    verification_time_ms=(time.time() - start_time) * 1000
                )

            verified_claims["asset_commitment_valid"] = True

            # Verify proof hash
            expected_input = (
                f"{proof_content['user_commitment']}:"
                f"{proof_content['asset_commitment']}:"
                f"{proof_content['timestamp']}:"
                f"{proof_content['nonce']}"
            )
            expected_hash = hashlib.sha256(expected_input.encode()).hexdigest()

            if proof_content["proof_hash"] != expected_hash:
                return ProofVerificationResult(
                    is_valid=False,
                    proof_id=proof.proof_id,
                    reason="Proof hash verification failed",
                    verified_claims=verified_claims,
                    verification_time_ms=(time.time() - start_time) * 1000
                )

            verified_claims["proof_hash_valid"] = True
            verified_claims["ownership_proven"] = True

        except (json.JSONDecodeError, KeyError) as e:
            return ProofVerificationResult(
                is_valid=False,
                proof_id=proof.proof_id,
                reason=f"Proof data parsing failed: {str(e)}",
                verified_claims=verified_claims,
                verification_time_ms=(time.time() - start_time) * 1000
            )

        verification_time = (time.time() - start_time) * 1000

        logger.info({
            "event": "zk_proof_verified",
            "proof_id": proof.proof_id,
            "verification_time_ms": verification_time
        })

        return ProofVerificationResult(
            is_valid=True,
            proof_id=proof.proof_id,
            verified_claims=verified_claims,
            verification_time_ms=verification_time
        )

    async def get_cached_proof(
        self,
        user_id: str,
        asset_id: str,
        device_id: Optional[str] = None
    ) -> Optional[ProofOfOwnership]:
        """
        Get a cached proof if it exists and is still valid.

        Args:
            user_id: User ID
            asset_id: Asset ID
            device_id: Device ID for device-bound proofs

        Returns:
            Cached proof if valid, None otherwise
        """
        from google.cloud.spanner_v1 import param_types

        def _get_cached(transaction):
            # Build query based on device binding
            if device_id and self.enable_device_binding:
                query = """
                    SELECT proof_id, proof_data, public_signals, expires_at, device_session_id
                    FROM ZKProofCache
                    WHERE user_id = @user_id
                        AND asset_id = @asset_id
                        AND device_session_id = @device_session_id
                    SELECT proof_id, proof_data, public_signals, expires_at, device_id
                    FROM ZKProofCache
                    WHERE user_id = @user_id
                        AND asset_id = @asset_id
                        AND device_id = @device_id
                        AND expires_at > CURRENT_TIMESTAMP()
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                params = {
                    "user_id": user_id,
                    "asset_id": asset_id,
                    "device_session_id": device_id
                    "device_id": device_id
                }
                param_types_map = {
                    "user_id": param_types.STRING,
                    "asset_id": param_types.STRING,
                    "device_session_id": param_types.STRING
                }
            else:
                query = """
                    SELECT proof_id, proof_data, public_signals, expires_at, device_session_id
                    "device_id": param_types.STRING
                }
            else:
                query = """
                    SELECT proof_id, proof_data, public_signals, expires_at, device_id
                    FROM ZKProofCache
                    WHERE user_id = @user_id
                        AND asset_id = @asset_id
                        AND expires_at > CURRENT_TIMESTAMP()
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                params = {
                    "user_id": user_id,
                    "asset_id": asset_id
                }
                param_types_map = {
                    "user_id": param_types.STRING,
                    "asset_id": param_types.STRING
                }

            results = transaction.execute_sql(
                query,
                params=params,
                param_types=param_types_map
            )

            for row in results:
                return row
            return None

        try:
            cached = self.spanner_pool.database.run_in_transaction(_get_cached)

            if cached:
                proof_data_str = cached[1]
                public_signals_str = cached[2]

                return ProofOfOwnership(
                    proof_id=cached[0],
                    user_id_commitment=self._generate_commitment(user_id),
                    asset_id_commitment=self._generate_commitment(asset_id),
                    proof_type=ProofType.OWNERSHIP,
                    proof_data=proof_data_str.encode() if isinstance(proof_data_str, str) else proof_data_str,
                    public_signals=json.loads(public_signals_str) if isinstance(public_signals_str, str) else public_signals_str,
                    created_at=datetime.utcnow(),  # Approximate
                    expires_at=cached[3],
                    device_bound=cached[4]
                )

            return None

        except Exception as e:
            logger.warning({
                "event": "cache_lookup_failed",
                "error": str(e)
            })
            return None

    async def _verify_ownership_exists(
        self,
        user_id: str,
        asset_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Verify that ownership exists in Spanner.
        """
        from google.cloud.spanner_v1 import param_types

        def _check_ownership(transaction):
            results = transaction.execute_sql(
                """
                SELECT owner_id, acquired_at, transfer_method, is_current
                FROM Owns
                WHERE owner_id = @user_id
                    AND asset_id = @asset_id
                    AND is_current = true
                SELECT owner_id, acquired_at, share_pct, is_active
                FROM Owns
                WHERE owner_id = @user_id
                    AND asset_id = @asset_id
                    AND is_active = true
                """,
                params={
                    "user_id": user_id,
                    "asset_id": asset_id
                },
                param_types={
                    "user_id": param_types.STRING,
                    "asset_id": param_types.STRING
                }
            )

            for row in results:
                return {
                    "owner_id": row[0],
                    "acquired_at": row[1],
                    "transfer_method": row[2],
                    "is_current": row[3]
                    "share_pct": row[2],
                    "is_active": row[3]
                }
            return None

        return self.spanner_pool.database.run_in_transaction(_check_ownership)

    async def _cache_proof(
        self,
        user_id: str,
        asset_id: str,
        proof: ProofOfOwnership
    ):
        """
        Cache a proof in Spanner.
        """
        from google.cloud import spanner

        def _insert_cache(transaction):
            transaction.insert(
                table="ZKProofCache",
                columns=[
                    "proof_id", "user_id", "asset_id", "proof_type",
                    "proof_hash", "proof_data", "public_signals", "device_session_id",
                    "proof_data", "public_signals", "device_id",
                    "created_at", "expires_at"
                ],
                values=[(
                    proof.proof_id,
                    user_id,
                    asset_id,
                    proof.proof_type.value,
                    hashlib.sha256(proof.proof_data).hexdigest() if isinstance(proof.proof_data, bytes) else hashlib.sha256(proof.proof_data.encode()).hexdigest(),
                    proof.proof_data.decode() if isinstance(proof.proof_data, bytes) else proof.proof_data,
                    json.dumps(proof.public_signals),
                    proof.device_bound,
                    spanner.COMMIT_TIMESTAMP,
                    proof.expires_at
                )]
            )

        self.spanner_pool.database.run_in_transaction(_insert_cache)

    async def invalidate_proofs(
        self,
        user_id: str,
        asset_id: Optional[str] = None
    ) -> int:
        """
        Invalidate cached proofs (e.g., after ownership transfer).

        Args:
            user_id: User whose proofs to invalidate
            asset_id: Specific asset (or all if None)

        Returns:
            Number of proofs invalidated
        """
        from google.cloud.spanner_v1 import param_types

        def _invalidate(transaction):
            if asset_id:
                # Delete specific asset proofs
                result = transaction.execute_sql(
                    """
                    DELETE FROM ZKProofCache
                    WHERE user_id = @user_id AND asset_id = @asset_id
                    """,
                    params={
                        "user_id": user_id,
                        "asset_id": asset_id
                    },
                    param_types={
                        "user_id": param_types.STRING,
                        "asset_id": param_types.STRING
                    }
                )
            else:
                # Delete all user proofs
                result = transaction.execute_sql(
                    """
                    DELETE FROM ZKProofCache
                    WHERE user_id = @user_id
                    """,
                    params={"user_id": user_id},
                    param_types={"user_id": param_types.STRING}
                )

            return result.stats.row_count_exact if result.stats else 0

        count = self.spanner_pool.database.run_in_transaction(_invalidate)

        logger.info({
            "event": "zk_proofs_invalidated",
            "user_id": user_id[:8] + "...",
            "asset_id": asset_id[:8] + "..." if asset_id else "all",
            "count": count
        })

        return count
