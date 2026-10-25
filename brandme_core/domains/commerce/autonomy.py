"""Member-set autonomy boundaries for agent grants (Ultra plan 02 item 6; ch.05 §3, §5).

A boundary narrows what an agent may do *without asking first* inside a grant. It never replaces
the member's approval: every purchase still needs a trusted-surface approval or a member-signed
AP2 closed mandate (ch.05 §3, ADR-14), and a level that would skip it is refused with
``autonomous_not_supported``. Inside a boundary the concierge prepares on its own and, at the
``buy_after_approval`` level, places the exact quote the member approved. Outside it the agent is
refused, or its request is *held*: the approval binds to the member, who completes the purchase.

* **Rules** name a merchant (``provider_id`` + ``merchant_id``, the identities sealed into every
  quote; provider brand text is never an identity) or a wishlist (exact ``source_variant_ref``
  values at one provider, pinned by the member: commerce never reads the wardrobe). Each rule has a
  level and an optional all-in cap. Everything no rule names gets the default level, ``prepare``:
  the concierge prepares by default.
* **The evaluator** is pure (no clock, store or context): ``evaluate`` returns allow, hold or
  refuse with fixed codes. When several rules match, the most restrictive level and the lowest cap
  apply. The grant's mode is the ceiling and its limits stay the outer bound.
* **Growth** happens only through the member's explicit change (``classify_change`` tells a
  narrowing from a widening; nothing in this build widens a boundary on its own).

This module imports only ``money`` and ``errors``.
"""

from __future__ import annotations

import contextvars
import enum
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, Iterator, Mapping, Optional, Tuple

from .errors import DelegationInvalid, InvalidRequest
from .money import Money, MoneyError

EVALUATOR_VERSION = "1.0.0"
ASSISTANT_CLIENT_ID = "brandme-assistant"  # Brand.Me's own concierge; every other client is external
BOUNDARY_SCHEMA = "brandme.autonomy_boundary.v1"
STORAGE_KEY = "autonomy_boundary"  # the key inside the AgentDelegations.limits JSON document
MAX_RULES, MAX_WISHLIST_REFS, MAX_TOTAL_REFS = 20, 200, 500
# Levels that would let an agent buy without the member's approval: refused, never stored.
UNSUPPORTED_LEVELS = frozenset({"buy_without_approval", "autonomous", "unattended"})

PROVIDER_ID_RE = re.compile(r"^[a-z0-9_]{1,80}$")
# Exact ASCII identities, compared byte for byte and never normalized (no case folding, no NFKC).
REF_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,256}$")


class AutonomyLevel(str, enum.Enum):
    SUGGEST = "suggest"  # search and report; build nothing
    PREPARE = "prepare"  # carts, quotes and approval requests; the member completes
    BUY_AFTER_APPROVAL = "buy_after_approval"  # also place the exact quote the member approved


LEVEL_RANK = {AutonomyLevel.SUGGEST: 0, AutonomyLevel.PREPARE: 1, AutonomyLevel.BUY_AFTER_APPROVAL: 2}


class RuleScope(str, enum.Enum):
    MERCHANT = "merchant"
    WISHLIST = "wishlist"


class Action(str, enum.Enum):
    CART_PREPARE = "cart_prepare"
    QUOTE = "quote"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_BINDING = "approval_binding"
    EXECUTE = "execute"
    # Not evaluated: the member placing a purchase their concierge prepared (a research signal).
    MEMBER_COMPLETION = "member_completion"


REQUIRED_LEVEL = {
    Action.MEMBER_COMPLETION: AutonomyLevel.SUGGEST,
    Action.CART_PREPARE: AutonomyLevel.PREPARE, Action.QUOTE: AutonomyLevel.PREPARE,
    Action.APPROVAL_REQUEST: AutonomyLevel.PREPARE, Action.APPROVAL_BINDING: AutonomyLevel.BUY_AFTER_APPROVAL,
    Action.EXECUTE: AutonomyLevel.BUY_AFTER_APPROVAL,
}
_CAPPED_ACTIONS = frozenset({Action.APPROVAL_REQUEST, Action.APPROVAL_BINDING, Action.EXECUTE})


class Outcome(str, enum.Enum):
    REFUSE = "refuse"
    HOLD = "hold"
    ALLOW = "allow"


OUTCOME_RANK = {Outcome.REFUSE: 0, Outcome.HOLD: 1, Outcome.ALLOW: 2}

# Closed vocabularies. ``CODES`` is in priority order: a decision's primary code is the first present.
# ``autonomy_held_for_member`` is the service's, never the evaluator's: an agent executing an approval
# the member's rules bound to the member.
CODES = ("autonomy_boundary_unreadable", "autonomy_held_for_member", "autonomy_level_suggest_only",
         "autonomy_level_prepare_only",
         "autonomy_cap_currency_differs", "over_autonomy_cap", "autonomy_total_unknown",
         "autonomy_mode_ceiling", "within_boundary", "grant_limits_only", "completed_by_member")
ALLOW_CODES = frozenset({"within_boundary", "grant_limits_only", "completed_by_member"})
SCOPES = ("no_boundary", "default", "merchant", "wishlist", "merchant_and_wishlist", "unreadable")
CAP_BUCKETS = ("no_total", "no_cap", "currency_differs", "le_50", "le_80", "le_100", "over")
CHANGES = ("unchanged", "narrowing", "widening")
WAIT_BANDS = ("lt_1m", "lt_10m", "lt_1h", "lt_24h", "ge_24h")


def wait_band(seconds: float) -> str:
    """How long the member took to approve, as a band (the log never carries times)."""
    for limit, band in ((60, "lt_1m"), (600, "lt_10m"), (3600, "lt_1h"), (86400, "lt_24h")):
        if seconds < limit:
            return band
    return "ge_24h"


def _invalid(detail: str) -> InvalidRequest:
    return InvalidRequest(detail, code="invalid_autonomy_boundary")


def _level(raw: Any) -> AutonomyLevel:
    if isinstance(raw, AutonomyLevel):
        return raw
    if isinstance(raw, str) and raw in UNSUPPORTED_LEVELS:
        raise DelegationInvalid("an agent cannot buy without the member's approval in this build",
                                code="autonomous_not_supported")
    try:
        return AutonomyLevel(raw)
    except ValueError:
        raise _invalid("unknown autonomy level") from None


@dataclass(frozen=True)
class ActionFacts:
    """What an agent is about to do, from the sealed quote or the validated cart (never model text)."""
    action: Action
    provider_id: str
    merchant_id: str
    variant_refs: FrozenSet[str]
    total: Optional[Money] = None  # the sealed quote's all-in total; None before a quote exists


@dataclass(frozen=True)
class BoundaryRule:
    scope: RuleScope
    provider_id: str
    level: AutonomyLevel
    merchant_id: Optional[str] = None  # MERCHANT only
    variant_refs: FrozenSet[str] = frozenset()  # WISHLIST only: 1..MAX_WISHLIST_REFS exact refs
    max_total: Optional[Money] = None  # all-in per-order cap; None = no boundary cap

    def __post_init__(self) -> None:
        if not isinstance(self.scope, RuleScope) or not isinstance(self.level, AutonomyLevel):
            raise DelegationInvalid("rule scope and level must be closed values", code="autonomy_rule_invalid")
        if not isinstance(self.provider_id, str) or not PROVIDER_ID_RE.match(self.provider_id):
            raise DelegationInvalid("rule needs a provider id", code="autonomy_rule_invalid")
        if self.scope is RuleScope.MERCHANT:
            if not isinstance(self.merchant_id, str) or not REF_RE.match(self.merchant_id) or self.variant_refs:
                raise DelegationInvalid("a merchant rule names exactly one merchant", code="autonomy_rule_invalid")
        else:
            if self.merchant_id is not None or not self.variant_refs:
                raise DelegationInvalid("a wishlist rule names variants, not a merchant",
                                        code="autonomy_rule_invalid")
            if len(self.variant_refs) > MAX_WISHLIST_REFS:
                raise DelegationInvalid("too many wishlist variants in one rule", code="autonomy_boundary_too_large")
            if not all(isinstance(r, str) and REF_RE.match(r) for r in self.variant_refs):
                raise DelegationInvalid("a wishlist variant ref is malformed", code="autonomy_rule_invalid")
        if self.max_total is not None and not isinstance(self.max_total, Money):
            raise DelegationInvalid("a cap must be money", code="autonomy_rule_invalid")

    def key(self) -> Tuple[str, str, str]:
        return (self.scope.value, self.provider_id, self.merchant_id or "")

    def matches(self, f: ActionFacts) -> bool:
        if self.provider_id != f.provider_id:
            return False
        if self.scope is RuleScope.MERCHANT:
            return self.merchant_id == f.merchant_id
        return bool(f.variant_refs) and f.variant_refs <= self.variant_refs  # every line on the wishlist

    def to_wire(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"scope": self.scope.value, "provider_id": self.provider_id, "level": self.level.value,
                               "max_total": self.max_total.to_wire() if self.max_total else None}
        if self.scope is RuleScope.MERCHANT:
            out["merchant_id"] = self.merchant_id
        else:
            out["variant_refs"] = sorted(self.variant_refs)
        return out


_RULE_KEYS = {RuleScope.MERCHANT: {"scope", "provider_id", "merchant_id", "level", "max_total"},
              RuleScope.WISHLIST: {"scope", "provider_id", "variant_refs", "level", "max_total"}}


@dataclass(frozen=True)
class AutonomyBoundary:
    default_level: AutonomyLevel = AutonomyLevel.PREPARE
    default_max_total: Optional[Money] = None
    rules: Tuple[BoundaryRule, ...] = ()
    # Load-only sentinel: a stored document this build cannot read evaluates fail-closed and is
    # written back verbatim (a newer schema survives a rolling deploy).
    unreadable: bool = False
    stored: Optional[Mapping[str, Any]] = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.unreadable:
            return
        if not isinstance(self.default_level, AutonomyLevel):
            raise DelegationInvalid("default level must be a closed value", code="autonomy_rule_invalid")
        rules = tuple(sorted(self.rules, key=BoundaryRule.key))
        object.__setattr__(self, "rules", rules)  # canonical: equal boundaries compare equal
        if len(rules) > MAX_RULES:
            raise DelegationInvalid("too many boundary rules", code="autonomy_boundary_too_large")
        if sum(len(r.variant_refs) for r in rules) > MAX_TOTAL_REFS:
            raise DelegationInvalid("too many wishlist variants", code="autonomy_boundary_too_large")
        if len({r.key() for r in rules}) != len(rules):
            raise DelegationInvalid("each merchant, and each provider's wishlist, appears once",
                                    code="autonomy_rule_duplicate")
        if len({c.currency for c in self.caps()}) > 1:
            raise DelegationInvalid("caps must share one currency", code="autonomy_cap_currency_mixed")

    def caps(self) -> Tuple[Money, ...]:
        return tuple(c for c in (self.default_max_total, *(r.max_total for r in self.rules)) if c is not None)

    @property
    def currency(self) -> Optional[str]:
        caps = self.caps()
        return caps[0].currency if caps else None

    # -- wire (gateway / trusted surface) -------------------------------------------
    def to_wire(self) -> Dict[str, Any]:
        if self.unreadable:
            return {"unreadable": True}
        return {"default_level": self.default_level.value,
                "default_max_total": self.default_max_total.to_wire() if self.default_max_total else None,
                "rules": [r.to_wire() for r in self.rules]}

    @classmethod
    def from_wire(cls, raw: Any) -> "AutonomyBoundary":
        if not isinstance(raw, Mapping) or not set(raw) <= {"default_level", "default_max_total", "rules"}:
            raise _invalid("a boundary is {default_level, default_max_total, rules}")
        rules_raw = raw.get("rules", [])
        if not isinstance(rules_raw, list) or len(rules_raw) > MAX_RULES:
            raise _invalid("rules must be a list of at most %d entries" % MAX_RULES)
        return cls(default_level=_level(raw.get("default_level", AutonomyLevel.PREPARE.value)),
                   default_max_total=_money_or_none(raw.get("default_max_total")),
                   rules=tuple(_rule_from_wire(r) for r in rules_raw))

    # -- storage (inside the AgentDelegations.limits JSON) ----------------------------
    def to_storage(self) -> Dict[str, Any]:
        if self.unreadable:
            return dict(self.stored or {})
        return {"schema": BOUNDARY_SCHEMA, "currency": self.currency, "default_level": self.default_level.value,
                "default_max_total_minor": self.default_max_total.amount_minor if self.default_max_total else None,
                "rules": [{"scope": r.scope.value, "provider_id": r.provider_id, "merchant_id": r.merchant_id,
                           "variant_refs": sorted(r.variant_refs), "level": r.level.value,
                           "max_total_minor": r.max_total.amount_minor if r.max_total else None}
                          for r in self.rules]}

    @classmethod
    def from_storage(cls, raw: Any) -> "AutonomyBoundary":
        """Never raises: a document this build cannot read loads as the fail-closed sentinel."""
        try:
            if not isinstance(raw, Mapping) or raw.get("schema") != BOUNDARY_SCHEMA:
                raise ValueError("unknown boundary schema")
            currency = raw["currency"]

            def cap(v: Any) -> Optional[Money]:
                if v is None:
                    return None
                if isinstance(v, bool) or not isinstance(v, int) or not isinstance(currency, str):
                    raise ValueError("bad cap")
                return Money(v, currency)

            rules = []
            for r in raw["rules"]:
                scope = RuleScope(r["scope"])
                rules.append(BoundaryRule(scope=scope, provider_id=r["provider_id"], level=AutonomyLevel(r["level"]),
                                          merchant_id=r["merchant_id"] if scope is RuleScope.MERCHANT else None,
                                          variant_refs=frozenset(r["variant_refs"]),
                                          max_total=cap(r["max_total_minor"])))
            return cls(default_level=AutonomyLevel(raw["default_level"]),
                       default_max_total=cap(raw["default_max_total_minor"]), rules=tuple(rules))
        except Exception:  # unreadable: fail closed, keep the document
            return cls(unreadable=True, stored=dict(raw) if isinstance(raw, Mapping) else {"value": raw})


def _money_or_none(raw: Any) -> Optional[Money]:
    if raw is None:
        return None
    try:
        return Money.from_wire(raw)
    except MoneyError:
        raise _invalid("a cap must be {amount_minor, currency}") from None


def _rule_from_wire(raw: Any) -> BoundaryRule:
    if not isinstance(raw, Mapping):
        raise _invalid("each rule is an object")
    try:
        scope = RuleScope(raw.get("scope"))
    except ValueError:
        raise _invalid("rule scope is merchant or wishlist") from None
    required = _RULE_KEYS[scope] - {"max_total"}
    if not required <= set(raw) <= _RULE_KEYS[scope]:
        raise _invalid(f"a {scope.value} rule is exactly {sorted(_RULE_KEYS[scope])}")
    refs = raw.get("variant_refs", [])
    if scope is RuleScope.WISHLIST and (not isinstance(refs, list) or len(refs) != len(set(refs))):
        raise _invalid("variant_refs is a list of distinct refs")
    return BoundaryRule(scope=scope, provider_id=raw["provider_id"], level=_level(raw["level"]),
                        merchant_id=raw.get("merchant_id"), variant_refs=frozenset(refs),
                        max_total=_money_or_none(raw.get("max_total")))


# ----------------------------------------------------------------------------- evaluation
@dataclass(frozen=True)
class AutonomyDecision:
    action: Action
    outcome: Outcome
    level: AutonomyLevel
    required_level: AutonomyLevel
    scope: str
    codes: Tuple[str, ...]
    cap_bucket: str
    rule_count: int = 0

    @property
    def primary_code(self) -> str:
        return self.codes[0]

    @property
    def allowed(self) -> bool:
        return self.outcome is Outcome.ALLOW


def cap_bucket(total: Optional[Money], cap: Optional[Money]) -> str:
    """How close the total is to the cap, from integers only (the log never carries amounts)."""
    if total is None:
        return "no_total"
    if cap is None:
        return "no_cap"
    if total.currency != cap.currency:
        return "currency_differs"
    t, c = total.amount_minor, cap.amount_minor
    if 2 * t <= c:
        return "le_50"
    if 5 * t <= 4 * c:
        return "le_80"
    return "le_100" if t <= c else "over"


def _min_level(levels) -> AutonomyLevel:
    return min(levels, key=LEVEL_RANK.__getitem__)


def _min_cap(caps) -> Optional[Money]:
    present = [c for c in caps if c is not None]
    if not present:
        return None
    if len({c.currency for c in present}) > 1:  # unreachable for a validated boundary; fail closed
        return Money(0, present[0].currency)
    return min(present, key=lambda c: c.amount_minor)


def evaluate(boundary: Optional[AutonomyBoundary], ceiling: AutonomyLevel, facts: ActionFacts) -> AutonomyDecision:
    """Pure: the decision for one agent action under the member's boundary and the grant's mode ceiling."""
    required = REQUIRED_LEVEL[facts.action]
    codes = []
    cap: Optional[Money] = None
    rule_count = 0
    if boundary is None:
        level, scope = ceiling, "no_boundary"
    elif boundary.unreadable:
        level, scope = AutonomyLevel.SUGGEST, "unreadable"
        codes.append("autonomy_boundary_unreadable")
    else:
        rule_count = len(boundary.rules)
        matched = [r for r in boundary.rules if r.matches(facts)]
        if matched:
            level = _min_level(r.level for r in matched)
            cap = _min_cap(r.max_total for r in matched)
            kinds = {r.scope for r in matched}
            scope = "merchant_and_wishlist" if len(kinds) == 2 else next(iter(kinds)).value
        else:
            level, cap, scope = boundary.default_level, boundary.default_max_total, "default"
    if LEVEL_RANK[level] > LEVEL_RANK[ceiling]:  # defence in depth: writes already refuse this
        level = ceiling
        codes.append("autonomy_mode_ceiling")
    outcome = Outcome.ALLOW
    if LEVEL_RANK[level] < LEVEL_RANK[required]:
        codes.append("autonomy_level_suggest_only" if level is AutonomyLevel.SUGGEST
                     else "autonomy_level_prepare_only")
        outcome = Outcome.HOLD if facts.action is Action.APPROVAL_BINDING else Outcome.REFUSE
    if facts.action in _CAPPED_ACTIONS and cap is not None:
        over = None
        if facts.total is None:
            over = "autonomy_total_unknown"
        elif facts.total.currency != cap.currency:
            over = "autonomy_cap_currency_differs"
        elif facts.total.amount_minor > cap.amount_minor:
            over = "over_autonomy_cap"
        if over:
            codes.append(over)
            capped = Outcome.REFUSE if facts.action is Action.EXECUTE else Outcome.HOLD
            outcome = min(outcome, capped, key=OUTCOME_RANK.__getitem__)
    if outcome is Outcome.ALLOW:
        codes.append("grant_limits_only" if boundary is None else "within_boundary")
    ordered = tuple(c for c in CODES if c in codes)
    return AutonomyDecision(facts.action, outcome, level, required, scope, ordered,
                            cap_bucket(facts.total, cap), rule_count)


# ----------------------------------------------------------------------------- change
def _le_cap(new: Optional[Money], old: Optional[Money]) -> bool:
    """new <= old where None means no cap (infinite); a currency change never counts as <=."""
    if old is None:
        return True
    if new is None:
        return False
    return new.currency == old.currency and new.amount_minor <= old.amount_minor


def _le_level(new: AutonomyLevel, old: AutonomyLevel) -> bool:
    return LEVEL_RANK[new] <= LEVEL_RANK[old]


def classify_change(old: Optional[AutonomyBoundary], new: Optional[AutonomyBoundary]) -> str:
    """``unchanged``, ``narrowing`` (no action gets a more permissive outcome) or ``widening``.

    Conservative: anything not provably narrowing is a widening. With no boundary the grant's mode
    ceiling applies with no cap, so ``None -> B`` narrows and ``B -> None`` widens.
    """
    if old == new and not (old is not None and old.unreadable):
        return "unchanged"
    if new is None:
        return "widening"
    if new.unreadable:
        return "widening"
    if old is None:
        return "narrowing"
    if old.unreadable:
        return "widening"
    if not (_le_level(new.default_level, old.default_level) and _le_cap(new.default_max_total, old.default_max_total)):
        return "widening"  # S1
    old_rules = {r.key(): r for r in old.rules}
    new_rules = {r.key(): r for r in new.rules}
    if set(old_rules) - set(new_rules):
        return "widening"  # S3: a removed rule frees what it restricted
    for k, n in new_rules.items():
        o = old_rules.get(k)
        if o is not None:  # S2: same match set, no higher level or cap
            if n.variant_refs != o.variant_refs or not _le_level(n.level, o.level) or not _le_cap(n.max_total, o.max_total):
                return "widening"
        elif not (_le_level(n.level, old.default_level) and _le_cap(n.max_total, old.default_max_total)):
            return "widening"  # S4: a new rule no looser than the old default
    return "narrowing"


# ----------------------------------------------------------------------------- record context
@dataclass(frozen=True)
class DecisionContext:
    """Where a decision came from, for its log line only; ``evaluate`` never reads it."""
    origin: str = "service"  # mcp | assistant | api | service
    request_id: Optional[str] = None
    task_id: Optional[str] = None
    step: Optional[int] = None


_CONTEXT: contextvars.ContextVar[DecisionContext] = contextvars.ContextVar("autonomy_decision_context",
                                                                          default=DecisionContext())


@contextmanager
def decision_context(*, origin: str, request_id: Optional[str] = None, task_id: Optional[str] = None,
                     step: Optional[int] = None) -> Iterator[None]:
    token = _CONTEXT.set(DecisionContext(origin, request_id, task_id, step))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def current_decision_context() -> DecisionContext:
    return _CONTEXT.get()


AutonomyDecisionSink = Callable[[Dict[str, Any]], None]
