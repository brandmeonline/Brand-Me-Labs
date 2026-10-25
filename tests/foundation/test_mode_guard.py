"""Mode guard: strict modes fail closed on trust-path simulation (BM-BASE-002)."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from brandme_core.boot import guard
from brandme_core.config import (
    AUDITED_PROCESSES,
    LEGACY_SIMULATED_ADAPTERS,
    AdapterKind,
    AdapterRegistration,
    Mode,
    ModeConfigurationError,
    ServiceConfig,
    TrustComponent,
    TrustPathViolation,
    check_registrations,
    enforce_boot_guard,
    get_mode,
    resolve_environment,
    service_registrations,
    simulation_labels,
)

REPO = Path(__file__).resolve().parents[2]

LEGACY_FAKES = ["orchestrator", "mcp", "identity", "compliance", "cube", "brain", "policy", "knowledge", "governance"]


def _jwk(key, kid="k-1"):
    """A JWK generated at runtime (nothing is stored); a private key keeps its ``d``."""
    return {**json.loads(ECAlgorithm.to_jwk(key)), "kid": kid}


PUBLIC_JWKS = json.dumps({"keys": [_jwk(ec.generate_private_key(ec.SECP256R1()).public_key())]})

# What a correctly configured sandbox deployment of each audited process sets
# (no credentials: the shared guard does not read them).
CONFIGURED = {
    "chain": {"MIDNIGHT_NETWORK": "preprod"},
    "read_api": {"READ_API_NETWORK": "preprod"},
    "read-api": {"READ_API_NETWORK": "preview"},
    "privacy_exports": {"EXPORT_NETWORK": "preprod"},
    "privacy-exports": {"EXPORT_NETWORK": "undeployed"},
    "events_worker": {},
    "events-worker": {},
    "events_retention": {},
    "gateway": {"IDENTITY_PROVIDER": "oidc", "OIDC_ISSUER": "https://issuer.example.test", "OIDC_AUDIENCE": "brandme-api"},
    # brandme_core/domains/persona/app.py _config: Spanner ids plus the assertion issuer and public JWKS.
    "consumer_domains": {"SPANNER_PROJECT_ID": "p", "SPANNER_INSTANCE_ID": "i", "SPANNER_DATABASE_ID": "d",
                         "CONSUMER_DOMAIN_ASSERTION_ISSUER": "brandme-gateway", "CONSUMER_DOMAIN_ASSERTION_JWKS": PUBLIC_JWKS},
    "consumer-domains": {"CONSUMER_DOMAIN_ASSERTION_ISSUER": "brandme-gateway", "CONSUMER_DOMAIN_ASSERTION_JWKS": PUBLIC_JWKS,
                         "BRANDME_MEDIA_BUCKET": "brandme-sandbox-media-x"},
}


def _env(mode, **extra):
    return {"BRANDME_MODE": mode, **extra}


def _configured(service, mode, **extra):
    env = {"BRANDME_MODE": mode, **CONFIGURED[service], **extra}
    if service != "gateway":
        env.setdefault("ENVIRONMENT", mode)
    return env


def test_mode_is_required_and_validated():
    with pytest.raises(ModeConfigurationError):
        get_mode({})
    with pytest.raises(ModeConfigurationError):
        get_mode({"BRANDME_MODE": "prod"})
    assert get_mode({"BRANDME_MODE": " Production "}) is Mode.PRODUCTION


def test_legacy_service_config_has_no_implicit_development_default(monkeypatch):
    monkeypatch.delenv("BRANDME_MODE", raising=False)
    with pytest.raises(ModeConfigurationError):
        ServiceConfig.is_development()
    with pytest.raises(ModeConfigurationError):
        ServiceConfig.is_production()
    monkeypatch.setenv("BRANDME_MODE", "production")
    assert ServiceConfig.is_production() and not ServiceConfig.is_development()


@pytest.mark.parametrize("service", LEGACY_FAKES)
@pytest.mark.parametrize("mode", ["production", "sandbox"])
def test_strict_modes_refuse_services_with_fake_trust_paths(service, mode):
    with pytest.raises(TrustPathViolation) as exc:
        enforce_boot_guard(service, env=_env(mode))
    assert exc.value.violations, "a refusal must name the fake"
    assert all("simulated, not allowed" in v for v in exc.value.violations)


@pytest.mark.parametrize("service", sorted(LEGACY_SIMULATED_ADAPTERS))
@pytest.mark.parametrize("mode", ["demo", "development"])
def test_local_modes_allow_labelled_simulation(service, mode):
    assert enforce_boot_guard(service, env=_env(mode)).value == mode


def test_every_legacy_adapter_is_a_labelled_simulation():
    for regs in LEGACY_SIMULATED_ADAPTERS.values():
        assert regs, "a legacy entry without a fake belongs in AUDITED_PROCESSES"
        for reg in regs:
            assert reg.kind is AdapterKind.SIMULATED
            assert reg.simulation_label.startswith("Simulated")


def test_unlabelled_simulation_is_rejected_even_in_demo():
    reg = AdapterRegistration(TrustComponent.CHAIN_MIDNIGHT, AdapterKind.SIMULATED, "x")
    assert check_registrations(Mode.DEMO, [reg])


def test_production_rejects_sandbox_and_required_unconfigured():
    sandbox = AdapterRegistration(TrustComponent.CHAIN_MIDNIGHT, AdapterKind.SANDBOX, "preprod")
    missing = AdapterRegistration(TrustComponent.AUTH_IDENTITY, AdapterKind.UNCONFIGURED, "oidc", required=True)
    real = AdapterRegistration(TrustComponent.AUTH_IDENTITY, AdapterKind.REAL, "oidc")
    assert check_registrations(Mode.PRODUCTION, [sandbox])
    assert check_registrations(Mode.PRODUCTION, [missing])
    assert check_registrations(Mode.PRODUCTION, [real]) == []


@pytest.mark.parametrize("flag", ["ENABLE_STUB_MODE", "MIDNIGHT_FALLBACK_MODE", "CARDANO_FALLBACK_MODE"])
def test_legacy_stub_flags_refused_in_production_even_for_clean_service(flag):
    clean = {"ENVIRONMENT": "production"}
    with pytest.raises(TrustPathViolation):
        enforce_boot_guard("events_worker", env=_env("production", **clean, **{flag: "true"}))
    assert enforce_boot_guard("events_worker", env=_env("production", **clean)) is Mode.PRODUCTION


def test_unknown_service_is_refused_in_strict_mode():
    with pytest.raises(TrustPathViolation):
        enforce_boot_guard("unaudited", env=_env("production"))


# --- audited foundation-era processes ----------------------------------------


@pytest.mark.parametrize("service", sorted(CONFIGURED))
def test_configured_foundation_process_is_allowed_in_sandbox(service):
    assert enforce_boot_guard(service, env=_configured(service, "sandbox")) is Mode.SANDBOX


@pytest.mark.parametrize("service", ["chain", "read_api", "privacy_exports"])
def test_test_network_only_processes_are_refused_in_production(service):
    """No Mainnet support exists, so Midnight test-network data is SANDBOX, never production."""
    with pytest.raises(TrustPathViolation) as exc:
        enforce_boot_guard(service, env=_configured(service, "production"))
    assert any("chain.midnight" in v and "sandbox, not allowed in production" in v for v in exc.value.violations)


@pytest.mark.parametrize("service", ["events_worker", "events_retention", "gateway", "consumer_domains"])
def test_processes_without_test_network_scope_are_allowed_in_production(service):
    assert enforce_boot_guard(service, env=_configured(service, "production")) is Mode.PRODUCTION


@pytest.mark.parametrize("service,variable", [("chain", "MIDNIGHT_NETWORK"), ("read_api", "READ_API_NETWORK"),
                                              ("privacy_exports", "EXPORT_NETWORK")])
@pytest.mark.parametrize("network", ["mainnet", "", "testnet-02"])
def test_unauthorized_midnight_network_is_required_but_unconfigured(service, variable, network):
    env = _configured(service, "sandbox", **{variable: network})
    with pytest.raises(TrustPathViolation) as exc:
        enforce_boot_guard(service, env=env)
    assert any("required but unconfigured" in v for v in exc.value.violations)


def test_chain_inventory_is_current():
    """The former entries cited deleted brandme-chain/src/services/* files."""
    regs = {r.component: r for r in service_registrations("chain", Mode.SANDBOX, {"MIDNIGHT_NETWORK": "preprod"})}
    assert regs[TrustComponent.CHAIN_MIDNIGHT].kind is AdapterKind.SANDBOX
    assert "brandme-chain/src/midnight/adapter.ts" in regs[TrustComponent.CHAIN_MIDNIGHT].implementation
    assert regs[TrustComponent.CHAIN_CARDANO].kind is AdapterKind.UNCONFIGURED
    assert not regs[TrustComponent.CHAIN_CARDANO].required
    assert "UnavailableCardanoAnchor" in regs[TrustComponent.CHAIN_CARDANO].implementation
    # MIDNIGHT_NETWORK defaults to preprod in brandme-chain/src/config/index.ts.
    default = service_registrations("chain", Mode.SANDBOX, {})
    assert default[0].kind is AdapterKind.SANDBOX


def _all_registrations():
    for regs in LEGACY_SIMULATED_ADAPTERS.values():
        yield from regs
    env = {**CONFIGURED["gateway"], **CONFIGURED["consumer_domains"], "BRANDME_TRYON_PROVIDER": "simulated",
           "MIDNIGHT_NETWORK": "preprod", "READ_API_NETWORK": "preprod", "EXPORT_NETWORK": "preprod"}
    for name, process in AUDITED_PROCESSES.items():
        for mode in Mode:
            yield from process.registrations(mode, env)
            yield from process.registrations(mode, {})
        assert process.summary


def test_every_cited_file_exists():
    roots = ("brandme-chain/", "brandme_core/", "brandme-core/", "brandme-gateway/", "brandme-agents/",
             "brandme-cube/", "brandme-governance/", "docs/")
    cited = set()
    for reg in _all_registrations():
        for text in (reg.implementation, reg.evidence):
            cited.update(p for p in re.findall(r"[\w./-]+\.(?:py|ts|md)", text) if p.startswith(roots))
    for process in AUDITED_PROCESSES.values():
        cited.update(p for p in re.findall(r"[\w./-]+\.(?:py|ts)", process.environment_source) if p.startswith(roots))
    assert cited, "the inventory must cite code"
    missing = sorted(p for p in cited if not (REPO / p).exists())
    assert not missing, f"inventory cites files that do not exist: {missing}"


def test_gateway_dev_identity_is_a_labelled_simulation():
    assert simulation_labels("gateway", _env("development")) == [{
        "component": "auth.identity",
        "label": "Simulated sign-in: fictional test identity, not a verified account",
        "implementation": "brandme-gateway/src/routes/v1/index.ts POST /session/dev (IDENTITY_PROVIDER=dev)",
    }]
    with pytest.raises(TrustPathViolation, match="auth.identity"):
        enforce_boot_guard("gateway", env=_env("sandbox"))


@pytest.mark.parametrize("override", [{"OIDC_ISSUER": "http://issuer.example.test"}, {"OIDC_AUDIENCE": ""}])
def test_gateway_oidc_without_issuer_and_audience_is_refused(override):
    with pytest.raises(TrustPathViolation, match="required but unconfigured"):
        enforce_boot_guard("gateway", env=_configured("gateway", "production", **override))


# --- consumer_domains (brandme_core/domains/persona/app.py guard("consumer_domains")) ----


def test_consumer_domains_is_audited_and_allowed_in_sandbox_with_complete_config():
    """It was refused as unaudited ("has no audited trust-path inventory") before this entry."""
    assert "consumer_domains" in AUDITED_PROCESSES
    env = _configured("consumer_domains", "sandbox")
    assert guard("consumer_domains", env=env) is Mode.SANDBOX
    regs = {r.component: r for r in service_registrations("consumer_domains", Mode.SANDBOX, env)}
    assert regs[TrustComponent.AUTH_IDENTITY].kind is AdapterKind.SANDBOX
    assert "persona/assertion.py DomainAssertionVerifier" in regs[TrustComponent.AUTH_IDENTITY].implementation
    assert regs[TrustComponent.TRYON_PHOTO].kind is AdapterKind.UNCONFIGURED and not regs[TrustComponent.TRYON_PHOTO].required
    production = service_registrations("consumer_domains", Mode.PRODUCTION, env)
    assert production[0].kind is AdapterKind.REAL


@pytest.mark.parametrize("mode", ["sandbox", "production"])
@pytest.mark.parametrize("flag", ["ENABLE_STUB_MODE", "ALLOW_STUB_FALLBACK", "ZK_ALLOW_STUB_FALLBACK"])
def test_consumer_domains_still_refuses_stub_flags(mode, flag):
    with pytest.raises(TrustPathViolation, match=f"{flag}='true' enables a stub fallback"):
        enforce_boot_guard("consumer_domains", env=_configured("consumer_domains", mode, **{flag: "true"}))


@pytest.mark.parametrize("mode", ["sandbox", "production"])
@pytest.mark.parametrize("emulator", ["SPANNER_EMULATOR_HOST", "STORAGE_EMULATOR_HOST"])
def test_consumer_domains_refuses_emulators_in_strict_modes(mode, emulator):
    with pytest.raises(TrustPathViolation) as exc:
        enforce_boot_guard("consumer_domains", env=_configured("consumer_domains", mode, **{emulator: "localhost:9010"}))
    assert exc.value.violations == [f"{emulator} points at a local emulator; consumer_domains uses real services in {mode}"]


@pytest.mark.parametrize("mode", ["sandbox", "production"])
def test_consumer_domains_refuses_the_simulated_tryon_provider_in_strict_modes(mode):
    with pytest.raises(TrustPathViolation, match=f"tryon.photo via .*SimulatedTryOnProvider.* is simulated, not allowed in {mode}"):
        enforce_boot_guard("consumer_domains", env=_configured("consumer_domains", mode, BRANDME_TRYON_PROVIDER="simulated"))


def test_consumer_domains_local_modes_use_emulators_and_label_the_simulated_provider():
    env = _configured("consumer_domains", "development", SPANNER_EMULATOR_HOST="localhost:9010",
                      STORAGE_EMULATOR_HOST="http://127.0.0.1:4443", BRANDME_TRYON_PROVIDER="simulated")
    assert enforce_boot_guard("consumer_domains", env=env) is Mode.DEVELOPMENT
    assert simulation_labels("consumer_domains", env) == [{
        "component": "tryon.photo",
        "label": "Generated visual preview. Not a fit or size guarantee. Simulated provider.",
        "implementation": "brandme_core/domains/media/providers.py SimulatedTryOnProvider (BRANDME_TRYON_PROVIDER=simulated)",
    }]


def _private_jwks():
    return json.dumps({"keys": [_jwk(ec.generate_private_key(ec.SECP256R1()))]})


@pytest.mark.parametrize("override,reason", [
    ({"CONSUMER_DOMAIN_ASSERTION_ISSUER": ""}, "CONSUMER_DOMAIN_ASSERTION_ISSUER is unset"),
    ({"CONSUMER_DOMAIN_ASSERTION_JWKS": ""}, "CONSUMER_DOMAIN_ASSERTION_JWKS is unset or holds no keys"),
    ({"CONSUMER_DOMAIN_ASSERTION_JWKS": '{"keys": []}'}, "CONSUMER_DOMAIN_ASSERTION_JWKS is unset or holds no keys"),
    ({"CONSUMER_DOMAIN_ASSERTION_JWKS": "not json"}, "CONSUMER_DOMAIN_ASSERTION_JWKS is not a JSON Web Key Set"),
    ({"CONSUMER_DOMAIN_ASSERTION_JWKS": '{"keys": [{"kty": "RSA", "kid": "k", "n": "x", "e": "AQAB"}]}'},
     "holds a key that is not a P-256 key with a kid"),
    ({"CONSUMER_DOMAIN_ASSERTION_JWKS": None}, "CONSUMER_DOMAIN_ASSERTION_JWKS holds a private key (public keys only)"),
    ({"BRANDME_TRYON_PROVIDER": "vendor-x"}, "BRANDME_TRYON_PROVIDER='vendor-x' is not a known provider"),
])
def test_consumer_domains_misconfiguration_is_required_but_unconfigured(override, reason):
    override = {k: (_private_jwks() if v is None else v) for k, v in override.items()}
    with pytest.raises(TrustPathViolation) as exc:
        enforce_boot_guard("consumer_domains", env=_configured("consumer_domains", "sandbox", **override))
    assert len(exc.value.violations) == 1
    assert reason in exc.value.violations[0] and exc.value.violations[0].endswith("is required but unconfigured")


def _domain_check(env):
    # GOOGLE_APPLICATION_CREDENTIALS at a missing file: credential lookup fails without a network call.
    return subprocess.run([sys.executable, "-m", "brandme_core.domains.persona.app", "--check"], cwd=REPO,
                          env={"PATH": "", "GOOGLE_APPLICATION_CREDENTIALS": str(REPO / "no-such-credentials.json"), **env},
                          capture_output=True, text=True, timeout=120)


def test_domain_service_entrypoint_passes_the_boot_guard_in_sandbox():
    """The real entrypoint: complete sandbox config gets past guard("consumer_domains") (exit 3 before
    this entry) and then refuses only because no Google credential exists here (exit 2)."""
    out = _domain_check(_configured("consumer_domains", "sandbox"))
    assert out.returncode == 2, out.stderr
    assert out.stdout == '{"status":"startup_refused"}\n'
    assert "[brandme boot]" not in out.stderr and "Traceback" not in out.stderr


@pytest.mark.parametrize("extra,reason", [({"ENABLE_STUB_MODE": "true"}, "ENABLE_STUB_MODE"),
                                          ({"BRANDME_TRYON_PROVIDER": "simulated"}, "tryon.photo")])
def test_domain_service_entrypoint_boot_guard_refuses_stub_and_simulated_provider(extra, reason):
    out = _domain_check(_configured("consumer_domains", "sandbox", **extra))
    assert out.returncode == 3 and out.stdout == ""
    assert "[brandme boot] consumer_domains: REFUSED" in out.stderr and reason in out.stderr


# --- single mode source --------------------------------------------------------


def test_environment_is_derived_from_brandme_mode():
    assert resolve_environment({"BRANDME_MODE": "sandbox"}) == "sandbox"
    assert resolve_environment({"BRANDME_MODE": "sandbox", "ENVIRONMENT": "sandbox"}) == "sandbox"
    with pytest.raises(ModeConfigurationError):
        resolve_environment({"ENVIRONMENT": "production"})
    with pytest.raises(ModeConfigurationError, match="conflicts"):
        resolve_environment({"BRANDME_MODE": "production", "ENVIRONMENT": "development"})


@pytest.mark.parametrize("service", ["brain", "governance", "events_worker", "chain"])
def test_conflicting_environment_refuses_every_service(service):
    with pytest.raises(ModeConfigurationError, match="conflicts"):
        enforce_boot_guard(service, env=_env("development", ENVIRONMENT="production"))


@pytest.mark.parametrize("service", ["read_api", "privacy_exports", "events_worker", "events_retention", "consumer_domains"])
@pytest.mark.parametrize("mode", ["sandbox", "development"])
def test_processes_that_read_environment_need_it_set(service, mode):
    with pytest.raises(TrustPathViolation, match="ENVIRONMENT is unset"):
        enforce_boot_guard(service, env={k: v for k, v in _configured(service, mode).items() if k != "ENVIRONMENT"})


def test_chain_without_environment_would_run_as_development():
    env = {k: v for k, v in _configured("chain", "sandbox").items() if k != "ENVIRONMENT"}
    with pytest.raises(TrustPathViolation, match="would run as 'development'"):
        enforce_boot_guard("chain", env=env)
    # In development the chain's own default agrees with BRANDME_MODE.
    assert enforce_boot_guard("chain", env={"BRANDME_MODE": "development"}) is Mode.DEVELOPMENT


def test_cors_config_uses_brandme_mode(monkeypatch):
    from brandme_core.cors_config import get_cors_config

    assert get_cors_config({"BRANDME_MODE": "development"})["allow_origins"]
    with pytest.raises(ModeConfigurationError):
        get_cors_config({})
    with pytest.raises(ModeConfigurationError):
        get_cors_config({"BRANDME_MODE": "development", "ENVIRONMENT": "production"})
    monkeypatch.setattr("brandme_core.cors_config.parse_cors_origins", lambda: ["*"])
    with pytest.raises(ValueError, match="not allowed"):
        get_cors_config({"BRANDME_MODE": "sandbox"})
    assert get_cors_config({"BRANDME_MODE": "demo"})["allow_origins"] == ["*"]


# --- preflight CLI -----------------------------------------------------------------


def _preflight(service, env):
    return subprocess.run([sys.executable, "-m", "brandme_core.config", "preflight", "--service", service],
                          cwd=REPO, env={"PATH": "", **env}, capture_output=True, text=True)


def test_preflight_cli_exits_nonzero_in_production():
    """The same command compose runs before each service starts."""
    refused = _preflight("orchestrator", {"BRANDME_MODE": "production"})
    assert refused.returncode == 3, refused.stderr
    assert "REFUSED" in refused.stderr and "chain.cardano" in refused.stderr
    allowed = _preflight("orchestrator", {"BRANDME_MODE": "demo"})
    assert allowed.returncode == 0, allowed.stderr
    assert "Simulated" in allowed.stdout


def test_preflight_cli_allows_configured_read_api_in_sandbox():
    allowed = _preflight("read-api", _configured("read-api", "sandbox"))
    assert allowed.returncode == 0, allowed.stderr
    assert "allowed in sandbox; simulated adapters: 0" in allowed.stdout
    refused = _preflight("read-api", {"BRANDME_MODE": "sandbox"})
    assert refused.returncode == 3 and "ENVIRONMENT is unset" in refused.stderr


def test_inventory_cli_lists_legacy_and_audited_processes():
    out = subprocess.run([sys.executable, "-m", "brandme_core.config", "inventory"], cwd=REPO,
                         env={"PATH": "", "BRANDME_MODE": "sandbox"}, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    for name in ("orchestrator", "chain", "read_api", "privacy_exports", "events_worker", "events_retention", "gateway",
                 "consumer_domains"):
        assert f'"{name}"' in out.stdout
    assert "services/midnight-client.ts" not in out.stdout
