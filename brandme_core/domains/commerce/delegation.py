"""Agent delegations: Research / Prepare / Buy-within-rules (ch.05 §5)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import FrozenSet, Optional, Tuple

from .errors import DelegationInvalid, Forbidden
from .money import Money
from .principal import Principal


class AssistanceMode(str, enum.Enum):
    RESEARCH = "research"
    PREPARE = "prepare"
    BUY_WITHIN_RULES = "buy_within_rules"


MODE_SCOPES = {
    AssistanceMode.RESEARCH: frozenset({"commerce:research"}),
    AssistanceMode.PREPARE: frozenset({"commerce:research", "commerce:cart"}),
    AssistanceMode.BUY_WITHIN_RULES: frozenset({"commerce:research", "commerce:cart", "commerce:purchase"}),
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


def build_delegation(*, granting: Principal, delegation_id: str, client_id: str,
                     mode: AssistanceMode, allowed_providers: FrozenSet[str],
                     limits: Optional[DelegationLimits], now: datetime,
                     expires_at: datetime) -> AgentDelegation:
    """Only a first-party trusted-UI session may create a grant."""
    if granting.is_agent:
        raise Forbidden("agents cannot create or widen delegations")
    if expires_at <= now:
        raise DelegationInvalid("expiry must be in the future")
    if mode is AssistanceMode.BUY_WITHIN_RULES:
        if limits is None:
            raise DelegationInvalid("buy-within-rules requires explicit limits")
        if not limits.allowed_merchants:
            raise DelegationInvalid("buy-within-rules requires named merchants")
    return AgentDelegation(
        id=delegation_id, member_id=granting.member_id, client_id=client_id, mode=mode,
        scopes=MODE_SCOPES[mode], allowed_providers=frozenset(allowed_providers),
        limits=limits, created_at=now, expires_at=expires_at)
