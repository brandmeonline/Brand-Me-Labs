"""Partner tiers (Ultra plan 02 item 7): enforcement mechanics behind a pricing-table interface.

Placeholder tiers only: no prices exist anywhere, the two shipped placeholder tiers sit at the two ends of every
limit (nothing, everything), and the placeholder table is refused outside demo and development. Quota numbers
used below are test values local to this module. Enforced: tier assignment (persisted as a setup item, both
stores); the 3D/AR activation gate, the downgrade reset, connection tests and process restarts that can never
bring an excluded capability back (both stores); the registry rule; the shelf quota at the brand-shelf load
seam (``load_shelf_page``, no production caller yet). Analytics and member connection are check functions with
no caller yet. Tiers never touch member search, quotes or purchases.
"""

import ast
import io
import json
import pathlib
import re
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from brandme_core.domains.commerce.errors import Forbidden, InvalidRequest, VersionConflict
from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers import tiers as T
from brandme_core.domains.providers.contracts import CAPABILITIES, CatalogPage, ProbeResult, SourceVariant
from brandme_core.domains.providers.ingestion import CatalogIngestor, IngestionAudit
from brandme_core.domains.providers.registry import CapabilityStatus, ProviderConnection, RegistryError
from brandme_core.domains.providers.setup import ProviderSetupService, SetupRefused, operator_ref
from brandme_core.domains.providers.tiers import (
    PLACEHOLDER_PRICING_TABLE, Analytics, Customization, StaticPricingTable, TierConfigError, TierDefinition,
    TierLimits,
)
from brandme_core.orchestrator.runlog import REJECTED, JsonLineRunLog, MemoryRunLog, RunLogViolation
from tests.fixtures.commerce.harness import MEMBER, member_session, world
from tests.fixtures.commerce.stores import _spanner_db, provider_setup_store  # noqa: F401  (fixtures)
from tests.test_providers_setup import OPERATOR, OPERATOR_MEMBER, RIGHTS, SECRET_REF, ScriptedProvider

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHOP = "fixture_shop"
T0 = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
FLOOR, CEILING = "placeholder_floor", "placeholder_ceiling"


def _placeholder(tier_id, shelf, customization=Customization.STANDARD):
    return TierDefinition(tier_id, f"Placeholder {tier_id[12:]} (not priced)",
                          TierLimits(shelf, customization, Analytics.NONE, False), placeholder=True)


# Test values for the shelf quota only (this module): not shipped, not prices, not an offer.
SHELF_TABLE = StaticPricingTable("placeholder-fx", (_placeholder("placeholder_shelf2", 2),
                                                    _placeholder("placeholder_shelf3", 3),
                                                    _placeholder("placeholder_shelf5", 5)))


def _shop(adapter, now):
    """A fictional non-simulation brand catalog whose 3D and photo try-on start unconfigured."""
    caps = {"catalog.search": CapabilityStatus("catalog.search", "sandbox", "sandbox_evidence", now, "fx:1",
                                               "sandbox_operation"),
            "catalog.3d": CapabilityStatus("catalog.3d", "unconfigured", "activation_pending_verification"),
            "tryon.photo": CapabilityStatus("tryon.photo", "unconfigured", "activation_pending_verification")}
    return ProviderConnection(provider_id=SHOP, display_name="Fixture Shop (fictional)", environment="development",
                              simulation=False, country_codes=("US",), disclosure="Fictional fixture provider.",
                              capabilities=caps, adapter=adapter)


def _process(store, table=None):
    """One process: its own registry and adapter over the shared setup store, with a strict decision log."""
    w = world()
    scripted = ScriptedProvider()
    w.registry.register(_shop(scripted, w.clock.now))
    log = MemoryRunLog(strict=True)
    svc = ProviderSetupService(w.registry, store, clock=w.clock, pricing_table=table, tier_audit=log.tier_decision)
    return SimpleNamespace(w=w, svc=svc, store=store, scripted=scripted, log=log)


@pytest.fixture
def env(provider_setup_store):
    return _process(provider_setup_store)


def _ready_for_activation(env, capability="catalog.3d"):
    """Every prerequisite done and a fresh passing connection test, so only the tier can refuse."""
    env.svc.update_setup(OPERATOR, SHOP, {"account_ref": "fictional-fixture-account", "credential_secret_ref": SECRET_REF})
    env.svc.update_setup(OPERATOR, SHOP, {"data_use": RIGHTS})
    env.scripted.next = ProbeResult("passed", "sandbox_operation", f"fx:run:{capability}", "Read one 3D asset.")
    assert env.svc.run_verification(OPERATOR, SHOP, capability, "read_only_test")["result"] == "passed"


def _version(env):
    return int(env.svc.get_setup(OPERATOR, SHOP)["version"])


def _state(env, capability="catalog.3d"):
    s = env.w.registry.get(SHOP).capability(capability)
    return s.state, s.reason_code


def _tier_lines(log):
    return [(ln["origin"], ln["dimension"], ln["outcome"], ln["code"]) for ln in log.events("provider.tier_decision")]


# =========================================================================== the table: no prices, no invented terms
def test_placeholder_tiers_are_labeled_everywhere_and_show_no_money(env):
    view = env.svc.get_setup(OPERATOR, SHOP)
    assert [o["tier_id"] for o in view["tier_options"]] == [FLOOR, CEILING]
    assert view["tier"]["source"] == "unassigned" and view["tier"]["price_label"] == T.PRICE_LABEL
    for t in view["tier_options"]:
        assert t["placeholder"] is True and t["price_status"] == "not_priced" and t["price_label"] == T.PRICE_LABEL
        assert t["display_name"].startswith("Placeholder") and "(not priced)" in t["display_name"]
        assert "decision_ref" not in t
    text = json.dumps({"tier": view["tier"], "tier_options": view["tier_options"]})
    assert not re.search(r"\d+[.,]\d{2}\b|[$€£¥]|\b(USD|EUR|GBP|JPY)\b", text)
    assert not set(re.findall(r'"([a-z_]*(?:price|amount|cost|fee)[a-z_]*)":', text)) - {"price_status", "price_label"}


def test_the_shipped_placeholders_invent_no_quota_only_the_two_ends_of_each_limit():
    floor, ceiling = (PLACEHOLDER_PRICING_TABLE.get(t).limits for t in (FLOOR, CEILING))
    assert floor == T.NO_TIER  # nothing beyond the standard presentation every listing has
    assert ceiling == TierLimits(None, Customization.AR, Analytics.AGGREGATE_DEMAND, True)
    assert [t.tier_id for t in PLACEHOLDER_PRICING_TABLE.tiers()] == [FLOOR, CEILING]


@pytest.mark.parametrize("make,code", [
    (lambda: TierDefinition("placeholder_x", "Placeholder X (not priced)", T.NO_TIER, True, decision_ref="dec-1"),
     "placeholder_has_decision"),
    (lambda: TierDefinition("gold", "Gold", T.NO_TIER, False), "tier_needs_founder_decision"),
    (lambda: TierDefinition("placeholder_x", "Tier X", T.NO_TIER, True), "placeholder_label_missing"),
    (lambda: TierDefinition("gold", "Placeholder gold", T.NO_TIER, False, decision_ref="dec-1"),
     "placeholder_label_mismatch"),
    (lambda: TierDefinition("silver", "Silver", T.NO_TIER, True), "placeholder_label_mismatch"),
    (lambda: TierDefinition("Gold Tier", "Gold", T.NO_TIER, False, decision_ref="dec-1"), "tier_id_invalid"),
    (lambda: TierLimits(-1, Customization.STANDARD, Analytics.NONE, False), "tier_field_invalid"),
    (lambda: TierLimits(True, Customization.STANDARD, Analytics.NONE, False), "tier_field_invalid"),
    (lambda: TierLimits(1, "ar", Analytics.NONE, False), "tier_field_invalid"),
])
def test_tier_definitions_refuse_prices_unlabeled_placeholders_and_undecided_real_tiers(make, code):
    with pytest.raises(TierConfigError) as e:
        make()
    assert e.value.code == code


def test_a_table_stays_consistent():
    floor = PLACEHOLDER_PRICING_TABLE.get(FLOOR)
    gold = TierDefinition("gold", "Gold", T.NO_TIER, False, decision_ref="dec-1")
    for args, code in [(("t-1", (floor, floor)), "duplicate_tier"), (("T 1", (floor,)), "table_version_invalid"),
                       (("t-1", (floor, gold)), "mixed_placeholder_table")]:
        with pytest.raises(TierConfigError) as e:
            StaticPricingTable(*args)
        assert e.value.code == code


def test_placeholder_table_only_in_demo_and_development():
    assert T.pricing_table_for("development") is PLACEHOLDER_PRICING_TABLE
    assert T.pricing_table_for("demo") is PLACEHOLDER_PRICING_TABLE
    for environment in ("sandbox", "production"):
        assert T.pricing_table_for(environment) is T.UNCONFIGURED_PRICING_TABLE  # nothing configured, nothing granted
        with pytest.raises(TierConfigError) as e:
            T.pricing_table_for(environment, PLACEHOLDER_PRICING_TABLE)
        assert e.value.code == "placeholder_pricing_table_refused"
    unconfigured = T.resolve_from_items({}, T.UNCONFIGURED_PRICING_TABLE)
    assert (unconfigured.source, unconfigured.limits) == ("unconfigured", T.NO_TIER)
    decided = StaticPricingTable("founder-1", (TierDefinition("entry", "Entry", T.NO_TIER, False,
                                                              decision_ref="founder-pricing-decision-1"),))
    assert T.pricing_table_for("production", decided) is decided  # a founder table drops in unchanged


def test_gated_capabilities_are_in_the_capability_vocabulary():
    assert T.GATED_CAPABILITIES <= set(CAPABILITIES)


# =========================================================================== assignment (both stores)
def test_operator_assigns_a_tier_and_a_new_process_reads_it_back(env):
    v = _version(env)
    view = env.svc.assign_tier(OPERATOR, SHOP, CEILING, if_match=v)
    assert view["tier"]["tier_id"] == CEILING and view["tier"]["source"] == "assigned"
    assert view["tier"]["label"] == T.PLACEHOLDER_NOTICE and int(view["version"]) == v + 1
    row = env.store.snapshot("development", SHOP).items["tier"]
    assert (row.done, row.evidence_ref, row.recorded_by) == (True, f"{CEILING}@placeholder-1", operator_ref(OPERATOR))
    assert _process(env.store).svc.get_setup(OPERATOR, SHOP)["tier"]["tier_id"] == CEILING


def test_assigning_a_tier_never_enables_a_capability(env):
    before = {n: s.state for n, s in env.w.registry.get(SHOP).capabilities.items()}
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    assert {n: s.state for n, s in env.w.registry.get(SHOP).capabilities.items()} == before
    assert env.store.snapshot("development", SHOP).capabilities == {}


def test_tier_assignment_needs_provider_admin_in_the_same_environment(env):
    for who in (member_session(), replace(OPERATOR, environment="production"),
                replace(OPERATOR, scopes=frozenset({"commerce:research"}))):
        with pytest.raises(Forbidden):
            env.svc.assign_tier(who, SHOP, CEILING)
    assert "tier" not in env.store.snapshot("development", SHOP).items


def test_unknown_tiers_and_stale_versions_are_refused_and_write_nothing(env):
    v = _version(env)
    for bad in ("gold", "placeholder_tier_z", 7):
        with pytest.raises(InvalidRequest) as e:
            env.svc.assign_tier(OPERATOR, SHOP, bad)
        assert e.value.code == "tier_unknown"
    with pytest.raises(VersionConflict):
        env.svc.assign_tier(OPERATOR, SHOP, CEILING, if_match=v + 5)
    assert _version(env) == v and "tier" not in env.store.snapshot("development", SHOP).items


def test_no_assignment_or_one_the_table_no_longer_knows_fails_closed(env):
    assert T.resolve_from_items(env.store.snapshot("development", SHOP).items, PLACEHOLDER_PRICING_TABLE).limits \
        == T.NO_TIER
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    renamed = StaticPricingTable("placeholder-2", PLACEHOLDER_PRICING_TABLE.tiers())
    tier = T.resolve_from_items(env.store.snapshot("development", SHOP).items, renamed)
    assert (tier.tier_id, tier.source, tier.limits) == (None, "assigned_unknown", T.NO_TIER)  # never the ceiling
    env.svc.assign_tier(OPERATOR, SHOP, None)
    assert env.svc.get_setup(OPERATOR, SHOP)["tier"]["source"] == "unassigned"


def test_any_pricing_table_implementation_drives_enforcement(env):
    class FounderTable:  # not a StaticPricingTable: only the Protocol
        table_version = "founder-1"
        _tiers = (TierDefinition("entry", "Entry", T.NO_TIER, False, decision_ref="founder-decision-1"),
                  TierDefinition("studio", "Studio", TierLimits(None, Customization.AR, Analytics.NONE, False),
                                 False, decision_ref="founder-decision-2"))

        def get(self, tier_id):
            return next((t for t in self._tiers if t.tier_id == tier_id), None)

        def tiers(self):
            return self._tiers

    env = _process(env.store, FounderTable())
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, "entry")
    with pytest.raises(SetupRefused) as e:
        env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert e.value.code == "activation_tier_excludes_capability"
    env.svc.assign_tier(OPERATOR, SHOP, "studio")
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert _state(env)[0] == "sandbox"


# =========================================================================== customization (both stores)
def test_3d_activation_is_refused_without_a_tier_and_below_it_and_allowed_at_it(env):
    _ready_for_activation(env)
    with pytest.raises(SetupRefused) as e:  # no tier assigned: fail closed
        env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert e.value.code == "activation_tier_excludes_capability"
    assert _state(env)[0] == "unconfigured"
    blocked = {i["key"]: i for s in env.svc.get_setup(OPERATOR, SHOP)["sections"] for i in s["items"]}
    assert blocked["activate:catalog.3d"]["state"] == "blocked"
    assert "no partner tier is assigned" in blocked["activate:catalog.3d"]["detail"]
    env.svc.assign_tier(OPERATOR, SHOP, FLOOR)
    with pytest.raises(SetupRefused):
        env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert _state(env)[0] == "sandbox"
    assert _tier_lines(env.log)[:2] == [("activation", "customization", "refuse", "tier_unassigned"),
                                        ("assignment", "assignment", "allow", "tier_assigned")]
    assert ("activation", "customization", "refuse", "tier_excludes_capability") in _tier_lines(env.log)
    assert ("activation", "customization", "allow", "tier_within_limits") in _tier_lines(env.log)


def test_a_downgrade_resets_excluded_capabilities_in_the_same_write(env):
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    env.svc.assign_tier(OPERATOR, SHOP, FLOOR)
    assert _state(env) == ("unconfigured", "tier_excludes_capability")
    snap = env.store.snapshot("development", SHOP)
    assert snap.capabilities["catalog.3d"].state == "unconfigured" and snap.items["activate:catalog.3d"].done is False
    assert _state(env, "catalog.search")[0] == "sandbox"  # ungated: untouched
    assert ("assignment", "customization", "refuse", "tier_reset_capability") in _tier_lines(env.log)
    # Not a suspension: after an upgrade and a fresh test, activation works again.
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.w.clock.advance(minutes=1)
    _ready_for_activation(env)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert _state(env)[0] == "sandbox"


def test_a_downgrade_from_a_stale_process_resets_a_capability_activated_elsewhere(env):
    b = _process(env.store)  # process B hydrates before process A activates
    b.svc.get_setup(OPERATOR, SHOP)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    _ready_for_activation(env)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    b.svc.assign_tier(OPERATOR, SHOP, FLOOR)  # B's registry never saw the activation
    assert env.store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "unconfigured"


@pytest.mark.parametrize("result,kind", [("passed", "sandbox_operation"), ("failed", "none")])
def test_a_connection_test_in_a_stale_process_never_brings_back_a_capability_the_tier_removed(env, result, kind):
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    b = _process(env.store)
    b.svc.get_setup(OPERATOR, SHOP)  # B hydrates while 3D is active
    assert _state(b)[0] == "sandbox"
    env.svc.assign_tier(OPERATOR, SHOP, FLOOR)  # A downgrades; B's registry is now stale
    b.scripted.next = ProbeResult(result, kind, f"fx:stale:{result}", "Stale-process connection test.")
    run = b.svc.run_verification(OPERATOR, SHOP, "catalog.3d", "read_only_test")
    assert run["result"] == result  # the test itself is recorded
    snap = env.store.snapshot("development", SHOP)
    assert snap.capabilities["catalog.3d"].state == "unconfigured"  # neither refreshed nor "degraded"
    assert any(r.evidence_ref == f"fx:stale:{result}" for r in env.store.recent_runs("development", SHOP, limit=20))
    assert _state(b) == ("unconfigured", "tier_excludes_capability")  # B's view healed
    assert _tier_lines(b.log) == [("verification", "customization", "refuse", "tier_excludes_capability")]


def test_a_process_started_under_a_new_table_never_revives_a_capability_it_excludes(env):
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    swapped = _process(env.store, StaticPricingTable("placeholder-2", PLACEHOLDER_PRICING_TABLE.tiers()))
    swapped.svc.get_setup(OPERATOR, SHOP)
    assert _state(swapped) == ("unconfigured", "tier_excludes_capability")
    assert _tier_lines(swapped.log) == [("hydrate", "customization", "refuse", "tier_unknown")]
    assert env.store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "sandbox"  # reads never write
    same = _process(env.store)  # the same table: the activation stands
    same.svc.get_setup(OPERATOR, SHOP)
    assert _state(same)[0] == "sandbox" and _tier_lines(same.log) == []


def test_tier_gated_capabilities_cannot_be_registered_executable():
    w = world()
    conn = _shop(ScriptedProvider(), w.clock.now)
    conn.capabilities["catalog.3d"] = CapabilityStatus("catalog.3d", "sandbox", "declared", w.clock.now, "fx:3d",
                                                       "sandbox_operation")
    with pytest.raises(RegistryError, match="tier_gated_capability_must_be_activated"):
        w.registry.register(conn)


# =========================================================================== shelf quota mechanics (in process)
def _variant(vid, *, product="p1", price=5000, updated=T0, provider=SHOP):
    return SourceVariant(provider_id=provider, merchant_id="fictional-brand", source_product_id=product,
                         source_variant_id=vid, brand="Fictional", title=f"Item {vid}", category="top",
                         size_system=None, size_label=None, color=None, gtin=None,
                         product_url="https://brand.example.invalid/p", image_urls=(), price=Money(price, "USD"),
                         availability="in_stock", source_updated_at=updated, rights_policy_ref="fictional")


def _page(items, tombstones=(), cursor="c1"):
    return CatalogPage(tuple(items), cursor, tuple(tombstones))


def _ingest(ing, items, limit, run="r1", now=T0, tombstones=()):
    audit = IngestionAudit(run, SHOP)
    ing.ingest_page(_page(items, tombstones), provider_id=SHOP, now=now, audit=audit, max_active_listings=limit)
    return audit


def test_the_shelf_limit_refuses_each_addition_beyond_it():
    ing = CatalogIngestor()
    audit = _ingest(ing, [_variant(f"v{i}") for i in range(5)], 3)
    assert (audit.accepted, audit.new_listings, audit.quota_refused, audit.rejected) == (3, 3, 2, 2)
    assert audit.rejections == ["v3:shelf_quota_exceeded", "v4:shelf_quota_exceeded"]
    assert audit.admitted_refs == ["v0", "v1", "v2"]
    assert ing.shelf_usage(SHOP) == len(ing.offers(SHOP)) == 3
    for bad in (-1, True, "3"):
        with pytest.raises(ValueError):
            _ingest(ing, [], bad)


def test_updates_and_tombstones_are_never_refused_and_free_capacity_for_the_next_page():
    ing = CatalogIngestor()
    _ingest(ing, [_variant(f"v{i}") for i in range(3)], 3)
    later = T0 + timedelta(hours=1)
    audit = _ingest(ing, [_variant(f"v{i}", price=4000, updated=later) for i in range(3)] + [_variant("v9", updated=later)],
                    3, run="r2", now=later, tombstones=[("p1", "v0")])
    assert (audit.accepted, audit.quota_refused, audit.tombstoned) == (3, 1, 1)  # price updates pass; v9 waits
    audit = _ingest(ing, [_variant("v9", updated=later)], 3, run="r3", now=later + timedelta(minutes=5))
    assert audit.accepted == 1 and ing.shelf_usage(SHOP) == 3  # the tombstone freed v9's slot


def test_a_lower_limit_never_deletes_and_reviving_a_tombstone_counts_as_an_addition():
    ing = CatalogIngestor()
    _ingest(ing, [_variant(f"v{i}") for i in range(5)], 5)
    assert ing.shelf_usage(SHOP) == 5  # the partner is downgraded to 2: nothing is deleted
    later = T0 + timedelta(hours=1)
    audit = _ingest(ing, [_variant("v0", price=1, updated=later), _variant("v7", updated=later)], 2, run="r2",
                    now=later, tombstones=[("p1", "v1")])
    assert (audit.accepted, audit.quota_refused) == (1, 1)  # the update to v0 passes, v7 does not
    revived = _ingest(ing, [_variant("v1", updated=later + timedelta(hours=1))], 2, run="r3",
                      now=later + timedelta(hours=1))
    assert (revived.accepted, revived.quota_refused) == (0, 1)  # bringing back a tombstoned variant is an addition


def test_concurrent_pages_cannot_both_take_the_last_slot():
    ing = CatalogIngestor()
    _ingest(ing, [_variant(f"v{i}") for i in range(4)], 5)
    barrier, audits = threading.Barrier(8), []

    def page(i):
        barrier.wait()
        audits.append(_ingest(ing, [_variant(f"x{i}")], 5, run=f"t{i}"))

    threads = [threading.Thread(target=page, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(a.accepted for a in audits) == 1 and ing.shelf_usage(SHOP) == len(ing.offers(SHOP)) == 5


def test_no_limit_means_no_limit():
    assert _ingest(CatalogIngestor(), [_variant(f"v{i}") for i in range(40)], None).accepted == 40


# =========================================================================== shelf quota from the tier (both stores)
@pytest.fixture
def shelf(provider_setup_store):
    return _process(provider_setup_store, SHELF_TABLE)


def _load(env, ing, items, run="r1", tombstones=()):
    audit = IngestionAudit(run, SHOP)
    outcome, code = env.svc.load_shelf_page(ing, _page(items, tombstones), provider_id=SHOP, now=T0, audit=audit)
    return audit, outcome, code


def test_an_unassigned_connection_loads_nothing_new(shelf):
    ing = CatalogIngestor()
    audit, outcome, code = _load(shelf, ing, [_variant("v0"), _variant("v1")])
    assert (audit.accepted, audit.quota_refused, outcome, code) == (0, 2, "refuse", "tier_unassigned")
    assert ing.offers(SHOP) == []


def test_the_shelf_load_reads_the_assigned_tier_on_each_page_and_logs_each_page(shelf):
    ing = CatalogIngestor()
    shelf.svc.assign_tier(OPERATOR, SHOP, "placeholder_shelf2")
    assert _load(shelf, ing, [_variant(f"v{i}") for i in range(3)])[1:] == ("partial", "shelf_quota_exceeded")
    shelf.svc.assign_tier(OPERATOR, SHOP, "placeholder_shelf5")
    assert _load(shelf, ing, [_variant(f"w{i}") for i in range(3)], run="r2")[1:] == ("allow", "tier_within_limits")
    assert _load(shelf, ing, [], run="r3")[1:] == ("allow", "no_new_listings")
    assert _load(shelf, ing, [_variant("z0")], run="r4")[1:] == ("refuse", "shelf_quota_exceeded")  # 5 of 5
    pages = [ln for ln in shelf.log.events("provider.tier_decision") if ln["origin"] == "ingestion"]
    assert [(ln["units_requested"], ln["units_refused"]) for ln in pages] == [(3, 1), (3, 0), (0, 0), (1, 1)]
    assert {ln["actor_ref"] for ln in pages} == {None}


def test_the_shipped_placeholders_load_nothing_new_at_the_floor_and_everything_at_the_ceiling(env):
    ing = CatalogIngestor()
    env.svc.assign_tier(OPERATOR, SHOP, FLOOR)
    assert _load(env, ing, [_variant("v0")])[1:] == ("refuse", "shelf_quota_exceeded")
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    assert _load(env, ing, [_variant(f"v{i}") for i in range(30)], run="r2")[0].accepted == 30


def test_only_the_tiered_shelf_load_calls_the_ingestor_in_production_code():
    callers = []
    for path in sorted((ROOT / "brandme_core").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(fn):
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "ingest_page":
                        callers.append((path.relative_to(ROOT).as_posix(), fn.name))
    assert callers == [("brandme_core/domains/providers/setup.py", "load_shelf_page")]


# =========================================================================== check functions (no caller yet)
def _resolved(tier_id, table=PLACEHOLDER_PRICING_TABLE):
    return T.resolve_from_items({"tier": SimpleNamespace(done=True, evidence_ref=f"{tier_id}@{table.table_version}")},
                                table)


def test_analytics_is_tier_gated():
    floor, ceiling, none = _resolved(FLOOR), _resolved(CEILING), T.resolve_from_items({}, PLACEHOLDER_PRICING_TABLE)
    assert T.check_analytics(floor, Analytics.CATALOG_HEALTH).code == "tier_excludes_analytics"
    assert T.check_analytics(ceiling, Analytics.AGGREGATE_DEMAND).allowed
    assert T.check_analytics(none, Analytics.CATALOG_HEALTH).code == "tier_unassigned"
    with pytest.raises(ValueError):
        T.check_analytics(ceiling, Analytics.NONE)


def test_member_connection_needs_the_tier_first_and_only_then_reads_the_members_opt_in():
    reads = []

    def opt_in(answer):
        return lambda: reads.append(answer) or answer

    for tier, code in [(_resolved(FLOOR), "tier_excludes_member_connection"),
                       (T.resolve_from_items({}, PLACEHOLDER_PRICING_TABLE), "tier_unassigned")]:
        assert T.check_member_connection(tier, opt_in(True)).code == code
        assert T.check_member_connection(tier, opt_in(False)).code == code
    assert reads == []  # below the tier the member's choice is never read, so it cannot leak
    assert T.check_member_connection(_resolved(CEILING), opt_in(False)).code == "member_consent_required"
    assert T.check_member_connection(_resolved(CEILING), opt_in(True)).allowed
    assert reads == [False, True]


# =========================================================================== never on member paths
def test_member_facing_modules_never_read_tiers():
    modules = ["brandme_core/domains/commerce/service.py", "brandme_core/mcp/tools.py",
               "brandme_core/domains/providers/catalog.py", "brandme_core/orchestrator/runtime.py",
               "brandme_core/orchestrator/model_planner.py", "brandme_core/domains/commerce/quote.py",
               "brandme_core/domains/commerce/autonomy.py", "brandme_core/domains/commerce/delegation.py"]
    for path in modules:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        assert not any("tiers" in n for n in names), path


def test_tiers_never_appear_in_public_or_member_views(env):
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    public = json.dumps(env.w.registry.get(SHOP).to_public(), default=str)
    assert "tier" not in public and "placeholder" not in public


def test_connections_a_tier_cannot_bound_show_no_tier_block():
    from tests.test_commerce_http import Http
    h = Http()
    operator = h.bearer(["provider:admin"], client_id="ops-console")
    for provider in [c.provider_id for c in h.w.registry.all()]:  # no 3D/AR offered: nothing for a tier to bound
        view = h.call("provider.setup.get", {"provider_id": provider}, operator)
        assert view.status_code == 200, view.text
        assert "tier" not in view.json() and "tier_options" not in view.json()


# =========================================================================== logging
def test_every_tier_decision_writes_one_strict_line_without_raw_ids(env):
    from brandme_core.mcp.refs import log_ref
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    _ready_for_activation(env)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    env.svc.assign_tier(OPERATOR, SHOP, None)
    assert _tier_lines(env.log) == [
        ("assignment", "assignment", "allow", "tier_assigned"),
        ("activation", "customization", "allow", "tier_within_limits"),
        ("assignment", "assignment", "allow", "tier_cleared"),
        ("assignment", "customization", "refuse", "tier_reset_capability")]
    lines = env.log.events("provider.tier_decision")
    assert {ln["provider_ref"] for ln in lines} == {log_ref("provider", SHOP)}
    assert {ln["retention"] for ln in lines} == {"security_audit_180d"}
    text = json.dumps(env.log.lines)
    for raw in (SHOP, OPERATOR_MEMBER, MEMBER, "decision_ref"):
        assert raw not in text


GOOD_LINE = {"request_id": None, "origin": "activation", "dimension": "customization", "outcome": "allow",
             "code": "tier_within_limits", "provider_ref": "0123456789abcdef", "actor_ref": "fedcba9876543210",
             "tier_id": CEILING, "tier_source": "assigned", "placeholder": True, "table_version": "placeholder-1",
             "capability": "catalog.3d", "units_requested": None, "units_refused": None}


@pytest.mark.parametrize("change", [
    {"outcome": "allow", "code": "shelf_quota_exceeded"}, {"outcome": "partial", "origin": "activation"},
    {"provider_ref": "fixture_shop"}, {"code": "made_up"}, {"origin": "ingestion", "actor_ref": "0123456789abcdef"},
    {"origin": "assignment", "actor_ref": None}, {"origin": "verification", "actor_ref": None},
    {"origin": "hydrate"}, {"units_requested": 1, "units_refused": 2}, {"tier_id": None},
    {"tier_source": "unassigned"}, {"code": "no_new_listings"},
])
def test_the_run_log_refuses_a_malformed_tier_line(change):
    log = MemoryRunLog(strict=True)
    log.tier_decision(GOOD_LINE)
    with pytest.raises(RunLogViolation):
        log.tier_decision({**GOOD_LINE, **change})


def test_a_strict_sink_surfaces_a_bad_line_and_an_operational_failure_never_fails_the_operation(env):
    def down(record):
        raise ConnectionError("log pipeline down")

    env.svc.tier_audit = down
    assert env.svc.assign_tier(OPERATOR, SHOP, CEILING)["tier"]["tier_id"] == CEILING

    def broken(record):
        raise RunLogViolation("provider.tier_decision: bad line")

    env.svc.tier_audit = broken
    with pytest.raises(RunLogViolation):  # a malformed line is a bug: it surfaces after the write
        env.svc.assign_tier(OPERATOR, SHOP, FLOOR)
    assert env.svc.get_setup(OPERATOR, SHOP)["tier"]["tier_id"] == FLOOR
    stream = io.StringIO()
    JsonLineRunLog(environment="development", stream=stream).tier_decision({"origin": object()})
    assert json.loads(stream.getvalue())["event"] == REJECTED


# =========================================================================== HTTP
def test_tier_assignment_over_http_is_operator_only_needs_if_match_and_round_trips():
    from tests.test_commerce_http import Http
    h = Http()
    operator = h.bearer(["provider:admin"], client_id="ops-console")
    v = {"If-Match": '"1"'}
    assert h.call("provider.tier.assign", {"provider_id": "demo_atelier", "tier_id": CEILING}, None, v).status_code \
        == 403
    missing = h.call("provider.tier.assign", {"provider_id": "demo_atelier", "tier_id": CEILING}, operator)
    assert missing.status_code == 428
    version = h.call("provider.setup.get", {"provider_id": "demo_atelier"}, operator).json()["version"]
    ok = h.call("provider.tier.assign", {"provider_id": "demo_atelier", "tier_id": CEILING}, operator,
                {"If-Match": f'"{version}"'})
    assert ok.status_code == 200, ok.text
    assert ok.json()["tier"]["tier_id"] == CEILING and "decision_ref" not in ok.text
    stale = h.call("provider.tier.assign", {"provider_id": "demo_atelier", "tier_id": None}, operator,
                   {"If-Match": '"99"'})
    assert stale.status_code == 409
    extra = h.call("provider.tier.assign", {"provider_id": "demo_atelier", "tier_id": None, "price": "1"}, operator, v)
    assert extra.status_code == 400 and extra.json()["code"] == "unexpected_field"
    assert [ln["code"] for ln in h.tier_log.events("provider.tier_decision")] == ["tier_assigned"]
