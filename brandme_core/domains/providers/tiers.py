"""B2B partner tiers: enforcement mechanics behind a pricing-table interface (Ultra plan 02 item 7).

A tier belongs to a provider connection (a brand or retailer catalog, ch.05 §7) and bounds what that
partner's own operations may do:

* **quota**: shelf size, the active variants a connection may load (``ProviderSetupService.load_shelf_page``);
* **customization**, up to 3D and AR: the presentation capabilities a partner may activate
  (``catalog.3d``, ``tryon.photo``, ``tryon.live``);
* **analytics**: which aggregate partner reports it may read;
* **member connection**: whether it may be offered a channel to members. Necessary, never
  sufficient: each member's own opt-in is still required, and it is read only after the tier passes,
  so a partner never learns a member's choice.

**No prices, no invented terms.** Tier pricing and packaging are open founder decisions. Nothing here holds an
amount: ``price_status`` can only be ``not_priced``, and a tier that is not a placeholder must name a founder
decision record (``decision_ref``), a reference, never a price. The shipped ``PLACEHOLDER_PRICING_TABLE`` has
two tiers at the two ends of every limit (nothing, and everything), so enforcement can be exercised without
inventing a quota. It is refused outside demo and development, where no tier is configured and every partner
entitlement is refused until the founder's table exists. The founder's table drops in by implementing
``PricingTable`` with no other code change.

**Fail closed.** A connection with no tier, a tier the table no longer knows, or no table at all gets nothing
beyond the standard presentation every listing has; the refusal code says which.

**Never a member-path input.** Search, ranking, quotes, approvals and purchases never read a tier
(ch.03 §6 sponsorship never negates hard constraints; ch.05 §2 eligibility never decides a style
match). Brand.Me's own operator reads are never tier-gated.
"""

from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Tuple

from .contracts import CAPABILITIES

_LOG = logging.getLogger(__name__)
LOCAL_ENVIRONMENTS = frozenset({"demo", "development"})
ASSIGNMENT_ITEM_KEY = "tier"  # ProviderSetupItems.item_key; evidence_ref "<tier_id>@<table_version>"
ASSIGNMENT_SECTION = "prerequisites"
TIER_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
TABLE_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")
DECISION_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
PLACEHOLDER_PREFIX = "placeholder_"
PRICE_LABEL = "Not priced: founder decision pending"
PLACEHOLDER_NOTICE = ("Placeholder tiers exercise enforcement only. They have no price, sit at the two ends of each "
                      "limit, and are not an offer to any brand.")


class Customization(str, enum.Enum):
    STANDARD = "standard"  # the partner's own media as supplied
    THREE_D = "three_d"  # 3D assets
    AR = "ar"  # photo and live try-on (AR)


class Analytics(str, enum.Enum):
    NONE = "none"
    CATALOG_HEALTH = "catalog_health"  # the partner's own catalog: freshness, rejections, quota use
    AGGREGATE_DEMAND = "aggregate_demand"  # consented, cohort-suppressed aggregates only (ch.01 §11)


class PriceStatus(str, enum.Enum):
    NOT_PRICED = "not_priced"  # the only value: this build holds no prices


CUSTOMIZATION_RANK = {Customization.STANDARD: 0, Customization.THREE_D: 1, Customization.AR: 2}
ANALYTICS_RANK = {Analytics.NONE: 0, Analytics.CATALOG_HEALTH: 1, Analytics.AGGREGATE_DEMAND: 2}

# The existing capability vocabulary (contracts.CAPABILITIES). A capability not listed here is never tier-gated.
CAPABILITY_CUSTOMIZATION = {"catalog.3d": Customization.THREE_D, "tryon.photo": Customization.AR,
                            "tryon.live": Customization.AR}
GATED_CAPABILITIES = frozenset(CAPABILITY_CUSTOMIZATION)

DIMENSIONS = ("shelf_variants", "customization", "analytics", "member_connection", "assignment")
ORIGINS = ("ingestion", "activation", "verification", "hydrate", "assignment", "check")
SOURCES = ("assigned", "unassigned", "assigned_unknown", "unconfigured")
ALLOW_CODES = frozenset({"tier_within_limits", "no_new_listings", "tier_assigned", "tier_cleared"})
REFUSE_CODES = frozenset({"shelf_quota_exceeded", "tier_excludes_capability", "tier_excludes_analytics",
                          "tier_excludes_member_connection", "member_consent_required", "tier_unassigned",
                          "tier_unknown", "tier_not_configured", "tier_reset_capability"})
CODES = ALLOW_CODES | REFUSE_CODES
# Why a connection without a usable tier is refused, by resolution source.
NOT_ASSIGNED_CODES = {"unassigned": "tier_unassigned", "assigned_unknown": "tier_unknown",
                      "unconfigured": "tier_not_configured"}


class TierConfigError(ValueError):
    """A pricing table or tier that breaks the invariants; ``code`` names which."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TierLimits:
    shelf_variants: Optional[int]  # active (non-tombstoned) variants per connection; None = no limit
    customization: Customization
    analytics: Analytics
    member_connection: bool  # eligible for a member channel; each member's opt-in is still required

    def __post_init__(self) -> None:
        shelf = self.shelf_variants
        if not (shelf is None or (isinstance(shelf, int) and not isinstance(shelf, bool) and shelf >= 0)) \
                or not isinstance(self.customization, Customization) or not isinstance(self.analytics, Analytics) \
                or not isinstance(self.member_connection, bool):
            raise TierConfigError("tier_field_invalid")

    def to_wire(self) -> Dict[str, Any]:
        return {"shelf_variants": self.shelf_variants, "customization": self.customization.value,
                "analytics": self.analytics.value,
                "member_connection": "eligible_with_member_opt_in" if self.member_connection else "not_included"}


@dataclass(frozen=True)
class TierDefinition:
    tier_id: str
    display_name: str
    limits: TierLimits
    placeholder: bool
    decision_ref: Optional[str] = None  # a founder pricing-decision record; never an amount
    price_status: PriceStatus = PriceStatus.NOT_PRICED

    def __post_init__(self) -> None:
        if not isinstance(self.tier_id, str) or not TIER_ID_RE.match(self.tier_id):
            raise TierConfigError("tier_id_invalid")
        if self.price_status is not PriceStatus.NOT_PRICED:
            raise TierConfigError("price_not_supported")
        if self.placeholder != self.tier_id.startswith(PLACEHOLDER_PREFIX):
            raise TierConfigError("placeholder_label_mismatch")
        if self.placeholder:
            if not (self.display_name.startswith("Placeholder") and "(not priced)" in self.display_name):
                raise TierConfigError("placeholder_label_missing")
            if self.decision_ref is not None:
                raise TierConfigError("placeholder_has_decision")
        else:
            if "placeholder" in self.display_name.lower():
                raise TierConfigError("placeholder_label_mismatch")
            if not isinstance(self.decision_ref, str) or not DECISION_REF_RE.match(self.decision_ref):
                raise TierConfigError("tier_needs_founder_decision")

    def to_wire(self) -> Dict[str, Any]:
        # Operator views only. The decision record stays server-side (commercial detail, ch.05 §1).
        return {"tier_id": self.tier_id, "display_name": self.display_name, "placeholder": self.placeholder,
                "price_status": self.price_status.value, "price_label": PRICE_LABEL,
                "includes": self.limits.to_wire()}


class PricingTable(Protocol):
    """The interface the founder's priced table implements; enforcement reads nothing else."""
    table_version: str

    def get(self, tier_id: str) -> Optional[TierDefinition]: ...

    def tiers(self) -> Tuple[TierDefinition, ...]: ...


@dataclass(frozen=True)
class StaticPricingTable:
    table_version: str
    definitions: Tuple[TierDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.table_version, str) or not TABLE_VERSION_RE.match(self.table_version):
            raise TierConfigError("table_version_invalid")
        ids = [t.tier_id for t in self.definitions]
        if len(set(ids)) != len(ids):
            raise TierConfigError("duplicate_tier")
        if len({t.placeholder for t in self.definitions}) > 1:
            raise TierConfigError("mixed_placeholder_table")

    def get(self, tier_id: str) -> Optional[TierDefinition]:
        return next((t for t in self.definitions if t.tier_id == tier_id), None)

    def tiers(self) -> Tuple[TierDefinition, ...]:
        return self.definitions


# The two ends of every limit: enough to exercise each gate both ways, with no invented quota in between.
PLACEHOLDER_PRICING_TABLE = StaticPricingTable("placeholder-1", (
    TierDefinition("placeholder_floor", "Placeholder floor (not priced)",
                   TierLimits(0, Customization.STANDARD, Analytics.NONE, False), placeholder=True),
    TierDefinition("placeholder_ceiling", "Placeholder ceiling (not priced)",
                   TierLimits(None, Customization.AR, Analytics.AGGREGATE_DEMAND, True), placeholder=True),
))
UNCONFIGURED_PRICING_TABLE = StaticPricingTable("unconfigured", ())
# What a connection gets without a usable tier: nothing beyond the standard presentation every listing has.
NO_TIER = TierLimits(0, Customization.STANDARD, Analytics.NONE, False)


def pricing_table_for(environment: str, table: Optional[PricingTable] = None) -> PricingTable:
    """The table for an environment. Placeholder tiers exist only in demo and development; elsewhere,
    until the founder's table is supplied, no tier is configured and every entitlement is refused."""
    if table is None:
        return PLACEHOLDER_PRICING_TABLE if environment in LOCAL_ENVIRONMENTS else UNCONFIGURED_PRICING_TABLE
    # Any implementation (not only StaticPricingTable) must be one every decision line can record.
    version = getattr(table, "table_version", None)
    if not isinstance(version, str) or not TABLE_VERSION_RE.match(version):
        raise TierConfigError("table_version_invalid")
    tiers = table.tiers()
    if not all(isinstance(t, TierDefinition) for t in tiers):
        raise TierConfigError("tier_definition_invalid")
    if len({t.tier_id for t in tiers}) != len(tiers):
        raise TierConfigError("duplicate_tier")
    if environment not in LOCAL_ENVIRONMENTS and (not tiers or any(t.placeholder for t in tiers)):
        raise TierConfigError("placeholder_pricing_table_refused")
    return table


def is_placeholder(table: PricingTable) -> bool:
    tiers = table.tiers()
    return bool(tiers) and all(t.placeholder for t in tiers)


@dataclass(frozen=True)
class ResolvedTier:
    tier_id: Optional[str]
    limits: TierLimits
    source: str  # assigned | unassigned | assigned_unknown | unconfigured
    table_version: str
    placeholder: bool
    assigned_at: Optional[datetime] = None

    @property
    def assigned(self) -> bool:
        return self.source == "assigned"

    def to_wire(self) -> Dict[str, Any]:
        return {"tier_id": self.tier_id, "source": self.source, "table_version": self.table_version,
                "placeholder": self.placeholder, "price_status": PriceStatus.NOT_PRICED.value,
                "price_label": PRICE_LABEL, "includes": self.limits.to_wire(),
                "label": PLACEHOLDER_NOTICE if self.placeholder else None}


def assignment_value(tier_id: str, table: PricingTable) -> str:
    return f"{tier_id}@{table.table_version}"


def resolve_from_items(items: Mapping[str, Any], table: PricingTable) -> ResolvedTier:
    """The tier recorded in a connection's setup items, under ``table``. Fails closed: no table, no assignment,
    or an assignment the table no longer knows (another tier id or table version) all give ``NO_TIER``."""
    if not table.tiers():
        return ResolvedTier(None, NO_TIER, "unconfigured", table.table_version, False)
    item = items.get(ASSIGNMENT_ITEM_KEY)
    if item is None or not getattr(item, "done", False) or not getattr(item, "evidence_ref", None):
        return ResolvedTier(None, NO_TIER, "unassigned", table.table_version, False)
    tier_id, _, version = str(item.evidence_ref).partition("@")
    tier = table.get(tier_id)
    if tier is None or version != table.table_version:
        return ResolvedTier(None, NO_TIER, "assigned_unknown", table.table_version, False,
                            getattr(item, "recorded_at", None))
    return ResolvedTier(tier.tier_id, tier.limits, "assigned", table.table_version, tier.placeholder,
                        getattr(item, "recorded_at", None))


# ------------------------------------------------------------------------------- checks
@dataclass(frozen=True)
class TierDecision:
    allowed: bool
    dimension: str
    code: str

    @property
    def outcome(self) -> str:
        return "allow" if self.allowed else "refuse"


def _decide(tier: ResolvedTier, dimension: str, ok: bool, refuse_code: str) -> TierDecision:
    if not tier.assigned:
        return TierDecision(False, dimension, NOT_ASSIGNED_CODES[tier.source])
    return TierDecision(ok, dimension, "tier_within_limits" if ok else refuse_code)


def check_capability(tier: ResolvedTier, capability: str) -> TierDecision:
    """Activation of a presentation capability (3D, AR try-on). Ungated capabilities always pass."""
    needed = CAPABILITY_CUSTOMIZATION.get(capability)
    if needed is None:
        return TierDecision(True, "customization", "tier_within_limits")
    ok = CUSTOMIZATION_RANK[tier.limits.customization] >= CUSTOMIZATION_RANK[needed]
    return _decide(tier, "customization", ok, "tier_excludes_capability")


def shelf_decision(tier: ResolvedTier, *, requested: int, refused: int) -> Tuple[str, str]:
    """``(outcome, code)`` for one catalog page: ``requested`` additions to the shelf, ``refused`` of them."""
    if requested == 0:
        return "allow", "no_new_listings"
    if refused == 0:
        return "allow", "tier_within_limits"
    code = "shelf_quota_exceeded" if tier.assigned else NOT_ASSIGNED_CODES[tier.source]
    return ("refuse" if refused == requested else "partial"), code


def check_analytics(tier: ResolvedTier, report: Analytics) -> TierDecision:
    """No caller yet (the partner analytics surface is not built). Passing the tier gate is not enough
    for member-derived reports: consent, aggregation and small-cohort suppression stay the caller's duty."""
    if report is Analytics.NONE:
        raise ValueError("name the report being read")
    ok = ANALYTICS_RANK[tier.limits.analytics] >= ANALYTICS_RANK[report]
    return _decide(tier, "analytics", ok, "tier_excludes_analytics")


def check_member_connection(tier: ResolvedTier, read_opt_in: Callable[[], bool]) -> TierDecision:
    """No caller yet. The tier is checked first and ``read_opt_in`` is called only once it passes, so a
    refusal below the tier never depends on, or reveals, what the member chose."""
    gate = _decide(tier, "member_connection", tier.limits.member_connection, "tier_excludes_member_connection")
    if not gate.allowed:
        return gate
    opted_in = read_opt_in() is True
    return TierDecision(opted_in, "member_connection", "tier_within_limits" if opted_in else "member_consent_required")


# ------------------------------------------------------------------------------- log record
TierAuditSink = Callable[[Dict[str, Any]], None]


def decision_record(*, origin: str, dimension: str, outcome: str, code: str, provider_id: str, tier: ResolvedTier,
                    actor_ref: Optional[str] = None, capability: Optional[str] = None,
                    units_requested: Optional[int] = None, units_refused: Optional[int] = None,
                    request_id: Optional[str] = None) -> Dict[str, Any]:
    """A ``provider.tier_decision`` run-log record: keyed refs, codes and counts; never prices or raw ids."""
    from brandme_core.mcp.refs import log_ref  # lazy: brandme_core.mcp imports the commerce service
    assert capability is None or capability in CAPABILITIES
    if request_id is None:  # the calling request (the domain HTTP API sets it), so lines join its audit
        from brandme_core.domains.commerce.autonomy import current_decision_context  # leaf module, lazy
        request_id = current_decision_context().request_id
    return {"request_id": request_id, "origin": origin, "dimension": dimension, "outcome": outcome, "code": code,
            "provider_ref": log_ref("provider", provider_id),
            "actor_ref": log_ref("operator", actor_ref) if actor_ref else None,
            "tier_id": tier.tier_id, "tier_source": tier.source, "placeholder": tier.placeholder,
            "table_version": tier.table_version, "capability": capability,
            "units_requested": units_requested, "units_refused": units_refused}


def emit(sink: Optional[TierAuditSink], record: Dict[str, Any]) -> None:
    """Writes one decision line, after the operation it records. An operational sink failure never fails
    the operation; a strict (test) log refusing a malformed line (``strict_violation``) is a bug and raises."""
    if sink is None:
        return
    try:
        sink(record)
    except Exception as exc:
        if getattr(exc, "strict_violation", False):
            raise
        _LOG.warning("tier decision sink failed: %s", type(exc).__name__)
