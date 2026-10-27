"""Deterministic commerce test harness: frozen clock, local simulated provider, principals.

All people, merchants and products are fictional (contracts/demo-scenario.json).
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from brandme_core.domains.commerce.autonomy import AutonomyBoundary, AutonomyLevel, BoundaryRule, RuleScope
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
from brandme_core.orchestrator.runlog import MemoryRunLog

MEMBER = "2ad9041e-561e-527b-aa0d-5a7fda5f710b"  # fictional demo member
OTHER_MEMBER = "fa9ad97d-0187-5b71-a602-b05aabb329e1"
AGENT_CLIENT = "client-fictional-shopping-agent"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HEX_REF = re.compile(r"(?<![0-9A-Za-z])(?=[0-9]*[a-f])[0-9a-f]{16,64}(?![0-9A-Za-z])")


def without_random_ids(text: str) -> str:
    """``text`` with UUIDs and keyed hex refs replaced, so a check that a digit string (a card number, an
    amount) never reaches a log cannot match inside a random id by chance. A run of digits alone is never
    replaced (a card number or amount has no hex letter), so the check stays as strict as a plain ``in``."""
    return _HEX_REF.sub("<ref>", _UUID.sub("<id>", text))


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


def member_session(member: str = MEMBER, aal: str = "aal2", scopes=None,
                   environment: str = "development") -> Principal:
    """First-party trusted-UI session (foundation session principal: profile scopes only)."""
    return Principal(member_id=member, subject=f"sub-{member[:8]}", session_id="sess-1", client_id="brandme-web",
                     scopes=frozenset(scopes or {"profile:read", "profile:write", "privacy:manage"}),
                     assurance_level=aal, environment=environment)


def agent(delegation_id: Optional[str], scopes, member: str = MEMBER, client: str = AGENT_CLIENT) -> Principal:
    """Agent/bearer principal; ``delegation_id=None`` exercises (member, client) resolution."""
    return Principal(member_id=member, subject=f"sub-{member[:8]}", session_id=None, client_id=client,
                     scopes=frozenset(scopes), assurance_level="aal1", environment="development",
                     delegation_id=delegation_id)


def line(slug: str = "overshirt", size: str = "m", qty: int = 1) -> CartLineRequest:
    ref = f"demo-{slug}-{size}"
    return CartLineRequest(variant_uuid(ref), ref, qty)


def limits(per_order: int = 50_000, cumulative: int = 50_000, **kw) -> DelegationLimits:
    return DelegationLimits(currency="USD", max_per_order=Money(per_order, "USD"),
                            max_cumulative=Money(cumulative, "USD"), window_seconds=30 * 86400,
                            allowed_merchants=frozenset({MERCHANT_ID}), **kw)


def usd(minor: Optional[int]) -> Optional[Money]:
    return Money(minor, "USD") if minor is not None else None


def merchant_rule(level: str = "buy_after_approval", cap: Optional[int] = None, *, provider: str = PROVIDER_ID,
                  merchant: str = MERCHANT_ID) -> BoundaryRule:
    return BoundaryRule(RuleScope.MERCHANT, provider, AutonomyLevel(level), merchant_id=merchant, max_total=usd(cap))


def wishlist_rule(*refs: str, level: str = "buy_after_approval", cap: Optional[int] = None,
                  provider: str = PROVIDER_ID) -> BoundaryRule:
    return BoundaryRule(RuleScope.WISHLIST, provider, AutonomyLevel(level), variant_refs=frozenset(refs),
                        max_total=usd(cap))


def boundary(*rules: BoundaryRule, default: str = "prepare", default_cap: Optional[int] = None) -> AutonomyBoundary:
    """A member's assistant rules; the concierge prepares by default."""
    return AutonomyBoundary(default_level=AutonomyLevel(default), default_max_total=usd(default_cap), rules=rules)


# The test member's own rule on every buy grant ``World.delegate`` makes unless a test says otherwise: the
# assistant may place, at the demo merchant, what the member approved (no cap of its own; the grant's limits
# bound it). Without a rule the concierge only prepares. ``boundary=None`` asks for a grant with no rules.
MEMBER_RULES = object()


@dataclass
class World:
    clock: Clock
    provider: LocalAtelierProvider
    registry: ProviderRegistry
    store: object  # InMemoryCommerceStore | SpannerCommerceStore
    svc: CommerceService
    member: Principal = field(default_factory=member_session)
    # Every agent autonomy decision, through the strict closed run-log schema: a malformed line raises.
    decisions: MemoryRunLog = field(default_factory=lambda: MemoryRunLog(strict=True))

    def delegate(self, mode=AssistanceMode.BUY_WITHIN_RULES, lim: Optional[DelegationLimits] = None,
                 boundary=MEMBER_RULES):
        if boundary is MEMBER_RULES:
            boundary = AutonomyBoundary(rules=(merchant_rule(),)) if mode is AssistanceMode.BUY_WITHIN_RULES else None
        d = self.svc.create_delegation(
            self.member, client_id=AGENT_CLIENT, mode=mode, allowed_providers={PROVIDER_ID},
            limits=lim if lim is not None else (limits() if mode is AssistanceMode.BUY_WITHIN_RULES else None),
            expires_at=self.clock.now + timedelta(days=7), boundary=boundary)
        return d, agent(d.id, d.scopes)

    def decided(self):
        """``(action, outcome, primary code)`` for each logged autonomy decision, in order."""
        return [(ln["action"], ln["outcome"], ln["codes"][0]) for ln in self.decisions.events("commerce.autonomy_decision")]

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


def world(environment: str = "development", store=None, payments=None, fulfillment=None) -> World:
    """``payments`` / ``fulfillment``: an instance, or a factory taking the world's clock. Default: simulated."""
    clock = Clock()
    made = lambda x: x(clock) if isinstance(x, type) or inspect.isroutine(x) else x  # noqa: E731
    payments, fulfillment = made(payments), made(fulfillment)
    provider = LocalAtelierProvider(clock, payments=payments, fulfillment=fulfillment, environment=environment)
    registry = ProviderRegistry(environment)
    registry.register(local_atelier_connection(provider, environment, clock.now))
    store = store if store is not None else InMemoryCommerceStore()
    w = World(clock, provider, registry, store, CommerceService(
        store=store, registry=registry, environment=environment, clock=clock))
    w.svc.add_autonomy_sink(w.decisions.autonomy_decision)
    return w
