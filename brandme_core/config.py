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
from typing import Callable, Iterable, Mapping, Optional, Sequence


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
        """True in development mode. Raises ModeConfigurationError if BRANDME_MODE is unset."""
        return get_mode() is Mode.DEVELOPMENT

    @classmethod
    def is_production(cls) -> bool:
        """True in production mode. Raises ModeConfigurationError if BRANDME_MODE is unset."""
        return get_mode() is Mode.PRODUCTION


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


def resolve_environment(env: Optional[Mapping[str, str]] = None) -> str:
    """The process environment name, derived from BRANDME_MODE.

    BRANDME_MODE is the single mode source. ``ENVIRONMENT`` is accepted only as
    an echo for code that still reads it: when it is set it must equal
    BRANDME_MODE exactly, otherwise this raises. It never supplies a default.
    """
    env = os.environ if env is None else env
    mode = get_mode(env)
    echoed = env.get("ENVIRONMENT")
    if echoed is not None and echoed.strip() and echoed.strip() != mode.value:
        raise ModeConfigurationError(
            f"ENVIRONMENT={echoed.strip()!r} conflicts with BRANDME_MODE={mode.value!r}; "
            "BRANDME_MODE is the single mode source: unset ENVIRONMENT or set it to the same value"
        )
    return mode.value


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
    # Provider capability name from packages/provider-contracts/src/index.ts.
    TRYON_PHOTO = "tryon.photo"


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
# Inventory of trust-path fixtures that still exist in legacy service code.
#
# Each entry is a simulated adapter a service would serve today. A lane that
# replaces a fake with a verified adapter removes its entry here (or changes it
# to REAL/SANDBOX with evidence). Until then the service cannot boot in a
# strict mode. Full file:line inventory (dated 2026-10-05; its brandme-chain
# rows predate the Midnight adapter): docs/build/evidence/w00/trust-path-fixtures.md
#
# Foundation-era processes with no fabricated trust evidence are audited
# separately in AUDITED_PROCESSES below.
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
    # The decision endpoint (POST /governance/escalations/{scan_id}/decision) has
    # no authentication and writes the body's reviewer_user_id as AuditLog
    # human_approver_id: an unauthenticated human approval.
    "governance": (
        AdapterRegistration(
            TrustComponent.AUTH_IDENTITY, _SIM,
            "brandme-governance/governance_console/main.py resolve_escalation trusts body reviewer_user_id",
            "Simulated — the reviewer's identity is not authenticated",
        ),
    ),
}


# ---------------------------------------------------------------------------
# Audited foundation-era processes (read 2026-10-23 at the cited files;
# events_retention and consumer_domains read 2026-10-25).
#
# These processes fabricate no trust evidence. Their registrations describe
# what they actually serve, classified from the configuration they will run
# with, so a correctly configured strict-mode process is allowed and a
# misconfigured one is refused here as well as by its own config loader.
# Internal service boundaries (a per-service bearer credential plus a
# gateway-asserted X-Subject-Ref) are not registered as adapters; replacing
# that transport is the open PD-07 decision.
# ---------------------------------------------------------------------------

MIDNIGHT_TEST_NETWORKS: tuple[str, ...] = ("undeployed", "preview", "preprod")


@dataclass(frozen=True)
class AuditedProcess:
    """A process whose trust paths were read and classified, not assumed.

    ``environment_source`` names where the process reads ``ENVIRONMENT`` as its
    own mode; ``environment_default`` is what it falls back to when the
    variable is unset (``None``: it refuses to start). ``strict_refused_env``
    lists local-emulator variables the process's own loader refuses in
    sandbox/production; the guard refuses them there too.
    """

    summary: str
    registrations: Callable[[Mode, Mapping[str, str]], tuple[AdapterRegistration, ...]]
    environment_source: str = ""
    environment_default: Optional[str] = None
    strict_refused_env: tuple[str, ...] = ()


def _midnight_scope(env: Mapping[str, str], variable: str, implementation: str, evidence: str,
                    default: str = "") -> AdapterRegistration:
    raw = env.get(variable)
    # An empty value is invalid, not unset (brandme-chain's zod enum rejects it).
    network = (default if raw is None else raw).strip()
    if network in MIDNIGHT_TEST_NETWORKS:
        return AdapterRegistration(
            TrustComponent.CHAIN_MIDNIGHT, AdapterKind.SANDBOX,
            f"{implementation} [{variable}={network}]", evidence=evidence,
        )
    # Mainnet is not authorized in this build, and anything else is invalid.
    return AdapterRegistration(
        TrustComponent.CHAIN_MIDNIGHT, AdapterKind.UNCONFIGURED,
        f"{implementation} [{variable}={network or 'unset'} is not an authorized network]",
        required=True, evidence=evidence,
    )


_NO_PREPROD_EVIDENCE = (
    "No Preprod transaction, deployed contract address or finality evidence yet "
    "(docs/build/evidence/midnight-integration-2026-10-22.md:53)."
)


def _chain(mode: Mode, env: Mapping[str, str]) -> tuple[AdapterRegistration, ...]:
    return (
        _midnight_scope(
            env, "MIDNIGHT_NETWORK",
            "brandme-chain/src/midnight/adapter.ts RightsAdapter (Midnight.js providers, construction fails "
            "without them; no fallback), served read-only: capability.ts:58 writesAuthorized=false, "
            "network.ts assertWritable refuses Mainnet, reconciliation worker disabled on Mainnet (src/index.ts:46-47)",
            _NO_PREPROD_EVIDENCE, default="preprod",  # brandme-chain/src/config/index.ts:26
        ),
        AdapterRegistration(
            TrustComponent.CHAIN_CARDANO, AdapterKind.UNCONFIGURED,
            "brandme-chain/src/cardano/anchor.ts UnavailableCardanoAnchor (not mounted; the retired "
            "/tx/anchor-scan and /tx/verify-root return 410 at src/index.ts:57-63)",
            evidence="No verified Cardano submitter; anchoring reports unavailable.",
        ),
    )


def _read_api(mode: Mode, env: Mapping[str, str]) -> tuple[AdapterRegistration, ...]:
    return (
        _midnight_scope(
            env, "READ_API_NETWORK",
            "brandme_core/read_api/reads.py ReadService: read-only Spanner reads of persisted rights "
            "projections scoped to READ_API_NETWORK + READ_API_CONTRACT_ADDRESS (read_api/config.py:37-38); "
            "no chain calls, no Mainnet mode",
            _NO_PREPROD_EVIDENCE,
        ),
    )


def _privacy_exports(mode: Mode, env: Mapping[str, str]) -> tuple[AdapterRegistration, ...]:
    return (
        _midnight_scope(
            env, "EXPORT_NETWORK",
            "brandme_core/privacy_exports/service.py ExportService: selected-category exports of persisted "
            "rights records scoped to EXPORT_NETWORK + EXPORT_CONTRACT_ADDRESS (privacy_exports/config.py:35-36) "
            "into the private export bucket; no chain calls, no Mainnet mode",
            _NO_PREPROD_EVIDENCE,
        ),
    )


def _gateway(mode: Mode, env: Mapping[str, str]) -> tuple[AdapterRegistration, ...]:
    provider = (env.get("IDENTITY_PROVIDER") or "dev").strip()  # gateway config/index.ts:77 default 'dev'
    if provider != "oidc":
        return (
            AdapterRegistration(
                TrustComponent.AUTH_IDENTITY, AdapterKind.SIMULATED,
                f"brandme-gateway/src/routes/v1/index.ts POST /session/dev (IDENTITY_PROVIDER={provider})",
                # Same label the gateway sends (middleware/mode.ts DEV_IDENTITY_LABEL).
                "Simulated sign-in: fictional test identity, not a verified account",
            ),
        )
    issuer = (env.get("OIDC_ISSUER") or "").strip()
    audience = (env.get("OIDC_AUDIENCE") or "").strip()
    jwks = (env.get("OIDC_JWKS_URI") or "").strip()
    if not issuer.startswith("https://") or not audience or (jwks and not jwks.startswith("https://")):
        return (
            AdapterRegistration(
                TrustComponent.AUTH_IDENTITY, AdapterKind.UNCONFIGURED,
                "brandme-gateway/src/middleware/session.ts OIDC verifier without an https OIDC_ISSUER, an OIDC_AUDIENCE "
                "and (when set) an https OIDC_JWKS_URI",
                required=True,
            ),
        )
    return (
        AdapterRegistration(
            TrustComponent.AUTH_IDENTITY,
            AdapterKind.REAL if mode is Mode.PRODUCTION else AdapterKind.SANDBOX,
            "brandme-gateway/src/middleware/session.ts:83-88 jose jwtVerify against the issuer JWKS "
            "(issuer, audience, asymmetric algorithm allowlist)",
            evidence=(
                "The issuer's tenant (sandbox or production) is attested by deployment configuration; this "
                "guard checks its shape only. The gateway's own guard (middleware/mode.ts:58-65) also refuses "
                "JWT_SECRET, symmetric algorithms, a non-https OIDC_JWKS_URI and non-https PUBLIC_ORIGINS/CORS_ORIGINS."
            ),
        ),
    )


def _public_jwks_problem(raw: str) -> str:
    """Why ``raw`` is not a JWKS of public P-256 keys with a kid ('' when it is).

    The same shape DomainAssertionVerifier.from_jwks accepts
    (brandme_core/domains/persona/assertion.py:50-57); a private member is refused.
    """
    try:
        keys = json.loads(raw).get("keys") if raw.strip() else None
    except (ValueError, AttributeError):
        return "is not a JSON Web Key Set"
    if not isinstance(keys, list) or not keys:
        return "is unset or holds no keys"
    for jwk in keys:
        if not isinstance(jwk, dict) or jwk.get("kty") != "EC" or jwk.get("crv") != "P-256" or not jwk.get("kid"):
            return "holds a key that is not a P-256 key with a kid"
        if "d" in jwk:
            return "holds a private key (public keys only)"
    return ""


def _consumer_domains(mode: Mode, env: Mapping[str, str]) -> tuple[AdapterRegistration, ...]:
    issuer = (env.get("CONSUMER_DOMAIN_ASSERTION_ISSUER") or "").strip()
    jwks_problem = _public_jwks_problem(env.get("CONSUMER_DOMAIN_ASSERTION_JWKS") or "")
    verifier = ("brandme_core/domains/persona/assertion.py DomainAssertionVerifier: ES256 gateway principal assertions "
                "(kid, issuer, audience brandme:consumer-domains, lifetime <= 60 s, jti single-use within the process (in-memory cache; the chart runs one replica), environment)")
    if not issuer or jwks_problem:
        missing = "CONSUMER_DOMAIN_ASSERTION_ISSUER is unset" if not issuer else f"CONSUMER_DOMAIN_ASSERTION_JWKS {jwks_problem}"
        identity = AdapterRegistration(TrustComponent.AUTH_IDENTITY, AdapterKind.UNCONFIGURED, f"{verifier} [{missing}]",
                                       required=True)
    else:
        identity = AdapterRegistration(
            TrustComponent.AUTH_IDENTITY,
            AdapterKind.REAL if mode is Mode.PRODUCTION else AdapterKind.SANDBOX,
            verifier,
            evidence=(
                "The member is authenticated by the gateway (audited process 'gateway'); this service verifies "
                "only the gateway's signature over that principal and holds public keys only. The gateway signs "
                "with brandme-gateway/src/services/domains.ts; this guard checks the JWKS shape, not the key."
            ),
        )
    # brandme_core/domains/media/providers.py:94-101 (registry_from_environment).
    choice = (env.get("BRANDME_TRYON_PROVIDER") or "").strip()
    if choice == "simulated":
        tryon = AdapterRegistration(
            TrustComponent.TRYON_PHOTO, AdapterKind.SIMULATED,
            "brandme_core/domains/media/providers.py SimulatedTryOnProvider (BRANDME_TRYON_PROVIDER=simulated)",
            # The job label the service returns (media/service.py:161); results carry
            # generated_visual_preview_simulated (service.py:346).
            "Generated visual preview. Not a fit or size guarantee. Simulated provider.",
        )
    elif choice:
        tryon = AdapterRegistration(
            TrustComponent.TRYON_PHOTO, AdapterKind.UNCONFIGURED,
            f"brandme_core/domains/media/providers.py [BRANDME_TRYON_PROVIDER={choice!r} is not a known provider]",
            required=True,
        )
    else:
        tryon = AdapterRegistration(
            TrustComponent.TRYON_PHOTO, AdapterKind.UNCONFIGURED,
            "brandme_core/domains/media/providers.py: no approved provider; photo previews report "
            "photo_preview_not_configured",
            evidence="No try-on provider account, region or terms exist to verify an adapter against.",
        )
    return identity, tryon


def _no_trust_path(mode: Mode, env: Mapping[str, str]) -> tuple[AdapterRegistration, ...]:
    return ()


AUDITED_PROCESSES: Mapping[str, AuditedProcess] = {
    "chain": AuditedProcess(
        "Node Midnight rights service: capability report, operation status and read-only reconciliation.",
        _chain,
        environment_source="brandme-chain/src/config/index.ts:15,47 (ENVIRONMENT, zod default 'development')",
        environment_default="development",
    ),
    "read_api": AuditedProcess(
        "Authenticated rights and My Data read API (python -m brandme_core.read_api).",
        _read_api,
        environment_source="brandme_core/read_api/config.py:26 (must equal BRANDME_MODE)",
    ),
    "privacy_exports": AuditedProcess(
        "Selected-category export API and leased worker (python -m brandme_core.privacy_exports [--worker]).",
        _privacy_exports,
        environment_source="brandme_core/privacy_exports/config.py:24 (must equal BRANDME_MODE)",
    ),
    "events_worker": AuditedProcess(
        "Outbox publisher to pre-provisioned Pub/Sub topics (python -m brandme_core.events.worker); "
        "no wallet, chain submission, topic creation or application side effects (events/worker.py:1-5).",
        _no_trust_path,
        environment_source="brandme_core/events/worker.py:41 (must equal BRANDME_MODE)",
    ),
    "events_retention": AuditedProcess(
        "Outbox retention job (python -m brandme_core.events.retention): purges delivered outbox rows 7 days "
        "after delivery and re-erases deleted subjects' event and replay records; Spanner only, no Pub/Sub, "
        "wallet, chain submission or application side effects (events/retention.py:1-25).",
        _no_trust_path,
        environment_source="brandme_core/events/retention.py:244 (must equal BRANDME_MODE)",
    ),
    "consumer_domains": AuditedProcess(
        "Consumer-domain HTTP service (python -m brandme_core.domains.persona.app): persona, wardrobe, social and "
        "rewards routers behind the gateway's ES256 principal assertion; /ops routers unmounted. Spanner via "
        "SPANNER_* only: the emulator is required in demo/development and refused in sandbox/production "
        "(persona/app.py:91-92). Media and try-on routes mount only with the optional BRANDME_MEDIA_BUCKET "
        "(media/gcs_store.py:325-349: storage emulator refused in strict modes, bucket policy checked). It never "
        "calls a try-on provider (the jobs process does), a wallet or a chain.",
        _consumer_domains,
        environment_source="brandme_core/domains/persona/app.py:88-90 (must equal BRANDME_MODE)",
        strict_refused_env=("SPANNER_EMULATOR_HOST", "STORAGE_EMULATOR_HOST"),
    ),
    "gateway": AuditedProcess(
        "Node API gateway. Its trust-path component is member identity; it also runs its own guard "
        "(brandme-gateway/src/middleware/mode.ts). The legacy /scan route is a placeholder, not trust evidence.",
        _gateway,
    ),
}


def canonical_service(service: str) -> str:
    """``read-api`` and ``read_api`` name the same process."""
    return service.strip().lower().replace("-", "_")


def service_registrations(
    service: str, mode: Mode, env: Optional[Mapping[str, str]] = None
) -> Optional[tuple[AdapterRegistration, ...]]:
    """The audited registrations for ``service`` in ``mode``; ``None`` if unaudited."""
    env = os.environ if env is None else env
    name = canonical_service(service)
    if name in LEGACY_SIMULATED_ADAPTERS:
        return tuple(LEGACY_SIMULATED_ADAPTERS[name])
    if name in AUDITED_PROCESSES:
        return AUDITED_PROCESSES[name].registrations(mode, env)
    return None


def _environment_echo_violations(service: str, mode: Mode, env: Mapping[str, str]) -> list[str]:
    process = AUDITED_PROCESSES.get(canonical_service(service))
    if process is None or not process.environment_source:
        return []
    raw = (env.get("ENVIRONMENT") or "").strip()
    if (raw or process.environment_default) == mode.value:
        return []
    # A set-but-different value was already rejected by resolve_environment().
    if process.environment_default:
        state = f"ENVIRONMENT is unset, so {service} would run as {process.environment_default!r}"
    else:
        state = f"ENVIRONMENT is unset and {service} refuses to start without it"
    return [f"{state} ({process.environment_source}); set ENVIRONMENT={mode.value}"]


def _strict_env_violations(service: str, mode: Mode, env: Mapping[str, str]) -> list[str]:
    process = AUDITED_PROCESSES.get(canonical_service(service))
    if process is None or not mode.is_strict:
        return []
    return [f"{name} points at a local emulator; {service} uses real services in {mode.value}"
            for name in process.strict_refused_env if str(env.get(name, "")).strip()]


def enforce_boot_guard(
    service: str,
    registrations: Optional[Iterable[AdapterRegistration]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Mode:
    """Raise if ``service`` may not boot in the current mode.

    Raises ModeConfigurationError when BRANDME_MODE is missing or invalid, or
    when ENVIRONMENT contradicts it, and TrustPathViolation when the process
    would serve a disallowed adapter. ``registrations`` defaults to the
    service's inventory entry (legacy or audited). Unknown services in a strict
    mode are rejected: an unaudited process is not evidence of a real adapter.
    """
    env = os.environ if env is None else env
    mode = get_mode(env)
    resolve_environment(env)
    violations = check_legacy_flags(mode, env)
    violations.extend(_environment_echo_violations(service, mode, env))
    violations.extend(_strict_env_violations(service, mode, env))
    if registrations is None:
        registrations = service_registrations(service, mode, env)
        if registrations is None:
            if mode.is_strict:
                violations.append(f"service {service!r} has no audited trust-path inventory")
            registrations = ()
    violations.extend(check_registrations(mode, registrations))
    if violations:
        raise TrustPathViolation(mode, violations)
    return mode


def simulation_labels(service: str, env: Optional[Mapping[str, str]] = None) -> list[dict]:
    """Labels a demo/development surface must display for ``service``."""
    env = os.environ if env is None else env
    name = canonical_service(service)
    regs: Iterable[AdapterRegistration] = ()
    if name in LEGACY_SIMULATED_ADAPTERS:
        regs = LEGACY_SIMULATED_ADAPTERS[name]
    elif name in AUDITED_PROCESSES:
        regs = AUDITED_PROCESSES[name].registrations(get_mode(env), env)
    return [
        {"component": r.component.value, "label": r.simulation_label, "implementation": r.implementation}
        for r in regs
        if r.kind is AdapterKind.SIMULATED
    ]


def _registration_json(reg: AdapterRegistration) -> dict:
    return {**asdict(reg), "component": reg.component.value, "kind": reg.kind.value}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brandme_core.config")
    sub = parser.add_subparsers(dest="cmd", required=True)
    pre = sub.add_parser("preflight", help="fail closed before a service boots")
    pre.add_argument("--service", required=True)
    sub.add_parser("inventory", help="print the trust-path inventory as JSON "
                                     "(audited processes are evaluated for the current environment)")
    args = parser.parse_args(argv)

    if args.cmd == "inventory":
        out: dict = {svc: [_registration_json(r) for r in regs] for svc, regs in LEGACY_SIMULATED_ADAPTERS.items()}
        try:
            mode: Optional[Mode] = get_mode()
        except ModeConfigurationError:
            mode = None
        for svc, process in AUDITED_PROCESSES.items():
            out[svc] = {
                "summary": process.summary,
                "environment_source": process.environment_source,
                "registrations": ([_registration_json(r) for r in process.registrations(mode, os.environ)]
                                  if mode else "set BRANDME_MODE to evaluate"),
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
