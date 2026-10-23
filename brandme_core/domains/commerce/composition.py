"""Startup composition for the commerce domain: which provider adapters run, chosen once from config.

ch.05 §1: "No adapter can silently change from live to demo. Dependency injection selects a
provider mode at startup; production boot rejects simulation implementations." Swapping the
simulated payment rail for Stripe test mode, or a future real merchant for the simulator, is a
change here and in configuration, not in the commerce service.

Configuration (environment variables; secrets come from the platform's secret store):

* ``BRANDME_MODE``: demo | development | sandbox | production (required).
* ``BRANDME_COMMERCE_PAYMENTS``: ``simulated`` (default) or ``stripe_test``; demo/development only.
* ``STRIPE_TEST_SECRET_KEY``: Stripe test-mode key (``sk_test_…``/``rk_test_…``) for ``stripe_test``.
* ``STRIPE_TEST_WEBHOOK_SECRET``: optional ``whsec_…`` to accept Stripe test webhooks.

A misconfigured choice refuses to boot; there is no fallback to another rail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional

from brandme_core.domains.providers.local_atelier import LocalAtelierProvider, local_atelier_connection
from brandme_core.domains.providers.payments import PaymentProcessor
from brandme_core.domains.providers.registry import ProviderRegistry

PAYMENTS_ENV = "BRANDME_COMMERCE_PAYMENTS"
RAILS = ("simulated", "stripe_test")
DEV_ENVIRONMENTS = ("demo", "development")


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


def payment_processor(rail: str, env: Mapping[str, str], clock: Callable[[], datetime],
                      environment: str = "development") -> PaymentProcessor:
    if rail == "simulated":
        from brandme_core.domains.providers.payments.simulated import SimulatedPaymentProcessor
        return SimulatedPaymentProcessor(clock, environment=environment)
    if rail == "stripe_test":
        from brandme_core.domains.providers.payments.stripe_test import (
            StripeKeyRefused, StripeTestConfig, StripeTestPaymentProcessor,
        )
        try:
            cfg = StripeTestConfig.from_env(env)
        except StripeKeyRefused as e:
            raise CompositionError("stripe_test_not_configured" if e.code == "stripe_key_missing"
                                   else "stripe_key_refused") from None
        from brandme_core.domains.providers.payments.stripe_wire import SdkStripeWire
        return StripeTestPaymentProcessor(cfg, wire=SdkStripeWire(cfg), environment=environment, clock=clock)
    raise CompositionError("payments_rail_unknown")


def build_providers(environment: str, *, env: Mapping[str, str],
                    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> CommerceProviders:
    registry = ProviderRegistry(environment)
    rail = env.get(PAYMENTS_ENV)
    if environment not in DEV_ENVIRONMENTS:
        # No simulated merchant, and no test-mode rail, outside demo/development. Real merchants
        # register here once one is contracted and verified.
        if rail:
            raise CompositionError("payments_rail_not_allowed")
        return CommerceProviders(registry, None, None)
    rail = rail or "simulated"
    if rail not in RAILS:
        raise CompositionError("payments_rail_unknown")
    provider = LocalAtelierProvider(clock, payments=payment_processor(rail, env, clock, environment),
                                    environment=environment)
    registry.register(local_atelier_connection(provider, environment, clock()))
    return CommerceProviders(registry, rail, provider)
