"""Startup composition for the commerce domain: which provider adapters run, chosen once from config.

ch.05 §1: "No adapter can silently change from live to demo. Dependency injection selects a
provider mode at startup; production boot rejects simulation implementations." Swapping the
simulated payment rail for Stripe test mode, or a future real merchant for the simulator, is a
change here and in configuration, not in the commerce service. The processor instance is fixed
inside the merchant adapter: a runtime Stripe failure surfaces as a ``ProviderError`` kind, and
the rail never changes underneath a running process.

Configuration (``ENV_KEYS`` only; no other name is ever read — not ``STRIPE_SECRET_KEY``,
``STRIPE_API_KEY``, ``ANTHROPIC_*`` or an ambient ``HTTPS_PROXY``; secrets come from the
platform's secret store):

* ``BRANDME_COMMERCE_PAYMENTS``: ``simulated`` (default) or ``stripe_test``; demo/development only.
* ``STRIPE_TEST_SECRET_KEY``: Stripe test-mode key (``sk_test_…`` or restricted ``rk_test_…``).
* ``STRIPE_TEST_WEBHOOK_SECRET`` / ``STRIPE_TEST_WEBHOOK_SECRET_PREVIOUS``: optional ``whsec_…``
  secrets (current and, during rotation, previous) to accept Stripe test webhooks.
* ``BRANDME_STRIPE_EGRESS_PROXY``: optional explicit proxy for Stripe egress.
* ``BRANDME_STRIPE_CA_BUNDLE``: optional absolute path to the CA bundle for Stripe egress.
* ``STRIPE_LOG``: read only to refuse ``debug``/``info``, under which the SDK prints request and
  response bodies to stderr.

A misconfigured choice refuses to boot with a fixed code; there is no fallback to another rail.
Nothing here makes a network call.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional

from brandme_core.domains.providers.local_atelier import LocalAtelierProvider, local_atelier_connection
from brandme_core.domains.providers.payments import PaymentProcessor, assert_payment_rail_allowed
from brandme_core.domains.providers.redaction import PaymentLogSink
from brandme_core.domains.providers.registry import ProviderRegistry, SimulationInProductionError

PAYMENTS_ENV = "BRANDME_COMMERCE_PAYMENTS"
ENV_KEYS = (PAYMENTS_ENV, "STRIPE_TEST_SECRET_KEY", "STRIPE_TEST_WEBHOOK_SECRET", "STRIPE_TEST_WEBHOOK_SECRET_PREVIOUS",
            "BRANDME_STRIPE_EGRESS_PROXY", "BRANDME_STRIPE_CA_BUNDLE", "STRIPE_LOG")
RAILS = ("simulated", "stripe_test")
DEV_ENVIRONMENTS = ("demo", "development")
# StripeKeyRefused codes that are passed through as boot codes; any other refusal is stripe_key_refused.
_CONFIG_CODES = {"stripe_key_missing": "stripe_test_not_configured",
                 "stripe_webhook_secret_refused": "stripe_webhook_secret_refused",
                 "stripe_egress_proxy_refused": "stripe_egress_proxy_refused",
                 "stripe_ca_bundle_refused": "stripe_ca_bundle_refused"}


class CompositionError(RuntimeError):
    """Startup refused; ``code`` is fixed and never carries a secret."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CommerceProviders:
    registry: ProviderRegistry
    payments_rail: Optional[str]
    demo_atelier: Optional[LocalAtelierProvider]
    payments: Optional[PaymentProcessor] = None


def _stripe_processor(view: Mapping[str, str], environment: str, clock: Callable[[], datetime],
                      wire_factory: Optional[Callable], log: Optional[PaymentLogSink]) -> PaymentProcessor:
    if view.get("STRIPE_LOG", "").strip().lower() in ("debug", "info"):
        raise CompositionError("stripe_log_refused")
    from brandme_core.domains.providers.payments.stripe_test import (
        StripeKeyRefused, StripeTestConfig, StripeTestPaymentProcessor,
    )
    try:
        cfg = StripeTestConfig.from_env(view)
    except StripeKeyRefused as e:
        raise CompositionError(_CONFIG_CODES.get(e.code, "stripe_key_refused")) from None
    if wire_factory is None:
        from brandme_core.domains.providers.payments.stripe_wire import SdkStripeWire
        wire_factory = SdkStripeWire  # the SDK is imported only here, on the Stripe rail
    try:
        wire = wire_factory(cfg)
    except StripeKeyRefused:
        raise CompositionError("stripe_key_refused") from None
    except ValueError as e:
        raise CompositionError("stripe_api_version_unverified" if str(e) == "stripe_api_version_unverified"
                               else "stripe_wire_refused") from None
    return StripeTestPaymentProcessor(cfg, wire=wire, environment=environment, clock=clock, log=log)


def build_providers(environment: str, *, env: Mapping[str, str],
                    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                    stripe_wire_factory: Optional[Callable] = None,
                    log: Optional[PaymentLogSink] = None) -> CommerceProviders:
    from brandme_core.config import AdapterKind, AdapterRegistration, Mode, TrustComponent, check_registrations

    view = {k: env[k] for k in ENV_KEYS if k in env}
    try:
        mode = Mode(environment)
    except ValueError:
        raise CompositionError("environment_unknown") from None
    registry = ProviderRegistry(environment)
    if environment not in DEV_ENVIRONMENTS:
        # No simulated merchant, and no test-mode rail, outside demo/development. Real merchants
        # register here once one is contracted and verified.
        if PAYMENTS_ENV in view:
            raise CompositionError("payments_rail_not_allowed")
        return CommerceProviders(registry, None, None, None)
    rail = view.get(PAYMENTS_ENV) or "simulated"
    if rail not in RAILS:
        raise CompositionError("payments_rail_unknown")
    if rail == "stripe_test":
        payments = _stripe_processor(view, environment, clock, stripe_wire_factory, log)
    else:
        from brandme_core.domains.providers.payments.simulated import SimulatedPaymentProcessor
        payments = SimulatedPaymentProcessor(clock, environment=environment)
    try:
        assert_payment_rail_allowed(environment, payments.descriptor)
    except (ValueError, SimulationInProductionError):
        raise CompositionError("payment_rail_not_allowed") from None
    provider = LocalAtelierProvider(clock, payments=payments, environment=environment)
    conn = local_atelier_connection(provider, environment, clock())
    if any(c.state not in ("sandbox", "unsupported") for c in conn.capabilities.values()):
        raise CompositionError("capability_state_invalid")  # a simulated merchant is never verified
    violations = check_registrations(mode, [
        AdapterRegistration(TrustComponent.COMMERCE_CHECKOUT, AdapterKind.SIMULATED,
                            "providers/local_atelier.py LocalAtelierProvider", conn.disclosure),
        AdapterRegistration(TrustComponent.COMMERCE_CHECKOUT,
                            AdapterKind.SANDBOX if rail == "stripe_test" else AdapterKind.SIMULATED,
                            f"providers/payments {payments.processor_id}", payments.descriptor.label)])
    if violations:
        raise CompositionError("trust_path_violation")
    registry.register(conn)
    return CommerceProviders(registry, rail, provider, payments)
