"""Autonomy boundaries (Ultra plan 02 item 6; ch.05 §3, §5; ADR-14).

A member sets per-merchant and per-wishlist rules for an assistant grant: a level (suggest, prepare,
buy_after_approval) and an optional all-in cap, defaulting to prepare. The commerce service enforces
them on every agent write path; nothing lets an agent buy without the member's approval; a boundary
grows only through the member's explicit change; every decision leaves one closed-schema line.

All-in demo totals (8% tax, no shipping): overshirt 9612, sneaker 10692, trousers 12852, bag 13932,
dress 17172, jacket 19332, overshirt + bag 23544, jacket + bag 33264.
"""

import json
import random
import uuid
from datetime import timedelta

import pytest

from brandme_core.domains.commerce import autonomy as A
from brandme_core.domains.commerce.autonomy import (
    Action, ActionFacts, AutonomyBoundary, AutonomyLevel, BoundaryRule, Outcome, RuleScope, classify_change, evaluate,
)
from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.errors import (
    ApprovalInvalid, DelegationInvalid, Forbidden, InvalidRequest, ProcessingRestricted, VersionConflict,
)
from brandme_core.domains.commerce.money import Money
from brandme_core.domains.commerce.privacy_handler import AGENT_GRANTS
from brandme_core.domains.commerce.service import CommerceService
from brandme_core.domains.commerce.store import InMemoryCommerceStore
from brandme_core.domains.providers.local_atelier import MERCHANT_ID, PROVIDER_ID
from brandme_core.orchestrator.runlog import MemoryRunLog, RunLogViolation
from tests.fixtures.commerce.harness import (
    AGENT_CLIENT, boundary, limits, line, member_session, merchant_rule, usd, wishlist_rule, world,
)
from tests.fixtures.commerce.stores import _spanner_db, commerce_store  # noqa: F401  (fixtures)
from tests.test_commerce_privacy import my_data  # noqa: F401  (fixture)
from tests.test_commerce_privacy_freeze import fw  # noqa: F401  (fixture: memory and Spanner freezes)

BUY = AutonomyLevel.BUY_AFTER_APPROVAL


@pytest.fixture
def w(commerce_store):
    return world(store=commerce_store)


def facts(action=Action.EXECUTE, provider=PROVIDER_ID, merchant=MERCHANT_ID, refs=("demo-dress-m",), total=17172):
    return ActionFacts(action, provider, merchant, frozenset(refs), usd(total) if total is not None else None)


def approve(w, op):
    ch = w.svc.open_approval_challenge(w.member, op.id)
    return ch, w.svc.approve(w.member, operation_id=op.id, challenge_id=ch.id, nonce=ch.nonce,
                             displayed_quote_hash=ch.quote_hash)


# =========================================================================== the pure model
def test_boundary_wire_and_storage_round_trips_are_canonical():
    b = boundary(wishlist_rule("demo-dress-m", "demo-bag-m", cap=20_000), merchant_rule(cap=15_000))
    assert [r.scope for r in b.rules] == [RuleScope.MERCHANT, RuleScope.WISHLIST]  # sorted by key
    assert AutonomyBoundary.from_wire(b.to_wire()) == b
    assert AutonomyBoundary.from_storage(json.loads(json.dumps(b.to_storage()))) == b
    reordered = boundary(merchant_rule(cap=15_000), wishlist_rule("demo-bag-m", "demo-dress-m", cap=20_000))
    assert reordered == b and reordered.to_storage() == b.to_storage()
    assert b.to_wire()["rules"][1]["variant_refs"] == ["demo-bag-m", "demo-dress-m"]


@pytest.mark.parametrize("raw,code", [
    ({"rules": [{"scope": "merchant", "provider_id": "p", "merchant_id": "m", "level": "prepare"}] * 2},
     "autonomy_rule_duplicate"),
    ({"rules": [{"scope": "wishlist", "provider_id": "p", "merchant_id": "m", "variant_refs": ["r"],
                 "level": "prepare"}]}, "invalid_autonomy_boundary"),
    ({"rules": [{"scope": "wishlist", "provider_id": "p", "variant_refs": [f"r{i}" for i in range(201)],
                 "level": "prepare"}]}, "autonomy_boundary_too_large"),
    ({"default_max_total": {"amount_minor": "100", "currency": "EUR"},
      "rules": [{"scope": "merchant", "provider_id": "p", "merchant_id": "m", "level": "prepare",
                 "max_total": {"amount_minor": "100", "currency": "USD"}}]}, "autonomy_cap_currency_mixed"),
    ({"rules": [{"scope": "merchant", "provider_id": "p", "merchant_id": "fictional demo", "level": "prepare"}]},
     "autonomy_rule_invalid"),
    ({"rules": [{"scope": "merchant", "provider_id": "p", "merchant_id": "fictional-dеmo", "level": "prepare"}]},
     "autonomy_rule_invalid"),  # Cyrillic е: refused, never normalized
    ({"rules": [{"scope": "brand", "provider_id": "p", "brand": "Atelier", "level": "prepare"}]},
     "invalid_autonomy_boundary"),
    ({"rules": [], "extra": True}, "invalid_autonomy_boundary"),
    ({"default_level": "everything"}, "invalid_autonomy_boundary"),
])
def test_malformed_or_oversized_boundaries_are_refused(raw, code):
    with pytest.raises((InvalidRequest, DelegationInvalid)) as e:
        AutonomyBoundary.from_wire(raw)
    assert e.value.code == code


@pytest.mark.parametrize("raw", [
    {"default_level": "buy_without_approval"}, {"default_level": "autonomous"},
    {"rules": [{"scope": "merchant", "provider_id": "p", "merchant_id": "m", "level": "unattended"}]},
])
def test_no_level_lets_an_agent_buy_without_the_members_approval(raw):
    with pytest.raises(DelegationInvalid) as e:
        AutonomyBoundary.from_wire(raw)
    assert e.value.code == "autonomous_not_supported"


def test_the_most_restrictive_matching_rule_wins():
    b = boundary(merchant_rule(cap=15_000), wishlist_rule("demo-dress-m", cap=20_000))
    d = {a: evaluate(b, BUY, facts(a)) for a in (Action.APPROVAL_REQUEST, Action.APPROVAL_BINDING, Action.EXECUTE)}
    assert {a: (x.outcome, x.scope, x.primary_code) for a, x in d.items()} == {
        Action.APPROVAL_REQUEST: (Outcome.HOLD, "merchant_and_wishlist", "over_autonomy_cap"),
        Action.APPROVAL_BINDING: (Outcome.HOLD, "merchant_and_wishlist", "over_autonomy_cap"),
        Action.EXECUTE: (Outcome.REFUSE, "merchant_and_wishlist", "over_autonomy_cap")}
    lower_level = boundary(merchant_rule(level="prepare"), wishlist_rule("demo-dress-m"))
    assert evaluate(lower_level, BUY, facts(Action.APPROVAL_BINDING)).primary_code == "autonomy_level_prepare_only"


def test_actions_no_rule_names_fall_to_the_default_level():
    other = facts(Action.CART_PREPARE, merchant="another-fictional-merchant", total=None)
    assert evaluate(boundary(merchant_rule(), default="suggest"), BUY, other).primary_code == "autonomy_level_suggest_only"
    assert evaluate(boundary(merchant_rule(), default="suggest"), BUY, other).outcome is Outcome.REFUSE
    binding = facts(Action.APPROVAL_BINDING, merchant="another-fictional-merchant")
    held = evaluate(boundary(merchant_rule()), BUY, binding)  # default prepare: the concierge prepares
    assert (held.outcome, held.scope, held.primary_code) == (Outcome.HOLD, "default", "autonomy_level_prepare_only")
    assert evaluate(boundary(), BUY, facts(Action.CART_PREPARE, total=None)).allowed


def test_caps_are_all_in_inclusive_currency_strict_and_bounded_by_the_mode():
    b = boundary(merchant_rule(cap=17_172))
    assert evaluate(b, BUY, facts(total=17_172)).allowed  # equal is within
    assert evaluate(b, BUY, facts(total=17_173)).primary_code == "over_autonomy_cap"
    eur = ActionFacts(Action.EXECUTE, PROVIDER_ID, MERCHANT_ID, frozenset({"demo-dress-m"}), Money(100, "EUR"))
    assert evaluate(b, BUY, eur).primary_code == "autonomy_cap_currency_differs"
    assert evaluate(b, BUY, facts(total=None)).primary_code == "autonomy_total_unknown"
    clamped = evaluate(b, AutonomyLevel.PREPARE, facts(Action.APPROVAL_BINDING, total=100))
    assert clamped.codes == ("autonomy_level_prepare_only", "autonomy_mode_ceiling") and clamped.outcome is Outcome.HOLD
    assert evaluate(None, BUY, facts()).codes == ("grant_limits_only",)
    assert evaluate(None, AutonomyLevel.PREPARE, facts(Action.APPROVAL_BINDING)).outcome is Outcome.HOLD
    buckets = [A.cap_bucket(usd(t), usd(c)) for t, c in [(50, 100), (51, 100), (80, 100), (81, 100), (100, 100),
                                                          (101, 100)]]
    assert buckets == ["le_50", "le_80", "le_80", "le_100", "le_100", "over"]
    assert (A.cap_bucket(None, usd(1)), A.cap_bucket(usd(1), None)) == ("no_total", "no_cap")


def test_an_unreadable_boundary_fails_closed_and_survives_verbatim():
    newer = {"schema": "brandme.autonomy_boundary.v9", "anything": [1, 2]}
    b = AutonomyBoundary.from_storage(newer)
    assert b.unreadable and b.to_storage() == newer and b.to_wire() == {"unreadable": True}
    assert evaluate(b, BUY, facts(Action.CART_PREPARE, total=None)).primary_code == "autonomy_boundary_unreadable"
    assert evaluate(b, BUY, facts(Action.APPROVAL_BINDING)).outcome is Outcome.HOLD
    assert AutonomyBoundary.from_storage({"schema": A.BOUNDARY_SCHEMA, "rules": "corrupt"}).unreadable
    assert classify_change(b, boundary()) == "widening"  # replacing it is the member's explicit change


# ----------------------------------------------------------------------- narrowing is sound
_PROVIDERS, _MERCHANTS, _REFS, _CAPS = ("demo_atelier", "other_shop"), ("m1", "m2"), ("r1", "r2", "r3"), (None, 5000, 10000)
_LEVELS = list(AutonomyLevel)


def _random_rule(rnd, key):
    kind, provider, merchant = key
    level, cap = rnd.choice(_LEVELS), usd(rnd.choice(_CAPS))
    if kind == "merchant":
        return BoundaryRule(RuleScope.MERCHANT, provider, level, merchant_id=merchant, max_total=cap)
    refs = frozenset(rnd.sample(_REFS, rnd.randint(1, 3)))
    return BoundaryRule(RuleScope.WISHLIST, provider, level, variant_refs=refs, max_total=cap)


_KEYS = [("merchant", p, m) for p in _PROVIDERS for m in _MERCHANTS] + [("wishlist", p, "") for p in _PROVIDERS]


def _random_boundary(rnd):
    keys = rnd.sample(_KEYS, rnd.randint(0, len(_KEYS)))
    return AutonomyBoundary(rnd.choice(_LEVELS), usd(rnd.choice(_CAPS)), tuple(_random_rule(rnd, k) for k in keys))


def _mutate(rnd, b):
    rules = {r.key(): r for r in b.rules}
    default, cap = b.default_level, b.default_max_total
    for _ in range(rnd.randint(1, 3)):
        move = rnd.randrange(5)
        if move == 0:
            default = rnd.choice(_LEVELS)
        elif move == 1:
            cap = usd(rnd.choice(_CAPS))
        elif move == 2 and rules:
            rules.pop(rnd.choice(sorted(rules)))
        elif move == 3:
            k = rnd.choice(_KEYS)
            rules[(k[0], k[1], k[2])] = _random_rule(rnd, k)
        elif rules:
            k = rnd.choice(sorted(rules))
            old = rules[k]
            rules[k] = BoundaryRule(old.scope, old.provider_id, rnd.choice(_LEVELS), merchant_id=old.merchant_id,
                                    variant_refs=old.variant_refs, max_total=usd(rnd.choice(_CAPS)))
    return AutonomyBoundary(default, cap, tuple(rules.values()))


def test_narrowing_classification_is_sound_against_the_evaluator():
    """No action gets a more permissive outcome under a change classified as narrowing (3000 seeded pairs)."""
    rnd = random.Random(20261025)
    counts = {"narrowing": 0, "widening": 0, "unchanged": 0}
    for _ in range(3000):
        old = _random_boundary(rnd)
        new = _mutate(rnd, old) if rnd.random() < 0.9 else None
        change = classify_change(old, new)
        counts[change] += 1
        if change != "narrowing":
            continue
        for _ in range(40):
            action = rnd.choice(list(Action))
            refs = frozenset(rnd.sample(_REFS, rnd.randint(1, 3)))
            total = None if action in (Action.CART_PREPARE, Action.QUOTE) else usd(rnd.choice((3000, 7000, 12000)))
            f = ActionFacts(action, rnd.choice(_PROVIDERS), rnd.choice(_MERCHANTS), refs, total)
            before, after = evaluate(old, BUY, f), evaluate(new, BUY, f)
            assert A.OUTCOME_RANK[after.outcome] <= A.OUTCOME_RANK[before.outcome], (old, new, f)
    assert counts["narrowing"] >= 100 and counts["widening"] >= 100, counts


def test_classify_change_examples():
    base = boundary(merchant_rule(cap=15_000), wishlist_rule("demo-dress-m", level="prepare"))
    assert classify_change(base, base) == "unchanged"
    assert classify_change(None, base) == "narrowing" and classify_change(base, None) == "widening"
    assert classify_change(base, boundary(merchant_rule(cap=20_000), wishlist_rule("demo-dress-m", level="prepare"))) \
        == "widening"  # a higher cap
    assert classify_change(base, boundary(merchant_rule(cap=15_000))) == "widening"  # a removed restriction
    assert classify_change(base, boundary(merchant_rule(cap=15_000), wishlist_rule("demo-dress-m", "demo-bag-m",
                                                                                    level="prepare"))) == "widening"
    assert classify_change(base, boundary(merchant_rule(cap=10_000), wishlist_rule("demo-dress-m", level="prepare"),
                                          default="suggest")) == "narrowing"


# =========================================================================== the service
def test_a_boundary_must_fit_inside_its_grant(w):
    cases = [
        (AssistanceMode.BUY_WITHIN_RULES, boundary(merchant_rule(provider="another_provider")),
         "autonomy_rule_provider_not_granted"),
        (AssistanceMode.PREPARE, boundary(merchant_rule()), "autonomy_level_exceeds_mode"),
        (AssistanceMode.RESEARCH, boundary(), "autonomy_level_exceeds_mode"),
        (AssistanceMode.BUY_WITHIN_RULES, boundary(merchant_rule(cap=50_001)), "autonomy_cap_exceeds_grant"),
        (AssistanceMode.BUY_WITHIN_RULES, boundary(merchant_rule(merchant="another-merchant")),
         "autonomy_merchant_not_granted"),
        (AssistanceMode.BUY_WITHIN_RULES, AutonomyBoundary(rules=(BoundaryRule(
            RuleScope.MERCHANT, PROVIDER_ID, BUY, merchant_id=MERCHANT_ID, max_total=Money(100, "EUR")),)),
         "currency_mismatch"),
    ]
    for mode, b, code in cases:
        with pytest.raises(DelegationInvalid) as e:
            w.delegate(mode, boundary=b)
        assert e.value.code == code, (mode, code)
    assert w.store.rows("delegations") == []
    d, _ = w.delegate(AssistanceMode.PREPARE, boundary=boundary(wishlist_rule("demo-dress-m", level="prepare")))
    assert d.boundary.rules[0].variant_refs == {"demo-dress-m"}


def test_the_boundary_round_trips_through_the_store(w):
    b = boundary(merchant_rule(cap=15_000), wishlist_rule("demo-dress-m", cap=20_000), default="suggest")
    d, _ = w.delegate(boundary=b)
    assert w.store.get("delegations", d.id).boundary == b
    other = w.svc.create_delegation(w.member, client_id="client-fictional-prepare-agent", mode=AssistanceMode.PREPARE,
                                    allowed_providers={PROVIDER_ID}, limits=None,
                                    expires_at=w.clock.now + timedelta(days=1), boundary=boundary(default="prepare"))
    assert w.store.get("delegations", other.id).boundary == boundary(default="prepare")  # no limits, still kept
    plain = w.svc.create_delegation(w.member, client_id="client-fictional-plain", mode=AssistanceMode.RESEARCH,
                                    allowed_providers={PROVIDER_ID}, limits=None,
                                    expires_at=w.clock.now + timedelta(days=1))
    assert w.store.get("delegations", plain.id).boundary is None and w.store.get("delegations", plain.id).limits is None


def test_spanner_keeps_limits_and_boundary_in_one_document_and_reads_legacy_rows(_spanner_db):
    from brandme_core.domains.commerce.spanner_store import SpannerCommerceStore, _grant_from_json
    from tests.fixtures.commerce.stores import wipe
    wipe(_spanner_db)
    w = world(store=SpannerCommerceStore(_spanner_db))
    d, _ = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    with _spanner_db.snapshot() as snap:
        (raw,) = [r[0] for r in snap.execute_sql("SELECT limits FROM AgentDelegations WHERE delegation_id = @d",
                                                params={"d": d.id}, param_types={"d": __import__(
                                                    "google.cloud.spanner_v1", fromlist=["param_types"]
                                                ).param_types.STRING})]
    doc = json.loads(raw.serialize()) if hasattr(raw, "serialize") else dict(raw)
    assert doc["currency"] == "USD" and doc[A.STORAGE_KEY]["schema"] == A.BOUNDARY_SCHEMA
    legacy = {k: v for k, v in doc.items() if k != A.STORAGE_KEY}
    lim, b = _grant_from_json(json.dumps(legacy))
    assert lim == limits() and b is None


def test_suggest_level_refuses_preparation_before_provider_io(w):
    d, ag = w.delegate(boundary=boundary(default="suggest"))
    with pytest.raises(Forbidden) as e:
        w.svc.create_cart(ag, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()])
    assert e.value.code == "autonomy_level_suggest_only"
    assert w.provider._carts == {} and w.store.rows("carts") == []
    assert w.decided() == [("cart_prepare", "refuse", "autonomy_level_suggest_only")]


def test_over_cap_request_is_held_and_the_agent_cannot_complete_it(w):
    """Exit evidence (item 6): an over-cap purchase is held for the member; within the cap the agent completes it."""
    d, ag = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    _, quote, op = w.prepared(ag, line("dress"))  # 17172 > 15000
    assert op.state == "awaiting_approval"
    ch, approval = approve(w, op)
    assert (ch.completed_by, ch.autonomy_codes) == ("member", ("over_autonomy_cap",))
    assert approval.delegation_ref is None
    with pytest.raises(Forbidden) as e:
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="auto-exec-dress-0001")
    assert e.value.code == "autonomy_held_for_member"
    assert w.provider.submit_calls == [] and w.store.rows("reservations") == []
    assert w.store.get("operations", op.id).state == "approved"
    done = w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=approval.id,
                                  idempotency_key="auto-exec-dress-0002")
    assert done.state == "accepted"
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000, "USD")  # not the agent's spend

    _, quote2, op2 = w.prepared(ag, line("overshirt"))  # 9612 <= 15000
    ch2, approval2 = approve(w, op2)
    assert (ch2.completed_by, ch2.autonomy_codes, approval2.delegation_ref) == ("agent", ("within_boundary",), d.id)
    res = w.svc.execute_purchase(ag, operation_id=op2.id, approval_id=approval2.id,
                                 idempotency_key="auto-exec-shirt-0001")
    assert res.state == "accepted"
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000 - 9612, "USD")
    within = ("within_boundary",)
    assert w.decided() == [
        ("cart_prepare", "allow", "within_boundary"), ("quote", "allow", "within_boundary"),
        ("approval_request", "hold", "over_autonomy_cap"), ("approval_binding", "hold", "over_autonomy_cap"),
        ("execute", "refuse", "autonomy_held_for_member"), ("member_completion", "allow", "completed_by_member"),
        ("cart_prepare", "allow", within[0]), ("quote", "allow", within[0]), ("approval_request", "allow", within[0]),
        ("approval_binding", "allow", within[0]), ("execute", "allow", within[0])]


# Every public CommerceService method, classified. A new method fails this test until it is classified.
CLASSIFIED = {
    "create_cart": "evaluated", "update_cart": "evaluated", "quote_cart": "evaluated",
    "request_purchase": "evaluated", "execute_purchase": "evaluated", "execute_approved_quote": "evaluated",
    "approve": "binding", "approve_with_ap2": "binding",
    "create_delegation": "first_party", "revoke_delegation": "first_party", "list_delegations": "first_party",
    "update_autonomy_boundary": "first_party", "open_approval_challenge": "first_party",
    "register_surface_key": "first_party",
    "get_quote": "read", "get_operation": "read", "get_order": "read", "available_budget": "read",
    "completion_preview": "read", "bind": "read",
    "request_cancellation": "exempt:reduces_spend", "request_return": "exempt:reduces_spend",
    "reconcile": "system", "handle_webhook": "system", "operator_queue": "operator",
    "erase_agent_grants": "privacy", "erase_carts_and_quotes": "privacy", "erase_order_side_data": "privacy",
    "add_autonomy_sink": "wiring",
}


def test_every_agent_write_path_consults_the_evaluator(w, monkeypatch):
    public = {n for n, v in vars(CommerceService).items() if not n.startswith("_") and callable(v)}
    assert public == set(CLASSIFIED)
    d, ag = w.delegate(boundary=boundary(merchant_rule()))
    cart, quote, op = w.prepared(ag, line("overshirt"))
    _, approval = approve(w, op)
    seen = []
    real = A.evaluate

    def refusing(b, ceiling, f):
        seen.append(f.action)
        decision = real(b, ceiling, f)
        outcome = Outcome.HOLD if f.action is Action.APPROVAL_BINDING else Outcome.REFUSE
        return A.AutonomyDecision(f.action, outcome, decision.level, decision.required_level, decision.scope,
                                  ("autonomy_level_suggest_only",), decision.cap_bucket, decision.rule_count)

    monkeypatch.setattr(A, "evaluate", refusing)
    calls = {
        "create_cart": lambda: w.svc.create_cart(ag, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()]),
        "update_cart": lambda: w.svc.update_cart(ag, cart.id, if_match=cart.revision, lines=[line("bag")]),
        "quote_cart": lambda: w.svc.quote_cart(ag, cart.id),
        "request_purchase": lambda: w.svc.request_purchase(ag, quote.id),
        "execute_purchase": lambda: w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id,
                                                           idempotency_key="bypass-exec-000001"),
        "execute_approved_quote": lambda: w.svc.execute_approved_quote(
            ag, quote_id=quote.id, approval_id=approval.id, delegation_id=d.id, idempotency_key="bypass-exec-000002"),
    }
    assert set(calls) == {n for n, k in CLASSIFIED.items() if k == "evaluated"}
    for name, call in calls.items():
        seen.clear()
        with pytest.raises(Forbidden) as e:
            call()
        assert e.value.code == "autonomy_level_suggest_only" and seen, name
    monkeypatch.setattr(A, "evaluate", real)
    _, _, op2 = w.prepared(ag, line("sneaker"))
    monkeypatch.setattr(A, "evaluate", refusing)
    seen.clear()
    _, approval2 = approve(w, op2)
    assert approval2.delegation_ref is None and Action.APPROVAL_BINDING in seen
    assert w.provider.submit_calls == []


def test_a_wishlist_rule_covers_only_carts_entirely_on_the_wishlist(w):
    d, ag = w.delegate(boundary=boundary(wishlist_rule("demo-dress-m", cap=20_000)))
    _, _, op = w.prepared(ag, line("dress"))
    _, approval = approve(w, op)
    assert approval.delegation_ref == d.id
    assert w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id,
                                  idempotency_key="wish-exec-0000001").state == "accepted"
    _, _, op2 = w.prepared(ag, line("dress", "s"), line("overshirt"))  # not all on the wishlist: default prepare
    ch, approval2 = approve(w, op2)
    assert approval2.delegation_ref is None and ch.autonomy_codes == ("autonomy_level_prepare_only",)


def test_only_the_members_session_changes_a_boundary_and_nothing_widens_it(w):
    d, ag = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    with pytest.raises(Forbidden) as e:
        w.svc.update_autonomy_boundary(ag, d.id, boundary(merchant_rule(cap=50_000)), if_match=d.version)
    assert e.value.code == "not_trusted_surface"
    for i, ref in enumerate(("overshirt", "sneaker", "trousers")):  # three agent-completed purchases
        _, _, op = w.prepared(ag, line(ref))
        _, approval = approve(w, op)
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key=f"no-grow-exec-{i:05d}")
    w.svc.reconcile(op.id)
    assert w.store.get("delegations", d.id).boundary == boundary(merchant_rule(cap=15_000))
    assert w.store.get("delegations", d.id).version == d.version
    with pytest.raises(VersionConflict) as e:
        w.svc.update_autonomy_boundary(w.member, d.id, boundary(merchant_rule(cap=20_000)), if_match=d.version + 7)
    assert e.value.current_version == d.version
    narrowed = w.svc.update_autonomy_boundary(w.member, d.id, boundary(merchant_rule(cap=10_000)), if_match=d.version)
    assert narrowed.version == d.version + 1
    widened = w.svc.update_autonomy_boundary(w.member, d.id, None, if_match=narrowed.version)
    assert widened.boundary is None and widened.version == narrowed.version + 1
    changes = [e.payload for e in w.store.outbox() if e.event_type == "commerce.delegation.boundary_changed"]
    assert [(c["change"], c["version"], c["rule_count"]) for c in changes] == [
        ("narrowing", d.version + 1, 1), ("widening", d.version + 2, 0)]
    same = w.svc.update_autonomy_boundary(w.member, d.id, None, if_match=widened.version)
    assert same.version == widened.version  # unchanged: no write, no event


def test_narrowing_stays_possible_during_a_pending_grant_deletion_but_widening_does_not(fw):
    w, freeze = fw
    d, _ = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    freeze(AGENT_GRANTS)
    with pytest.raises(ProcessingRestricted):  # widening is new processing of the member's data
        w.svc.update_autonomy_boundary(w.member, d.id, boundary(merchant_rule(cap=20_000)), if_match=d.version)
    narrowed = w.svc.update_autonomy_boundary(w.member, d.id, boundary(merchant_rule(cap=10_000)), if_match=d.version)
    assert narrowed.version == d.version + 1  # like revocation, narrowing is always possible


def test_narrowing_hands_approved_agent_work_back_to_the_member(w):
    d, ag = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    _, _, approved_op = w.prepared(ag, line("overshirt"))
    _, approval = approve(w, approved_op)
    assert approval.delegation_ref == d.id
    _, _, waiting_op = w.prepared(ag, line("sneaker"))
    current = w.store.get("delegations", d.id)
    w.svc.update_autonomy_boundary(w.member, d.id, boundary(merchant_rule(cap=5_000)), if_match=current.version)
    assert w.store.get("operations", approved_op.id).state == "approved"  # the member's approval stands
    assert w.store.get("approvals", approval.id).delegation_ref is None  # ... and is now the member's to complete
    assert w.store.get("operations", waiting_op.id).state == "awaiting_approval"  # decided at its approval
    changed = [e.payload for e in w.store.outbox() if e.event_type == "commerce.delegation.boundary_changed"]
    assert (changed[-1]["change"], changed[-1]["returned_operations"]) == ("narrowing", 1)
    with pytest.raises(Forbidden) as e:
        w.svc.execute_purchase(ag, operation_id=approved_op.id, approval_id=approval.id,
                               idempotency_key="narrowed-exec-00001")
    assert e.value.code == "autonomy_held_for_member" and w.provider.submit_calls == []
    assert w.svc.execute_purchase(w.member, operation_id=approved_op.id, approval_id=approval.id,
                                  idempotency_key="narrowed-exec-00002").state == "accepted"


def test_more_authority_for_an_agent_needs_the_members_step_up(w):
    """Widening a boundary, or granting purchase authority at all, needs the approval assurance level;
    narrowing never does (revoke-and-regrant cannot skip it)."""
    from tests.fixtures.commerce.harness import MEMBER
    d, ag = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    weak = member_session(aal="aal1")
    with pytest.raises(Forbidden) as e:
        w.svc.update_autonomy_boundary(weak, d.id, boundary(merchant_rule(cap=20_000)), if_match=d.version)
    assert e.value.code == "reauthentication_required"
    assert w.store.get("delegations", d.id).version == d.version
    narrowed = w.svc.update_autonomy_boundary(weak, d.id, boundary(merchant_rule(cap=10_000)), if_match=d.version)
    assert narrowed.version == d.version + 1
    w.svc.revoke_delegation(weak, d.id)
    with pytest.raises(Forbidden) as e:
        w.svc.create_delegation(weak, client_id=AGENT_CLIENT, mode=AssistanceMode.BUY_WITHIN_RULES,
                                allowed_providers={PROVIDER_ID}, limits=limits(),
                                expires_at=w.clock.now + timedelta(days=1))
    assert e.value.code == "reauthentication_required"
    prepare = w.svc.create_delegation(weak, client_id=AGENT_CLIENT, mode=AssistanceMode.PREPARE,
                                      allowed_providers={PROVIDER_ID}, limits=None,
                                      expires_at=w.clock.now + timedelta(days=1))
    assert prepare.mode is AssistanceMode.PREPARE  # preparing grants no purchase authority
    w.svc.revoke_delegation(weak, prepare.id)
    dev = member_session(aal="simulated")  # foundation's dev identity: only where every provider is simulated
    assert w.svc.create_delegation(dev, client_id=AGENT_CLIENT, mode=AssistanceMode.BUY_WITHIN_RULES,
                                   allowed_providers={PROVIDER_ID}, limits=limits(),
                                   expires_at=w.clock.now + timedelta(days=1)).member_id == MEMBER


def test_a_boundary_narrowed_between_reservation_and_submit_stops_unsent_work(w):
    d, ag = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    _, _, op = w.prepared(ag, line("overshirt"))
    _, approval = approve(w, op)
    real_submit = w.svc._submit

    def narrow_first(op_, quote, principal):
        current = w.store.get("delegations", d.id)
        # The member narrows after the reservation committed; the approved op is already "submitting".
        w.store.run(lambda tx: tx.put("delegations", d.id, current.__class__(
            **{**current.__dict__, "boundary": boundary(merchant_rule(cap=5_000)), "version": current.version + 1})))
        return real_submit(op_, quote, principal)

    w.svc._submit = narrow_first
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="race-exec-0000001")
    assert (res.state, res.reason_code) == ("cancelled", "autonomy_boundary_changed")
    assert w.provider.submit_calls == [] and all(e.state == "released" for e in w.store.rows("reservations"))
    assert w.decided()[-2:] == [("execute", "allow", "within_boundary"), ("execute", "refuse", "over_autonomy_cap")]


def test_widening_never_rebinds_an_approval_held_for_the_member(w):
    d, ag = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    _, _, op = w.prepared(ag, line("dress"))
    _, approval = approve(w, op)
    assert approval.delegation_ref is None
    w.svc.update_autonomy_boundary(w.member, d.id, boundary(merchant_rule(cap=50_000)),
                                   if_match=w.store.get("delegations", d.id).version)
    with pytest.raises(Forbidden) as e:
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="widen-exec-000001")
    assert e.value.code == "autonomy_held_for_member" and w.provider.submit_calls == []
    assert w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=approval.id,
                                  idempotency_key="widen-exec-000002").state == "accepted"


def test_a_revocation_after_binding_is_refused_inside_the_execute_transaction(w):
    d, ag = w.delegate(boundary=boundary(merchant_rule()))
    _, _, op = w.prepared(ag, line("overshirt"))
    _, approval = approve(w, op)
    bound = w.svc.bind(ag)
    w.svc.revoke_delegation(w.member, d.id)  # lands after the caller was bound
    real_bind = w.svc._bind
    w.svc._bind = lambda p: (bound, d)  # the stale grant the caller was bound with
    try:
        with pytest.raises((DelegationInvalid, ApprovalInvalid)):
            w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id,
                                   idempotency_key="revoked-exec-00001")
    finally:
        w.svc._bind = real_bind
    assert w.provider.submit_calls == [] and w.store.rows("reservations") == []


# =========================================================================== decision log
def test_each_agent_decision_writes_one_closed_schema_line_without_amounts_or_refs(w):
    from brandme_core.mcp.refs import log_ref
    d, ag = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    _, _, op = w.prepared(ag, line("dress"))
    _, approval = approve(w, op)
    with pytest.raises(Forbidden):
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="log-exec-00000001")
    lines = w.decisions.events("commerce.autonomy_decision")
    assert [(ln["action"], ln["outcome"], ln["cap_bucket"]) for ln in lines] == [
        ("cart_prepare", "allow", "no_total"), ("quote", "allow", "no_total"), ("approval_request", "hold", "over"),
        ("approval_binding", "hold", "over"), ("execute", "refuse", "over")]
    assert {ln["retention"] for ln in lines} == {"security_audit_180d"} and lines[-1]["level"] == "warning"
    # One purchase joins across request, binding and execute without its id; carts have no quote yet.
    assert [ln["quote_ref"] is not None for ln in lines] == [False, False, True, True, True]
    assert len({ln["quote_ref"] for ln in lines[2:]}) == 1
    assert [ln["wait_band"] for ln in lines] == [None, None, None, "lt_1m", None]  # how long the member took
    assert {(ln["client_kind"], ln["simulation"]) for ln in lines} == {("external", True)}
    assert all(ln["member_ref"] == log_ref("member", w.member.member_id) and ln["rule_count"] == 1
               and ln["scope"] == "merchant" and ln["evaluator"] == A.EVALUATOR_VERSION for ln in lines)
    text = json.dumps(w.decisions.lines)
    for secret in (w.member.member_id, d.id, op.id, "17172", "15000", "demo-dress-m", MERCHANT_ID):
        assert secret not in text, secret


@pytest.mark.parametrize("change", [
    {"extra": 1}, {"codes": ["made_up"]}, {"outcome": "hold", "action": "execute", "codes": ["over_autonomy_cap"]},
    {"outcome": "allow", "codes": ["over_autonomy_cap"]}, {"codes": []},
    {"origin": "assistant", "task_ref": None},
    {"outcome": "refuse", "action": "quote", "codes": ["autonomy_held_for_member"]},
    {"wait_band": "lt_1m"},  # only an approval's binding has a wait
    {"action": "member_completion", "codes": ["within_boundary"]},
    {"codes": ["completed_by_member"]},  # only on a member completion
    {"simulation": "yes"}, {"client_kind": "partner"},
])
def test_the_run_log_refuses_a_malformed_decision_line(change):
    from brandme_core.orchestrator.runlog import autonomy_decision_fields
    good = {"request_id": None, "origin": "service", "task_ref": None, "step": None, "member_ref": "0123456789abcdef",
            "delegation_id": str(uuid.uuid4()), "client_id": AGENT_CLIENT, "mode": "buy_within_rules",
            "action": "execute", "outcome": "allow", "autonomy_level": "buy_after_approval",
            "required_autonomy_level": "buy_after_approval", "scope": "merchant", "codes": ["within_boundary"],
            "cap_bucket": "le_50", "rule_count": 1, "boundary_version": 1, "evaluator": "1.0.0",
            "client_kind": "external", "quote_ref": "fedcba9876543210", "simulation": True, "wait_band": None}
    log = MemoryRunLog(strict=True)
    log.autonomy_decision(good)
    bad = {**good, **change}
    with pytest.raises(RunLogViolation):
        if "extra" in change:  # an unknown field never reaches a line: the sanitizer drops it, the spec refuses it
            log._emit("commerce.autonomy_decision", {**autonomy_decision_fields(good), "extra": 1})
        else:
            log.autonomy_decision(bad)


class RetryingStore(InMemoryCommerceStore):
    """Runs every outermost callback twice and discards the first attempt, as Spanner does on Aborted."""

    def run(self, fn):
        if self._depth == 0:
            with self._lock:
                snapshot = {t: dict(rows) for t, rows in self._tables.items()}
                try:
                    super().run(fn)
                except Exception:
                    pass
                self._tables = snapshot
        return super().run(fn)


def test_a_retried_transaction_logs_only_its_committed_attempt():
    w = world(store=RetryingStore())
    d, ag = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    _, _, op = w.prepared(ag, line("overshirt"))
    _, approval = approve(w, op)
    w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="retry-exec-000001")
    assert [a for a, _, _ in w.decided()] == ["cart_prepare", "quote", "approval_request", "approval_binding",
                                              "execute"]


def test_decision_lines_join_the_tool_call_audit_on_request_task_and_step():
    from brandme_core.mcp.authz import ExecutorAssertionVerifier
    from brandme_core.mcp.tools import McpToolExecutor
    from brandme_core.orchestrator import AssistantRuntime, DeterministicPlanner
    w = world()
    d, ag = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    audit = []
    ex = McpToolExecutor(commerce=w.svc, registry=w.registry, audit=audit.append,
                         verifier=ExecutorAssertionVerifier(gateway_issuer="gw", keys={}, environment="development"))
    rt = AssistantRuntime(ex, environment="development")
    task = rt.run(ag, rt.create(ag, "linen overshirt", AssistanceMode.BUY_WITHIN_RULES).id, DeterministicPlanner())
    assert task.state == "awaiting_approval"
    req = next(e for e in task.events if e.type == "approval_requested")
    assert req.data["completed_by"] == "agent"
    decisions = w.decisions.events("commerce.autonomy_decision")
    by_request = {r["request_id"]: r for r in audit}
    assert decisions and all(ln["origin"] == "assistant" for ln in decisions)
    for ln in decisions:
        call = by_request[ln["request_id"]]
        assert (ln["task_ref"], ln["step"]) == (call["task_ref"], call["step"])
    op_id = req.data["operation_id"]
    _, approval = approve(w, w.store.get("operations", op_id))
    status, outcome = ex.call(ag, {"request_id": str(uuid.uuid4()), "protocol_version": __import__(
        "brandme_core.mcp", fromlist=["MCP_PROTOCOL_VERSION"]).MCP_PROTOCOL_VERSION, "environment": "development",
        "tool": "brandme.purchase.execute", "arguments": {"operation_id": op_id, "approval_id": approval.id},
        "idempotency_key": "join-exec-00000001"}, origin="mcp")
    assert status == 200 and outcome.status == "ok"
    last = w.decisions.events("commerce.autonomy_decision")[-1]
    assert (last["action"], last["origin"], last["request_id"]) == ("execute", "mcp", audit[-1]["request_id"])


def test_compose_routes_autonomy_decisions_to_the_run_log():
    from brandme_core.mcp.authz import ExecutorAssertionVerifier
    from brandme_core.orchestrator.composition import compose_assistant
    w = world()
    log = MemoryRunLog(strict=True)
    compose_assistant(env={"BRANDME_MODE": "development"}, commerce=w.svc, registry=w.registry,
                      verifier=ExecutorAssertionVerifier(gateway_issuer="gw", keys={}, environment="development"),
                      run_log=log)
    d, ag = w.delegate(boundary=boundary(default="suggest"))
    with pytest.raises(Forbidden):
        w.svc.create_cart(ag, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()])
    (ln,) = log.events("commerce.autonomy_decision")
    assert (ln["action"], ln["outcome"], ln["codes"]) == ("cart_prepare", "refuse", ["autonomy_level_suggest_only"])


# =========================================================================== My Data
def test_erasure_deletes_boundaries_with_their_grants_and_clears_them_on_kept_grants(w):
    d, ag = w.delegate(boundary=boundary(merchant_rule(), wishlist_rule("demo-dress-m")))
    _, _, op = w.prepared(ag, line("overshirt"))
    _, approval = approve(w, op)
    w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="erase-exec-000001")
    plain = w.svc.create_delegation(w.member, client_id="client-fictional-other", mode=AssistanceMode.PREPARE,
                                    allowed_providers={PROVIDER_ID}, limits=None,
                                    expires_at=w.clock.now + timedelta(days=1), boundary=boundary())
    counts = w.svc.erase_agent_grants(w.member.member_id)
    assert w.store.get("delegations", plain.id) is None  # deleted with its grant
    kept = w.store.get("delegations", d.id)
    assert kept is not None and kept.revoked_at is not None and kept.boundary is None  # authority kept, rules gone
    assert counts.get("boundaries_cleared") == 1 and counts["kept"] == 1
    again = w.svc.erase_agent_grants(w.member.member_id)
    assert "boundaries_cleared" not in again  # idempotent


def test_export_carries_the_members_boundary_with_its_grant(_spanner_db, monkeypatch):
    from datetime import datetime, timezone
    from brandme_core.domains.commerce.privacy_handler import HANDLER
    from brandme_core.domains.commerce.spanner_store import SpannerCommerceStore
    from brandme_core.domains.privacy import PrivacyRegistry
    from brandme_core.domains.privacy.privacy import MyDataService
    from tests.fixtures.commerce.harness import OTHER_MEMBER
    from tests.fixtures.commerce.stores import wipe
    from tests.test_commerce_privacy import _Objects
    monkeypatch.setenv("BRANDME_MODE", "development")
    wipe(_spanner_db)
    reg = PrivacyRegistry()
    reg.register(HANDLER)
    w = world(store=SpannerCommerceStore(_spanner_db))
    w.delegate(boundary=boundary(wishlist_rule("demo-dress-m", cap=20_000)))
    w.svc.create_delegation(member_session(member=OTHER_MEMBER), client_id=AGENT_CLIENT, mode=AssistanceMode.PREPARE,
                            allowed_providers={PROVIDER_ID}, limits=None, expires_at=w.clock.now + timedelta(days=1),
                            boundary=boundary(wishlist_rule("demo-bag-s", level="prepare")))
    out = MyDataService(_spanner_db, _Objects(), reg, environment="development").export(
        w.member.member_id, datetime.now(timezone.utc))
    text = json.dumps(out["package"]["categories"][AGENT_GRANTS], default=str)
    assert "demo-dress-m" in text and A.STORAGE_KEY in text
    assert "demo-bag-s" not in text and OTHER_MEMBER not in text


# =========================================================================== surfaces
def test_an_ap2_approval_over_the_cap_binds_to_the_member():
    from jwcrypto.jwk import JWK
    from tests.test_commerce_ap2 import mandates
    w = world()
    d, ag = w.delegate(boundary=boundary(merchant_rule(cap=15_000)))
    _, quote, op = w.prepared(ag, line("dress"))
    user = JWK.generate(kty="EC", crv="P-256")
    w.svc.register_surface_key(w.member, user.export_public(as_dict=True))
    cm, pm = mandates(w, quote, user, int(w.clock.now.timestamp()))
    approval = w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
    assert approval.delegation_ref is None
    with pytest.raises(Forbidden) as e:
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="ap2-held-exec-001")
    assert e.value.code == "autonomy_held_for_member" and w.provider.submit_calls == []
    assert ("approval_binding", "hold", "over_autonomy_cap") in w.decided()


def test_the_domain_http_api_refuses_to_mount_without_an_autonomy_sink():
    from brandme_core.domains.commerce.http_api import CommerceHttpApi
    from brandme_core.mcp.authz import DOMAIN_AUDIENCE, ExecutorAssertionVerifier
    w = world()
    w.svc._autonomy_sinks.clear()
    verifier = ExecutorAssertionVerifier(gateway_issuer="gw", keys={}, environment="development",
                                         audience=DOMAIN_AUDIENCE, allow_session=True)
    with pytest.raises(ValueError):
        CommerceHttpApi(service=w.svc, verifier=verifier, audit=lambda r: None, tier_audit=lambda r: None)


def test_http_boundary_create_update_and_refusals():
    from tests.test_commerce_http import Http
    h = Http()
    b = {"default_level": "prepare", "default_max_total": None, "rules": [
        {"scope": "merchant", "provider_id": PROVIDER_ID, "merchant_id": MERCHANT_ID, "level": "buy_after_approval",
         "max_total": {"amount_minor": "15000", "currency": "USD"}}]}
    grant = {"client_id": AGENT_CLIENT, "mode": "buy_within_rules", "allowed_providers": [PROVIDER_ID],
             "expires_at": "2026-10-12T12:00:00Z",
             "limits": {"currency": "USD", "max_per_order": {"amount_minor": "50000", "currency": "USD"},
                        "max_cumulative": {"amount_minor": "50000", "currency": "USD"}, "window_seconds": 86400,
                        "allowed_merchants": [MERCHANT_ID]}}
    bad = h.call("delegation.create", {**grant, "autonomy_boundary": {**b, "default_level": "buy_without_approval"}})
    assert bad.status_code == 403 and bad.json()["code"] == "autonomous_not_supported"
    r = h.call("delegation.create", {**grant, "autonomy_boundary": b})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["autonomy_boundary"] == b
    did, version = created["id"], created["version"]
    agent_p = h.bearer(["commerce:research", "commerce:cart", "commerce:purchase"], delegation_id=did)
    assert h.call("delegation.boundary.update", {"delegation_id": did, "autonomy_boundary": None}, agent_p,
                  {"If-Match": f'"{version}"'}).status_code == 403
    stale = h.call("delegation.boundary.update", {"delegation_id": did, "autonomy_boundary": None},
                   headers={"If-Match": '"99"'})
    assert stale.status_code == 409 and stale.headers["etag"] == f'"{version}"'
    narrowed = {**b, "rules": [{**b["rules"][0], "max_total": {"amount_minor": "9000", "currency": "USD"}}]}
    ok = h.call("delegation.boundary.update", {"delegation_id": did, "autonomy_boundary": narrowed},
                headers={"If-Match": f'"{version}"'})
    assert ok.status_code == 200 and ok.json()["autonomy_boundary"] == narrowed
    assert h.call("delegation.boundary.update", {"delegation_id": did, "autonomy_boundary": narrowed, "x": 1},
                  headers={"If-Match": '"2"'}).json()["code"] == "unexpected_field"


@pytest.mark.parametrize("rail", ["simulated", "stripe_double"])
def test_mission_agent_assisted_purchase_inside_a_member_cap_is_fully_audited(commerce_store, rail):
    """Ultra plan 02 mission on both rails: the member sets a $250.00 cap; the concierge prepares through MCP; the
    member approves; the agent places it; the over-cap basket is held for the member. Stripe double = fixture
    double, not Stripe."""
    from brandme_core.mcp import MCP_PROTOCOL_VERSION
    from brandme_core.mcp.authz import ExecutorAssertionVerifier
    from brandme_core.mcp.tools import McpToolExecutor
    from tests.test_commerce_payments_flow import _held, rail_world
    if True:
        w = rail_world(rail, commerce_store)
        d, ag = w.delegate(boundary=boundary(merchant_rule(cap=25_000)))
        audit = []
        ex = McpToolExecutor(commerce=w.svc, registry=w.registry, audit=audit.append,
                             verifier=ExecutorAssertionVerifier(gateway_issuer="gw", keys={}, environment="development"))

        def tool(name, args, key=None):
            status, outcome = ex.call(ag, {"request_id": str(uuid.uuid4()), "protocol_version": MCP_PROTOCOL_VERSION,
                                           "environment": "development", "tool": name, "arguments": args,
                                           "idempotency_key": key}, origin="mcp")
            assert outcome.status == "ok", (name, outcome.problem)
            return outcome.structured_content

        def basket(*items, key):
            lines = [{"variant_id": l.variant_id, "source_variant_ref": l.source_variant_ref, "quantity": 1}
                     for l in items]
            cart = tool("brandme.cart.create", {"provider_id": PROVIDER_ID, "merchant_id": MERCHANT_ID, "lines": lines},
                        key)
            quote = tool("brandme.checkout.quote", {"cart_id": cart["cart_id"]})["quote"]
            return quote, tool("brandme.purchase.request", {"quote_id": quote["id"]})

        quote, req = basket(line("overshirt"), line("bag"), key="mission-cart-000001")  # 23544 <= 25000
        assert (req["completed_by"], req["autonomy_codes"]) == ("agent", ["within_boundary"])
        _, approval = approve(w, w.store.get("operations", req["operation_id"]))
        placed = tool("brandme.purchase.execute", {"operation_id": req["operation_id"], "approval_id": approval.id},
                      "mission-exec-000001")
        assert placed["state"] == "accepted", rail
        order = w.store.get("orders", w.store.get("operations", req["operation_id"]).order_id)
        w.svc._apply_observation(order.id, w.provider.lookup(order.provider_order_ref), "system:reconciler")
        assert w.store.get("orders", order.id).payment_status == "authorized"
        assert _held(w, order.provider_order_ref).authorized == Money(23_544, "USD")
        assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000 - 23_544, "USD")

        quote2, req2 = basket(line("jacket"), line("bag", "s"), key="mission-cart-000002")  # 33264 > 25000
        assert (req2["completed_by"], req2["autonomy_codes"]) == ("member", ["over_autonomy_cap"])
        _, approval2 = approve(w, w.store.get("operations", req2["operation_id"]))
        status, refused = ex.call(ag, {"request_id": str(uuid.uuid4()), "protocol_version": MCP_PROTOCOL_VERSION,
                                       "environment": "development", "tool": "brandme.purchase.execute",
                                       "arguments": {"operation_id": req2["operation_id"], "approval_id": approval2.id},
                                       "idempotency_key": "mission-exec-000002"}, origin="mcp")
        assert refused.problem["code"] == "autonomy_held_for_member"
        assert w.svc.execute_purchase(w.member, operation_id=req2["operation_id"], approval_id=approval2.id,
                                      idempotency_key="mission-exec-000003").state == "accepted"
        lines = w.decisions.events("commerce.autonomy_decision")
        assert [(ln["action"], ln["outcome"], ln["cap_bucket"]) for ln in lines] == [
            ("cart_prepare", "allow", "no_total"), ("quote", "allow", "no_total"),
            ("approval_request", "allow", "le_100"), ("approval_binding", "allow", "le_100"),
            ("execute", "allow", "le_100"),
            ("cart_prepare", "allow", "no_total"), ("quote", "allow", "no_total"),
            ("approval_request", "hold", "over"), ("approval_binding", "hold", "over"), ("execute", "refuse", "over"),
            ("member_completion", "allow", "over")]
        tool_requests = {r["request_id"] for r in audit}
        assert all(ln["request_id"] in tool_requests for ln in lines if ln["origin"] == "mcp")
        assert [r["status"] for r in audit] == ["ok"] * 7 + ["error"]
