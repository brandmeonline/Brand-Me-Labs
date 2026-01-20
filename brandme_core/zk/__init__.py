"""
Brand.Me v9 — Zero-Knowledge Proof Module
==========================================

ZK proofs for privacy-preserving ownership verification.
Used by AR glasses to verify asset ownership without exposing private keys.
"""

from brandme_core.zk.proof_of_ownership import (
    ProofOfOwnership,
    ProofRequest,
    ProofResponse,
    ProofVerificationResult,
    ZKProofManager,
)

__all__ = [
    "ProofOfOwnership",
    "ProofRequest",
    "ProofResponse",
    "ProofVerificationResult",
    "ZKProofManager",
]
