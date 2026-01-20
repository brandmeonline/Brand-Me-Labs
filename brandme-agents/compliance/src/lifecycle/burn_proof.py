"""
Brand.Me v9 — Midnight Burn Proof Verification
===============================================

Verifies ZK burn proofs from Midnight for DISSOLVE→REPRINT transitions.
Ensures material was properly dissolved before allowing reprint.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import httpx

from brandme_core.logging import get_logger

logger = get_logger("lifecycle.burn_proof")


@dataclass
class BurnProof:
    """
    Midnight burn proof for material dissolution.

    This proof is generated when physical material is processed
    for recycling/dissolution and verified before allowing reprint.
    """
    proof_hash: str                             # SHA256 of ZK proof
    parent_asset_id: str                        # Asset that was dissolved
    material_batch_id: str                      # Material batch being recycled
    midnight_tx_hash: str                       # Midnight transaction reference
    dissolution_method: str                     # "chemical", "mechanical", "enzymatic"
    material_recovery_pct: float                # % of material recovered (0-100)
    verification_timestamp: Optional[datetime] = None
    verifier_id: Optional[str] = None           # ID of verifying facility


@dataclass
class BurnProofVerificationResult:
    """Result of burn proof verification."""
    is_valid: bool
    proof_hash: str
    parent_asset_id: str
    material_recovery_pct: Optional[float] = None
    error: Optional[str] = None
    midnight_confirmed: bool = False
    verification_timestamp: Optional[datetime] = None


class BurnProofVerifier:
    """
    Verifies Midnight burn proofs for circular economy transitions.

    In production, this connects to Midnight devnet/mainnet to verify
    ZK proofs of material dissolution.
    """

    def __init__(
        self,
        midnight_api_url: str = "http://midnight-devnet:9000",
        timeout: int = 30,
        spanner_pool=None,
        allow_stub_fallback: bool = False,
        require_midnight: bool = True
    ):
        """
        Initialize the burn proof verifier.

        Args:
            midnight_api_url: URL of Midnight API
            timeout: Request timeout in seconds
            spanner_pool: Spanner connection pool for caching verified proofs
            allow_stub_fallback: If True, allow stub verification when Midnight unavailable
            require_midnight: If True, fail when Midnight is unavailable (production mode)
        """
        self.midnight_api_url = midnight_api_url
        self.timeout = timeout
        self.spanner_pool = spanner_pool
        self.allow_stub_fallback = allow_stub_fallback
        self.require_midnight = require_midnight
        self._client: Optional[httpx.AsyncClient] = None

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

    async def verify(
        self,
        burn_proof_hash: str,
        parent_asset_id: str
    ) -> bool:
        """
        Verify a burn proof is valid.

        Args:
            burn_proof_hash: Hash of the burn proof
            parent_asset_id: ID of the dissolved parent asset

        Returns:
            True if proof is valid and confirmed on Midnight
        """
        result = await self.verify_detailed(burn_proof_hash, parent_asset_id)
        return result.is_valid

    async def verify_detailed(
        self,
        burn_proof_hash: str,
        parent_asset_id: str
    ) -> BurnProofVerificationResult:
        """
        Verify a burn proof with detailed results.

        Args:
            burn_proof_hash: Hash of the burn proof
            parent_asset_id: ID of the dissolved parent asset

        Returns:
            BurnProofVerificationResult with full details
        """
        try:
            client = await self._get_client()

            # Query Midnight for burn proof verification
            response = await client.post(
                f"{self.midnight_api_url}/v1/verify-burn-proof",
                json={
                    "proof_hash": burn_proof_hash,
                    "asset_id": parent_asset_id
                }
            )

            if response.status_code == 200:
                data = response.json()
                result = BurnProofVerificationResult(
                    is_valid=data.get("valid", False),
                    proof_hash=burn_proof_hash,
                    parent_asset_id=parent_asset_id,
                    material_recovery_pct=data.get("material_recovery_pct"),
                    midnight_confirmed=True,
                    verification_timestamp=datetime.utcnow()
                )
                # Cache successful verification
                if result.is_valid:
                    await self._cache_verification(result)
                return result
            else:
                logger.warning({
                    "event": "midnight_verification_failed",
                    "status_code": response.status_code,
                    "proof_hash": burn_proof_hash[:16] + "..."
                })
                return BurnProofVerificationResult(
                    is_valid=False,
                    proof_hash=burn_proof_hash,
                    parent_asset_id=parent_asset_id,
                    error=f"Midnight returned status {response.status_code}"
                )

        except httpx.ConnectError:
            logger.warning({
                "event": "midnight_unavailable",
                "proof_hash": burn_proof_hash[:16] + "...",
                "parent_asset_id": parent_asset_id[:8] + "...",
                "require_midnight": self.require_midnight,
                "allow_stub": self.allow_stub_fallback
            })

            # Check cached verification in Spanner first
            cached_result = await self._check_cached_verification(burn_proof_hash)
            if cached_result:
                logger.info({
                    "event": "burn_proof_cached_verification",
                    "proof_hash": burn_proof_hash[:16] + "..."
                })
                return cached_result

            # Production mode: fail if Midnight is required
            if self.require_midnight and not self.allow_stub_fallback:
                return BurnProofVerificationResult(
                    is_valid=False,
                    proof_hash=burn_proof_hash,
                    parent_asset_id=parent_asset_id,
                    error="Midnight network unavailable - burn proof cannot be verified in production mode",
                    midnight_confirmed=False
                )

            # Development mode: use stub verification
            if self.allow_stub_fallback:
                logger.warning({
                    "event": "midnight_unavailable_stub_verify",
                    "proof_hash": burn_proof_hash[:16] + "...",
                    "parent_asset_id": parent_asset_id[:8] + "..."
                })
                return await self._stub_verify(burn_proof_hash, parent_asset_id)

            # Default: fail verification
            return BurnProofVerificationResult(
                is_valid=False,
                proof_hash=burn_proof_hash,
                parent_asset_id=parent_asset_id,
                error="Midnight network unavailable",
                midnight_confirmed=False
            )

        except Exception as e:
            logger.error({
                "event": "burn_proof_verification_error",
                "error": str(e),
                "proof_hash": burn_proof_hash[:16] + "..."
            })
            return BurnProofVerificationResult(
                is_valid=False,
                proof_hash=burn_proof_hash,
                parent_asset_id=parent_asset_id,
                error=str(e)
            )

    async def _check_cached_verification(
        self,
        burn_proof_hash: str
    ) -> Optional[BurnProofVerificationResult]:
        """
        Check for cached verification result in Spanner.

        Returns cached result if found and still valid, None otherwise.
        """
        if not self.spanner_pool:
            return None

        try:
            from google.cloud.spanner_v1 import param_types

            def _check_cache(transaction):
                results = transaction.execute_sql(
                    """
                    SELECT parent_asset_id, material_recovery_pct, verified_at, is_valid
                    FROM BurnProofCache
                    WHERE proof_hash = @proof_hash
                        AND verified_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
                    LIMIT 1
                    """,
                    params={"proof_hash": burn_proof_hash},
                    param_types={"proof_hash": param_types.STRING}
                )
                for row in results:
                    return {
                        "parent_asset_id": row[0],
                        "material_recovery_pct": row[1],
                        "verified_at": row[2],
                        "is_valid": row[3]
                    }
                return None

            cached = self.spanner_pool.database.run_in_transaction(_check_cache)

            if cached:
                return BurnProofVerificationResult(
                    is_valid=cached["is_valid"],
                    proof_hash=burn_proof_hash,
                    parent_asset_id=cached["parent_asset_id"],
                    material_recovery_pct=cached["material_recovery_pct"],
                    midnight_confirmed=True,  # Was confirmed when cached
                    verification_timestamp=cached["verified_at"]
                )
            return None

        except Exception as e:
            logger.warning({
                "event": "burn_proof_cache_check_failed",
                "error": str(e)
            })
            return None

    async def _cache_verification(
        self,
        result: BurnProofVerificationResult
    ):
        """Cache successful verification result in Spanner."""
        if not self.spanner_pool or not result.midnight_confirmed:
            return

        try:
            from google.cloud import spanner
            import uuid

            def _cache(transaction):
                transaction.insert_or_update(
                    table="BurnProofCache",
                    columns=[
                        "cache_id", "proof_hash", "parent_asset_id",
                        "material_recovery_pct", "is_valid", "verified_at"
                    ],
                    values=[(
                        str(uuid.uuid4()),
                        result.proof_hash,
                        result.parent_asset_id,
                        result.material_recovery_pct,
                        result.is_valid,
                        spanner.COMMIT_TIMESTAMP
                    )]
                )

            self.spanner_pool.database.run_in_transaction(_cache)

        except Exception as e:
            logger.warning({
                "event": "burn_proof_cache_write_failed",
                "error": str(e)
            })

    async def _stub_verify(
        self,
        burn_proof_hash: str,
        parent_asset_id: str
    ) -> BurnProofVerificationResult:
        """
        Stub verification for development/testing.

        In production, this should NEVER be used.
        """
        # Simple validation: proof hash must be 64 hex chars
        if len(burn_proof_hash) != 64:
            return BurnProofVerificationResult(
                is_valid=False,
                proof_hash=burn_proof_hash,
                parent_asset_id=parent_asset_id,
                error="Invalid proof hash format"
            )

        try:
            int(burn_proof_hash, 16)
        except ValueError:
            return BurnProofVerificationResult(
                is_valid=False,
                proof_hash=burn_proof_hash,
                parent_asset_id=parent_asset_id,
                error="Invalid proof hash: not hexadecimal"
            )

        # Stub: Accept valid format proofs
        return BurnProofVerificationResult(
            is_valid=True,
            proof_hash=burn_proof_hash,
            parent_asset_id=parent_asset_id,
            material_recovery_pct=85.0,  # Stub value
            midnight_confirmed=False,
            verification_timestamp=datetime.utcnow()
        )

    async def generate_proof_request(
        self,
        asset_id: str,
        material_batch_id: str,
        dissolution_method: str
    ) -> dict:
        """
        Generate a burn proof request for a dissolution facility.

        This creates the request that a recycling facility uses
        to generate a Midnight ZK proof.

        Args:
            asset_id: Asset being dissolved
            material_batch_id: Material batch being recycled
            dissolution_method: Method of dissolution

        Returns:
            Dict with proof request parameters
        """
        # Create deterministic request ID
        request_input = f"{asset_id}{material_batch_id}{dissolution_method}"
        request_id = hashlib.sha256(request_input.encode()).hexdigest()[:32]

        return {
            "request_id": request_id,
            "asset_id": asset_id,
            "material_batch_id": material_batch_id,
            "dissolution_method": dissolution_method,
            "midnight_contract": "brandme_burn_proof_v1",
            "required_inputs": [
                "asset_authenticity_hash",
                "material_signature_hash",
                "dissolution_timestamp",
                "facility_id",
                "recovery_percentage"
            ],
            "created_at": datetime.utcnow().isoformat()
        }
