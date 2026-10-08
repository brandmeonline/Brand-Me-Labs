"""Deterministic commerce test harness: frozen clock, local simulated provider, principals.

All people, merchants and products are fictional (contracts/demo-scenario.json).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from brandme_core.domains.commerce.delegation import AssistanceMode, DelegationLimits
from brandme_core.domains.commerce.money import Money
from brandme_core.domains.commerce.principal import Principal
from brandme_core.domains.commerce.service import CommerceService
from brandme_core.domains.commerce.store import InMemoryCommerceStore
from brandme_core.domains.providers.contracts import CartLineRequest
from brandme_core.domains.providers.local_atelier import (
    MERCHANT_ID, PROVIDER_ID, LocalAtelierProvider, local_atelier_connection, variant_uuid,
)
from brandme_core.domains.providers.registry import ProviderRegistry

MEMBER = "2ad9041e-561e-527b-aa0d-5a7fda5f710b"  # fictional demo member
OTHER_MEMBER = "fa9ad97d-0187-5b71-a602-b05aabb329e1"
AGENT_CLIENT = "client-fictional-shopping-agent"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


def member_session(member: str = MEMBER, aal: str = "aal2", scopes=None) -> Principal:
    return Principal(member_id=member, subject=f"sub-{member[:8]}", issuer="https://idp.example.invalid",
                     client_id="brandme-web", scopes=frozenset(scopes or {
                         "commerce:research", "commerce:cart", "commerce:purchase"}),
                     assurance_level=aal, environment="development", session_id="sess-1",
                     first_party_session=True)


def agent(delegation_id: str, scopes, member: str = MEMBER, client: str = AGENT_CLIENT) -> Principal:
    return Principal(member_id=member, subject=f"sub-{member[:8]}", issuer="https://idp.example.invalid",
                     client_id=client, scopes=frozenset(scopes), assurance_level="aal1",
                     environment="development", delegation_id=delegation_id)


def line(slug: str = "overshirt", size: str = "m", qty: int = 1) -> CartLineRequest:
    ref = f"demo-{slug}-{size}"
    return CartLineRequest(variant_uuid(ref), ref, qty)


def limits(per_order: int = 50_000, cumulative: int = 50_000, **kw) -> DelegationLimits:
    return DelegationLimits(currency="USD", max_per_order=Money(per_order, "USD"),
                            max_cumulative=Money(cumulative, "USD"), window_seconds=30 * 86400,
                            allowed_merchants=frozenset({MERCHANT_ID}), **kw)


@dataclass
class World:
    clock: Clock
    provider: LocalAtelierProvider
    registry: ProviderRegistry
    store: InMemoryCommerceStore
    svc: CommerceService
    member: Principal = field(default_factory=member_session)

    def delegate(self, mode=AssistanceMode.BUY_WITHIN_RULES, lim: Optional[DelegationLimits] = None):
        d = self.svc.create_delegation(
            self.member, client_id=AGENT_CLIENT, mode=mode, allowed_providers={PROVIDER_ID},
            limits=lim if lim is not None else (limits() if mode is AssistanceMode.BUY_WITHIN_RULES else None),
            expires_at=self.clock.now + timedelta(days=7))
        return d, agent(d.id, d.scopes)

    def prepared(self, actor: Principal, *lines_):
        cart = self.svc.create_cart(actor, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID,
                                    lines=list(lines_ or [line()]))
        quote = self.svc.quote_cart(actor, cart.id)
        op = self.svc.request_purchase(actor, quote.id)
        return cart, quote, op

    def approve(self, op):
        ch = self.svc.open_approval_challenge(self.member, op.id)
        return self.svc.approve(self.member, operation_id=op.id, challenge_id=ch.id, nonce=ch.nonce,
                                displayed_quote_hash=ch.quote_hash)


def world(environment: str = "development") -> World:
    clock = Clock()
    provider = LocalAtelierProvider(clock)
    registry = ProviderRegistry(environment)
    registry.register(local_atelier_connection(provider, environment, clock.now))
    store = InMemoryCommerceStore()
    return World(clock, provider, registry, store, CommerceService(
        store=store, registry=registry, environment=environment, clock=clock))
