"""Server-owned provider registry and effective capabilities (ch.05 §1, §8).

"Configured" is not "verified": a capability becomes ``verified`` only through
``record_verification`` with evidence of the exact capability exercised. A host
reachability check never verifies anything beyond reachability.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .contracts import CAPABILITIES, CAPABILITY_STATES, EXECUTABLE_STATES

# Evidence kinds that can justify each state.
VERIFYING_EVIDENCE = frozenset({"sandbox_operation", "production_operation", "conformance_suite"})


class RegistryError(ValueError):
    pass


class SimulationInProductionError(RuntimeError):
    """Boot guard: simulation adapters are never allowed outside demo/development."""


@dataclass(frozen=True)
class CapabilityStatus:
    name: str
    state: str
    reason_code: str
    last_checked_at: Optional[datetime] = None
    evidence_ref: Optional[str] = None
    evidence_kind: Optional[str] = None

    def __post_init__(self) -> None:
        if self.name not in CAPABILITIES:
            raise RegistryError(f"unknown capability {self.name}")
        if self.state not in CAPABILITY_STATES:
            raise RegistryError(f"unknown capability state {self.state}")
        if self.state == "verified" and (
            not self.evidence_ref or self.last_checked_at is None
            or self.evidence_kind not in VERIFYING_EVIDENCE
        ):
            raise RegistryError("verified requires current operation/conformance evidence")

    def to_public(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "reason_code": self.reason_code,
            "last_checked_at": self.last_checked_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.last_checked_at else None,
            "evidence_ref": self.evidence_ref,
        }


@dataclass
class ProviderConnection:
    provider_id: str
    display_name: str
    environment: str
    simulation: bool  # True for deterministic local/demo adapters
    country_codes: Tuple[str, ...]
    disclosure: str
    capabilities: Dict[str, CapabilityStatus]
    access_level: str = "unconfigured"  # provider-specific (e.g. link_only, approved_publisher)
    operator_account_ref: Optional[str] = None  # server-only
    credential_ref: Optional[str] = None  # Secret Manager reference; never a secret value
    data_use: Mapping[str, bool] = field(default_factory=dict)  # e.g. {"display_images": False}
    allowed_redirect_hosts: Tuple[str, ...] = ()
    adapter: Any = None  # server-only adapter instance
    protocols: Mapping[str, str] = field(default_factory=dict)  # e.g. {"ap2": "0.2"} only when verified/simulated
    merchant_public_keys: Mapping[str, Any] = field(default_factory=dict)  # merchant_id -> checkout JWT key
    version: int = 1

    def capability(self, name: str) -> CapabilityStatus:
        if name not in CAPABILITIES:
            raise RegistryError(f"unknown capability {name}")
        return self.capabilities.get(
            name, CapabilityStatus(name, "unsupported", "not_offered_by_provider"))

    def can_execute(self, name: str) -> bool:
        return self.capability(name).state in EXECUTABLE_STATES

    def to_public(self) -> Dict[str, Any]:
        """Sanitized ``ProviderPublic`` DTO: no credentials, accounts or contracts."""
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "environment": self.environment,
            "capabilities": [self.capabilities[k].to_public() for k in sorted(self.capabilities)],
            "country_codes": list(self.country_codes),
            "disclosure": self.disclosure,
        }


class ProviderRegistry:
    def __init__(self, environment: str):
        self.environment = environment
        self._lock = threading.RLock()
        self._connections: Dict[str, ProviderConnection] = {}

    def register(self, connection: ProviderConnection) -> None:
        if connection.environment != self.environment:
            raise RegistryError("connection environment does not match registry environment")
        if connection.simulation and self.environment not in ("demo", "development"):
            raise SimulationInProductionError(
                f"simulation provider {connection.provider_id} refused in {self.environment}")
        with self._lock:
            if connection.provider_id in self._connections:
                raise RegistryError(f"duplicate provider {connection.provider_id}")
            self._connections[connection.provider_id] = connection

    def get(self, provider_id: str) -> ProviderConnection:
        with self._lock:
            try:
                return self._connections[provider_id]
            except KeyError:
                raise RegistryError(f"unknown provider {provider_id}") from None

    def all(self) -> List[ProviderConnection]:
        with self._lock:
            return list(self._connections.values())

    def set_capability(self, provider_id: str, status: CapabilityStatus) -> None:
        with self._lock:
            conn = self.get(provider_id)
            conn.capabilities[status.name] = status
            conn.version += 1

    def record_verification(self, provider_id: str, capability: str, *, evidence_ref: str,
                            evidence_kind: str, checked_at: datetime) -> CapabilityStatus:
        conn = self.get(provider_id)
        if conn.simulation:
            # A fixture proves app behavior, not a provider relationship.
            state, reason = "sandbox", "deterministic_local_simulation"
        elif evidence_kind not in VERIFYING_EVIDENCE:
            raise RegistryError(f"{evidence_kind} cannot verify {capability}")
        elif conn.environment == "production" and evidence_kind == "production_operation":
            state, reason = "verified", "verified_by_production_evidence"
        else:
            # Sandbox runs and conformance suites prove the sandbox path, not live access.
            state, reason = "sandbox", "sandbox_evidence"
        status = CapabilityStatus(capability, state, reason, checked_at, evidence_ref, evidence_kind)
        self.set_capability(provider_id, status)
        return status

    def suspend(self, provider_id: str, capability: str, reason_code: str, at: datetime) -> None:
        current = self.get(provider_id).capability(capability)
        self.set_capability(provider_id, replace(
            current, state="suspended", reason_code=reason_code, last_checked_at=at))

    def effective(self, provider_id: str, capability: str, *, country_code: Optional[str] = None,
                  consent: bool = True) -> Tuple[bool, str]:
        """Intersection of provider capability, consent and geography (subset of ch.05 §1)."""
        conn = self.get(provider_id)
        status = conn.capability(capability)
        if status.state not in EXECUTABLE_STATES:
            return False, status.reason_code
        if not consent:
            return False, "consent_required"
        if country_code and country_code not in conn.country_codes:
            return False, "geography_unavailable"
        return True, status.state
