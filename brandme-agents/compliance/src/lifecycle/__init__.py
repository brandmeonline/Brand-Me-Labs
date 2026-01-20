"""
Brand.Me v9 — DPP Lifecycle State Machine
==========================================

Implements the Digital Product Passport (DPP) lifecycle for circular economy:

    PRODUCED → ACTIVE → REPAIR → DISSOLVE → REPRINT
         ↑                   ↓
         └───────────────────┘

Key features:
- State transition validation with Midnight burn proof for DISSOLVE→REPRINT
- ESG impact tracking for each transition
- Integration with Cardano for material certificates
"""

from .state_machine import (
    LifecycleState,
    LifecycleStateMachine,
    StateTransitionError,
    BurnProofRequiredError,
    DissolveAuthRequiredError,
)

from .burn_proof import (
    BurnProofVerifier,
    BurnProof,
)

from .esg_verifier import (
    ESGVerifier,
    ESGScore,
    ESGVerificationResult,
)

__all__ = [
    # State Machine
    "LifecycleState",
    "LifecycleStateMachine",
    "StateTransitionError",
    "BurnProofRequiredError",
    "DissolveAuthRequiredError",
    # Burn Proof
    "BurnProofVerifier",
    "BurnProof",
    # ESG
    "ESGVerifier",
    "ESGScore",
    "ESGVerificationResult",
]
