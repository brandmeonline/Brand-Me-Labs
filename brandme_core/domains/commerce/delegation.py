"""Agent delegations: Research / Prepare / Buy-within-rules (ch.05 §5)."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import FrozenSet, Optional

from .autonomy import LEVEL_RANK, NO_BOUNDARY, AutonomyBoundary, AutonomyLevel, RuleScope
from .errors import DelegationInvalid, Forbidden
from .money import Money
from .principal import Principal, is_agent


class AssistanceMode(str, enum.Enum):
    RESEARCH = "research"
    PREPARE = "prepare"
    BUY_WITHIN_RULES = "buy_within_rules"


MODE_SCOPES = {
    AssistanceMode.RESEARCH: frozenset({"commerce:research"}),
    AssistanceMode.PREPARE: frozenset({"commerce:research", "commerce:cart"}),
    AssistanceMode.BUY_WITHIN_RULES: frozenset({"commerce:research", "commerce:cart", "commerce:purchase"}),
}
# The most an autonomy boundary may allow under each mode: a boundary only ever narrows its grant.
# The most a grant's agent may do once the member approves: only a buy grant may ever place the order.
MODE_CEILING = {
    AssistanceMode.RESEARCH: AutonomyLevel.PREPARE,  # never reached: research grants cannot request purchases
    AssistanceMode.PREPARE: AutonomyLevel.PREPARE,
    AssistanceMode.BUY_WITHIN_RULES: AutonomyLevel.BUY_AFTER_APPROVAL,
}
# Categories excluded from the default fashion scope regardless of grant text.
DEFAULT_EXCLUDED_CATEGORIES = frozenset({"gift_card", "subscription", "restricted"})


@dataclass(frozen=True)
class DelegationLimits:
    currency: str
    max_per_order: Money  # all-in total (tax + shipping included)
    max_cumulative: Money  # rolling window, including in-flight reservations
    window_seconds: int
    allowed_merchants: FrozenSet[str]
    allowed_categories: FrozenSet[str] = frozenset()  # empty = any non-excluded fashion category
    allowed_variant_refs: FrozenSet[str] = frozenset()  # empty = no variant restriction
    delivery_ref: Optional[str] = None
    payment_instrument_ref: Optional[str] = None
    require_returnable: bool = True
    allow_substitution: bool = False
    require_final_human_approval: bool = True
    refund_credit_back: bool = False
    totals_include_tax_and_shipping: bool = True

    def __post_init__(self) -> None:
        if self.max_per_order.currency != self.currency or self.max_cumulative.currency != self.currency:
            raise DelegationInvalid("delegation limits must use the grant currency")
        if not self.require_final_human_approval:
            # Autonomous purchasing requires provider + AP2 open-mandate support
            # that no configured provider has. Refuse rather than pretend.
            raise DelegationInvalid("autonomous purchase without final approval is not supported",
                                    code="autonomous_not_supported")
        if not self.totals_include_tax_and_shipping:
            raise DelegationInvalid("limits are all-in totals in this build")
        if self.allow_substitution:
            raise DelegationInvalid("substitution is not supported in this build")
        if self.window_seconds <= 0:
            raise DelegationInvalid("window must be positive")


@dataclass(frozen=True)
class AgentDelegation:
    id: str
    member_id: str
    client_id: str
    mode: AssistanceMode
    scopes: FrozenSet[str]
    allowed_providers: FrozenSet[str]
    limits: Optional[DelegationLimits]
    created_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    version: int = 1
    # The member's autonomy boundary (``autonomy.py``); None: no rules, so the agent places nothing (prepare).
    boundary: Optional[AutonomyBoundary] = None

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at

    def require_active_for(self, principal: Principal, now: datetime) -> None:
        if principal.delegation_id != self.id or principal.member_id != self.member_id \
                or principal.client_id != self.client_id:
            raise DelegationInvalid("delegation does not belong to this principal")
        if self.revoked_at is not None:
            raise DelegationInvalid("delegation revoked", code="delegation_revoked")
        if now >= self.expires_at:
            raise DelegationInvalid("delegation expired", code="delegation_expired")


def normalize_boundary(boundary: Optional[AutonomyBoundary]) -> Optional[AutonomyBoundary]:
    """An empty boundary (no rules, prepare by default, no cap) is no boundary: stored as none, valid on any grant."""
    return None if boundary is not None and not boundary.unreadable and boundary == NO_BOUNDARY else boundary


def check_boundary_fits(boundary: Optional[AutonomyBoundary], *, mode: AssistanceMode,
                        allowed_providers: FrozenSet[str], limits: Optional[DelegationLimits]) -> None:
    """A boundary belongs to a buy grant and may only narrow it: no provider or merchant the grant does not
    name, no cap above the grant's per-order limit or in another currency (and no level above the mode)."""
    if boundary is None:
        return
    if boundary.unreadable:
        raise DelegationInvalid("this boundary cannot be read; replace it", code="autonomy_boundary_unreadable")
    if mode is not AssistanceMode.BUY_WITHIN_RULES:
        # A boundary decides only who places an approved order, and only a buy grant's agent ever may.
        raise DelegationInvalid("assistant rules apply to buy-within-rules grants only",
                                code="autonomy_boundary_needs_buy_grant")
    ceiling = MODE_CEILING[mode]
    if any(LEVEL_RANK[lv] > LEVEL_RANK[ceiling]
           for lv in (boundary.default_level, *(r.level for r in boundary.rules))):
        raise DelegationInvalid(f"a {mode.value} grant allows at most the {ceiling.value} level",
                                code="autonomy_level_exceeds_mode")
    if any(r.provider_id not in allowed_providers for r in boundary.rules):
        raise DelegationInvalid("a rule names a provider the grant does not allow",
                                code="autonomy_rule_provider_not_granted")
    caps = boundary.caps()
    if caps and limits is None:
        raise DelegationInvalid("caps need a grant with purchase limits", code="autonomy_cap_exceeds_grant")
    for cap in caps:
        if cap.currency != limits.currency:
            raise DelegationInvalid("a cap must be in the grant currency", code="currency_mismatch")
        if cap.amount_minor > limits.max_per_order.amount_minor:
            raise DelegationInvalid("a cap is above the grant's per-order limit", code="autonomy_cap_exceeds_grant")
    if limits is not None and any(r.scope is RuleScope.MERCHANT and r.merchant_id not in limits.allowed_merchants
                                  for r in boundary.rules):
        raise DelegationInvalid("a rule names a merchant the grant does not allow",
                                code="autonomy_merchant_not_granted")


def build_delegation(*, granting: Principal, delegation_id: str, client_id: str,
                     mode: AssistanceMode, allowed_providers: FrozenSet[str],
                     limits: Optional[DelegationLimits], now: datetime,
                     expires_at: datetime, boundary: Optional[AutonomyBoundary] = None) -> AgentDelegation:
    """Only a first-party trusted-UI session may create a grant."""
    if is_agent(granting):
        raise Forbidden("agents cannot create or widen delegations")
    if expires_at <= now:
        raise DelegationInvalid("expiry must be in the future")
    if mode is AssistanceMode.BUY_WITHIN_RULES:
        if limits is None:
            raise DelegationInvalid("buy-within-rules requires explicit limits")
        if not limits.allowed_merchants:
            raise DelegationInvalid("buy-within-rules requires named merchants")
    boundary = normalize_boundary(boundary)
    check_boundary_fits(boundary, mode=mode, allowed_providers=frozenset(allowed_providers), limits=limits)
    return AgentDelegation(
        id=delegation_id, member_id=granting.member_id, client_id=client_id, mode=mode,
        scopes=MODE_SCOPES[mode], allowed_providers=frozenset(allowed_providers),
        limits=limits, created_at=now, expires_at=expires_at, boundary=boundary)
