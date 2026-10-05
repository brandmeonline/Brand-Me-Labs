"""Mode guard: strict modes fail closed on trust-path simulation (BM-BASE-002)."""
import subprocess
import sys
from pathlib import Path

import pytest

from brandme_core.config import (
    LEGACY_SIMULATED_ADAPTERS,
    AdapterKind,
    AdapterRegistration,
    Mode,
    ModeConfigurationError,
    TrustComponent,
    TrustPathViolation,
    check_registrations,
    enforce_boot_guard,
    get_mode,
)

REPO = Path(__file__).resolve().parents[2]


def _env(mode, **extra):
    return {"BRANDME_MODE": mode, **extra}


def test_mode_is_required_and_validated():
    with pytest.raises(ModeConfigurationError):
        get_mode({})
    with pytest.raises(ModeConfigurationError):
        get_mode({"BRANDME_MODE": "prod"})
    assert get_mode({"BRANDME_MODE": " Production "}) is Mode.PRODUCTION


@pytest.mark.parametrize("service", ["orchestrator", "chain", "mcp", "identity", "compliance", "cube", "brain", "policy", "knowledge"])
@pytest.mark.parametrize("mode", ["production", "sandbox"])
def test_strict_modes_refuse_services_with_fake_trust_paths(service, mode):
    with pytest.raises(TrustPathViolation) as exc:
        enforce_boot_guard(service, env=_env(mode))
    assert exc.value.violations, "a refusal must name the fake"


@pytest.mark.parametrize("service", sorted(LEGACY_SIMULATED_ADAPTERS))
@pytest.mark.parametrize("mode", ["demo", "development"])
def test_local_modes_allow_labelled_simulation(service, mode):
    assert enforce_boot_guard(service, env=_env(mode)).value == mode


def test_every_simulated_adapter_carries_a_visible_label():
    for regs in LEGACY_SIMULATED_ADAPTERS.values():
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
    with pytest.raises(TrustPathViolation):
        enforce_boot_guard("governance", env=_env("production", **{flag: "true"}))
    assert enforce_boot_guard("governance", env=_env("production")) is Mode.PRODUCTION


def test_unknown_service_is_refused_in_strict_mode():
    with pytest.raises(TrustPathViolation):
        enforce_boot_guard("unaudited", env=_env("production"))


def test_preflight_cli_exits_nonzero_in_production():
    """The same command compose runs before each service starts."""
    base = [sys.executable, "-m", "brandme_core.config", "preflight", "--service", "orchestrator"]
    refused = subprocess.run(base, cwd=REPO, env={"BRANDME_MODE": "production", "PATH": ""}, capture_output=True, text=True)
    assert refused.returncode == 3, refused.stderr
    assert "REFUSED" in refused.stderr and "chain.cardano" in refused.stderr
    allowed = subprocess.run(base, cwd=REPO, env={"BRANDME_MODE": "demo", "PATH": ""}, capture_output=True, text=True)
    assert allowed.returncode == 0, allowed.stderr
    assert "Simulated" in allowed.stdout
