# brandme_core/config.py
"""
Centralized configuration management for Brand.Me services.

Two layers live here:

1. ``ServiceConfig`` — legacy connection settings (Spanner, Firestore, service
   URLs). Kept read-compatible for existing callers.
2. Build modes (``BRANDME_MODE``) and the trust-path boot guard required by
   docs/design/brandme/06-delivery-verification.md (W00) and README "Build modes".

Modes:
    demo         deterministic fictional fixtures; every simulated adapter is
                 visibly labelled
    development  real domain logic against emulators + deterministic adapters
    sandbox      authorized partner sandboxes / Midnight Preprod; no simulation
                 in the trust path
    production   approved providers only; no stub fallback anywhere in the
                 trust path

Production and sandbox fail closed: a process that would serve a simulated
trust-path adapter (fake chain hash, fake proof, constant ESG value, fake
commerce ID, default reprint eligibility, auth shortcut) refuses to boot.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable, Mapping, Optional, Sequence


class ServiceConfig:
    """Base configuration for all Brand.Me services."""

    # Spanner Configuration (v8)
    SPANNER_PROJECT_ID: str = os.getenv("SPANNER_PROJECT_ID", "test-project")
    SPANNER_INSTANCE_ID: str = os.getenv("SPANNER_INSTANCE_ID", "brandme-instance")
    SPANNER_DATABASE_ID: str = os.getenv("SPANNER_DATABASE_ID", "brandme-db")
    SPANNER_POOL_SIZE: int = int(os.getenv("SPANNER_POOL_SIZE", "10"))
    SPANNER_MAX_SESSIONS: int = int(os.getenv("SPANNER_MAX_SESSIONS", "100"))

    # Firestore Configuration (v8)
    FIRESTORE_PROJECT_ID: str = os.getenv("FIRESTORE_PROJECT_ID", "test-project")

    # HTTP Client Configuration
    HTTP_TIMEOUT: int = int(os.getenv("HTTP_TIMEOUT", "30"))
    HTTP_MAX_RETRIES: int = int(os.getenv("HTTP_MAX_RETRIES", "3"))
    HTTP_RETRY_BACKOFF: float = float(os.getenv("HTTP_RETRY_BACKOFF", "0.5"))
    HTTP_POOL_CONNECTIONS: int = int(os.getenv("HTTP_POOL_CONNECTIONS", "10"))
    HTTP_POOL_MAXSIZE: int = int(os.getenv("HTTP_POOL_MAXSIZE", "20"))

    # Service URLs
    BRAIN_SERVICE_URL: str = os.getenv("BRAIN_SERVICE_URL", "http://brain:8000")
    POLICY_SERVICE_URL: str = os.getenv("POLICY_SERVICE_URL", "http://policy:8001")
    ORCHESTRATOR_SERVICE_URL: str = os.getenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator:8002")
    KNOWLEDGE_SERVICE_URL: str = os.getenv("KNOWLEDGE_SERVICE_URL", "http://knowledge:8003")
    COMPLIANCE_SERVICE_URL: str = os.getenv("COMPLIANCE_SERVICE_URL", "http://compliance:8004")
    IDENTITY_SERVICE_URL: str = os.getenv("IDENTITY_SERVICE_URL", "http://identity:8005")
    GOVERNANCE_SERVICE_URL: str = os.getenv("GOVERNANCE_SERVICE_URL", "http://governance:8006")
    CUBE_SERVICE_URL: str = os.getenv("CUBE_SERVICE_URL", "http://cube:8007")

    # Service Behavior. Stub mode is now opt-in (was default "true"); the mode
    # guard below rejects it outright in sandbox/production.
    ENABLE_STUB_MODE: bool = os.getenv("ENABLE_STUB_MODE", "false").lower() == "true"
    ENABLE_STRICT_VALIDATION: bool = os.getenv("ENABLE_STRICT_VALIDATION", "false").lower() == "true"

    # CORS Configuration
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:*,http://localhost:3000").split(",")

    @classmethod
    def get_spanner_config(cls) -> dict:
        """Returns Spanner connection configuration."""
        return {
            "project_id": cls.SPANNER_PROJECT_ID,
            "instance_id": cls.SPANNER_INSTANCE_ID,
            "database_id": cls.SPANNER_DATABASE_ID,
        }

    @classmethod
    def is_development(cls) -> bool:
        """Returns True if running in development mode."""
        return get_mode(default=Mode.DEVELOPMENT) is Mode.DEVELOPMENT

    @classmethod
    def is_production(cls) -> bool:
        """Returns True if running in production mode."""
        return get_mode(default=Mode.DEVELOPMENT) is Mode.PRODUCTION


# ---------------------------------------------------------------------------
# Build modes
# ---------------------------------------------------------------------------


class Mode(str, Enum):
    DEMO = "demo"
    DEVELOPMENT = "development"
    SANDBOX = "sandbox"
    PRODUCTION = "production"

    @property
    def is_strict(self) -> bool:
        """Strict modes forbid any simulated adapter in the trust path."""
        return self in (Mode.SANDBOX, Mode.PRODUCTION)


class ModeConfigurationError(RuntimeError):
    """BRANDME_MODE is missing or invalid."""


class TrustPathViolation(RuntimeError):
    """A strict mode would serve a simulated or unconfigured trust-path adapter."""

    def __init__(self, mode: Mode, violations: Sequence[str]):
        self.mode = mode
        self.violations = list(violations)
        super().__init__(
            f"BRANDME_MODE={mode.value} refuses to boot; trust-path violations: "
            + "; ".join(self.violations)
        )


def get_mode(env: Optional[Mapping[str, str]] = None, default: Optional[Mode] = None) -> Mode:
    """Resolve BRANDME_MODE. There is no implicit default unless the caller passes one."""
    env = os.environ if env is None else env
    raw = (env.get("BRANDME_MODE") or "").strip().lower()
    if not raw:
        if default is not None:
            return default
        raise ModeConfigurationError(
            "BRANDME_MODE is not set; choose one of demo, development, sandbox, production"
        )
    try:
        return Mode(raw)
    except ValueError as exc:
        raise ModeConfigurationError(
            f"BRANDME_MODE={raw!r} is invalid; choose one of demo, development, sandbox, production"
        ) from exc


class TrustComponent(str, Enum):
    """Trust-path capabilities that must never be faked in a strict mode."""

    CHAIN_CARDANO = "chain.cardano"
    CHAIN_MIDNIGHT = "chain.midnight"
    PROOF_OWNERSHIP = "proof.ownership"
    ESG_ORACLE = "esg.oracle"
    COMMERCE_CHECKOUT = "commerce.checkout"
    COMMERCE_MANDATE = "commerce.mandate"
    RIGHTS_REPRINT = "rights.reprint"
    AUTH_IDENTITY = "auth.identity"


class AdapterKind(str, Enum):
    REAL = "real"              # production provider, verified
    SANDBOX = "sandbox"        # authorized partner sandbox / test network
    SIMULATED = "simulated"    # deterministic fixture; demo/development only
    UNCONFIGURED = "unconfigured"  # capability unavailable; must not be offered


ALLOWED_KINDS: Mapping[Mode, frozenset] = {
    Mode.DEMO: frozenset({AdapterKind.SIMULATED, AdapterKind.UNCONFIGURED, AdapterKind.SANDBOX}),
    Mode.DEVELOPMENT: frozenset({AdapterKind.SIMULATED, AdapterKind.UNCONFIGURED, AdapterKind.SANDBOX}),
    Mode.SANDBOX: frozenset({AdapterKind.SANDBOX, AdapterKind.UNCONFIGURED}),
    Mode.PRODUCTION: frozenset({AdapterKind.REAL, AdapterKind.UNCONFIGURED}),
}


@dataclass(frozen=True)
class AdapterRegistration:
    """A trust-path implementation a process would serve.

    ``required`` means the process cannot do its job with the capability
    unconfigured (e.g. production identity). ``simulation_label`` is the
    user-visible label demo/development surfaces must render.
    """

    component: TrustComponent
    kind: AdapterKind
    implementation: str
    simulation_label: str = ""
    required: bool = False
    evidence: str = ""


def check_registrations(mode: Mode, registrations: Iterable[AdapterRegistration]) -> list[str]:
    """Return violations (empty list means the boot is allowed)."""
    violations: list[str] = []
    for reg in registrations:
        where = f"{reg.component.value} via {reg.implementation}"
        if reg.kind not in ALLOWED_KINDS[mode]:
            violations.append(f"{where} is {reg.kind.value}, not allowed in {mode.value}")
            continue
        if reg.kind is AdapterKind.SIMULATED and not reg.simulation_label.strip():
            violations.append(f"{where} is simulated without a visible simulation label")
        if reg.kind is AdapterKind.UNCONFIGURED and reg.required and mode.is_strict:
            violations.append(f"{where} is required but unconfigured")
    return violations


# Process-level legacy switches that turn on success-shaped fallbacks.
LEGACY_STUB_FLAGS: tuple[str, ...] = (
    "ENABLE_STUB_MODE",
    "MIDNIGHT_FALLBACK_MODE",
    "CARDANO_FALLBACK_MODE",
    "ZK_ALLOW_STUB_FALLBACK",
    "ALLOW_STUB_FALLBACK",
)


def check_legacy_flags(mode: Mode, env: Optional[Mapping[str, str]] = None) -> list[str]:
    env = os.environ if env is None else env
    if not mode.is_strict:
        return []
    return [
        f"{flag}={env[flag]!r} enables a stub fallback"
        for flag in LEGACY_STUB_FLAGS
        if str(env.get(flag, "")).strip().lower() in {"1", "true", "yes", "on"}
    ]


# ---------------------------------------------------------------------------
# Inventory of trust-path fixtures that still exist in service code.
#
# Each entry is a simulated adapter a service would serve today. A lane that
# replaces a fake with a verified adapter removes its entry here (or changes it
# to REAL/SANDBOX with evidence). Until then the service cannot boot in a
# strict mode. Full file:line inventory: docs/build/evidence/w00/trust-path-fixtures.md
# ---------------------------------------------------------------------------

_SIM = AdapterKind.SIMULATED

LEGACY_SIMULATED_ADAPTERS: Mapping[str, tuple[AdapterRegistration, ...]] = {
    "brain": (
        AdapterRegistration(
            TrustComponent.CHAIN_CARDANO, _SIM, "brandme-core/brain/main.py call_orchestrator_commit fallback",
            "Simulated — no blockchain transaction was made",
        ),
    ),
    "orchestrator": (
        AdapterRegistration(
            TrustComponent.CHAIN_CARDANO, _SIM, "brandme-core/orchestrator/main.py cardano_tx_ string",
            "Simulated — no Cardano transaction was made",
        ),
        AdapterRegistration(
            TrustComponent.CHAIN_MIDNIGHT, _SIM, "brandme-core/orchestrator/worker.py stub tx hashes",
            "Simulated — no Midnight transaction was made",
        ),
    ),
    "identity": (
        AdapterRegistration(
            TrustComponent.PROOF_OWNERSHIP, _SIM, "brandme_core/zk/proof_of_ownership.py hash/JSON proof",
            "Simulated — not a zero-knowledge proof",
        ),
        AdapterRegistration(
            TrustComponent.AUTH_IDENTITY, _SIM, "brandme-agents/identity/src/main.py path user_id, synthetic trust_score",
            "Simulated — caller identity is not authenticated",
        ),
    ),
    "compliance": (
        AdapterRegistration(
            TrustComponent.ESG_ORACLE, _SIM, "brandme-agents/compliance constant ESG threshold/scores",
            "Simulated — ESG values are not verified claims",
        ),
        AdapterRegistration(
            TrustComponent.CHAIN_MIDNIGHT, _SIM, "brandme-agents/compliance burn-proof stub",
            "Simulated — no Midnight burn proof exists",
        ),
    ),
    "cube": (
        AdapterRegistration(
            TrustComponent.RIGHTS_REPRINT, _SIM, "brandme_core/firestore/wardrobe.py default reprint eligibility",
            "Simulated — reprint rights are not verified",
        ),
        AdapterRegistration(
            TrustComponent.ESG_ORACLE, _SIM, "brandme-cube/src ESG/molecular fixture values",
            "Simulated — ESG values are not verified claims",
        ),
    ),
    "mcp": (
        AdapterRegistration(
            TrustComponent.COMMERCE_MANDATE, _SIM, "brandme_core/mcp/tools.py ap2.* mandate UUIDs",
            "Simulated — not an AP2 mandate",
        ),
        AdapterRegistration(
            TrustComponent.COMMERCE_CHECKOUT, _SIM, "brandme_core/mcp/tools.py checkout completion",
            "Simulated — no merchant order was placed",
        ),
        AdapterRegistration(
            TrustComponent.AUTH_IDENTITY, _SIM, "brandme_core/mcp/tools.py executor trusts user_id argument",
            "Simulated — caller identity is not authenticated",
        ),
    ),
    "chain": (
        AdapterRegistration(
            TrustComponent.CHAIN_MIDNIGHT, _SIM, "brandme-chain/src/services/midnight-client.ts mock client",
            "Simulated — no Midnight transaction was made",
        ),
        AdapterRegistration(
            TrustComponent.CHAIN_CARDANO, _SIM, "brandme-chain/src/services/cardano-tx-builder.ts fallback",
            "Simulated — no Cardano transaction was made",
        ),
    ),
    # Services with no known trust-path fakes still go through the flag check.
    "policy": (
        AdapterRegistration(
            TrustComponent.AUTH_IDENTITY, _SIM, "brandme-core/policy/main.py canViewFace/canTransferOwnership trust payload IDs",
            "Simulated — ownership and viewer identity are not verified",
        ),
    ),
    "knowledge": (
        AdapterRegistration(
            TrustComponent.ESG_ORACLE, _SIM, "brandme-agents/knowledge/src/main.py constant passport facets",
            "Simulated — sustainability and origin facts are fixtures",
        ),
    ),
    # No trust-path fabrication found in the governance console (escalation listing only).
    "governance": (),
}


def enforce_boot_guard(
    service: str,
    registrations: Optional[Iterable[AdapterRegistration]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Mode:
    """Raise TrustPathViolation if ``service`` may not boot in the current mode.

    ``registrations`` defaults to the service's legacy inventory entry. Unknown
    services in a strict mode are rejected: an unaudited process is not
    evidence of a real adapter.
    """
    mode = get_mode(env)
    violations = check_legacy_flags(mode, env)
    if registrations is None:
        if service not in LEGACY_SIMULATED_ADAPTERS:
            if mode.is_strict:
                violations.append(f"service {service!r} has no audited trust-path inventory")
            registrations = ()
        else:
            registrations = LEGACY_SIMULATED_ADAPTERS[service]
    violations.extend(check_registrations(mode, registrations))
    if violations:
        raise TrustPathViolation(mode, violations)
    return mode


def simulation_labels(service: str) -> list[dict]:
    """Labels a demo/development surface must display for ``service``."""
    return [
        {"component": r.component.value, "label": r.simulation_label, "implementation": r.implementation}
        for r in LEGACY_SIMULATED_ADAPTERS.get(service, ())
        if r.kind is AdapterKind.SIMULATED
    ]


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brandme_core.config")
    sub = parser.add_subparsers(dest="cmd", required=True)
    pre = sub.add_parser("preflight", help="fail closed before a service boots")
    pre.add_argument("--service", required=True)
    sub.add_parser("inventory", help="print the trust-path inventory as JSON")
    args = parser.parse_args(argv)

    if args.cmd == "inventory":
        out = {
            svc: [{**asdict(r), "component": r.component.value, "kind": r.kind.value} for r in regs]
            for svc, regs in LEGACY_SIMULATED_ADAPTERS.items()
        }
        print(json.dumps(out, indent=2))
        return 0

    try:
        mode = enforce_boot_guard(args.service)
    except (ModeConfigurationError, TrustPathViolation) as exc:
        print(f"[brandme preflight] {args.service}: REFUSED — {exc}", file=sys.stderr)
        return 3
    labels = simulation_labels(args.service)
    print(f"[brandme preflight] {args.service}: allowed in {mode.value}; simulated adapters: {len(labels)}")
    for item in labels:
        print(f"  - {item['component']}: {item['label']}")
    return 0


# Singleton instance
config = ServiceConfig()


if __name__ == "__main__":
    sys.exit(_main())
