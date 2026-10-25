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


class _ProtocolTable:
    """A PricingTable that is not a StaticPricingTable, so none of its constructor checks ran."""

    def __init__(self, version, tiers):
        self.table_version, self._tiers = version, tuple(tiers)

    def get(self, tier_id):
        return next((t for t in self._tiers if getattr(t, "tier_id", None) == tier_id), None)

    def tiers(self):
        return self._tiers


def test_any_supplied_table_is_checked_before_it_can_drive_enforcement():
    floor = PLACEHOLDER_PRICING_TABLE.get(FLOOR)
    gold = TierDefinition("gold", "Gold", T.NO_TIER, False, decision_ref="founder-decision-1")
    cases = [("development", _ProtocolTable("Bad Version!", (floor,)), "table_version_invalid"),
             ("development", _ProtocolTable(None, (floor,)), "table_version_invalid"),
             ("development", _ProtocolTable("t-1", (floor, {"tier_id": "x"})), "tier_definition_invalid"),
             ("production", _ProtocolTable("t-1", (gold, gold)), "duplicate_tier"),
             ("production", _ProtocolTable("t-1", (gold, floor)), "placeholder_pricing_table_refused"),
             ("production", _ProtocolTable("t-1", ()), "placeholder_pricing_table_refused")]
    for environment, table, code in cases:
        with pytest.raises(TierConfigError) as e:
            T.pricing_table_for(environment, table)
        assert e.value.code == code, (environment, code)
    ok = _ProtocolTable("t-1", (gold,))
    assert T.pricing_table_for("production", ok) is ok


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


class _StoreDown(Exception):
    pass


class _Interleave:
    """A process's handle on the shared store, with one write (by another process, or another call of this one)
    slipped in at a chosen point, each used once: just before this handle's next transaction (``before_next``),
    just after its next commit (``after_next``), or just after its next snapshot read (``after_read``). And
    ``fail_read_after_commit``: an error the first read after the next commit raises."""

    def __init__(self, store):
        self._store = store
        self.before_next = self.after_next = self.after_read = self.fail_read_after_commit = None
        self._fail_read = None

    def __getattr__(self, name):
        return getattr(self._store, name)

    def transact(self, *args, **kwargs):
        before, self.before_next = self.before_next, None
        if before is not None:
            before()
        result = self._store.transact(*args, **kwargs)
        self._fail_read, self.fail_read_after_commit = self.fail_read_after_commit, None
        after, self.after_next = self.after_next, None
        if after is not None:
            after()
        return result

    def snapshot(self, *args, **kwargs):
        if self._fail_read is not None:
            error, self._fail_read = self._fail_read, None
            raise error
        snap = self._store.snapshot(*args, **kwargs)
        hook, self.after_read = self.after_read, None
        if hook is not None:
            hook()
        return snap


def _active_3d_with_a_stale_reader(env, store=None):
    """A activates 3D under the ceiling; B reads it while active (B's registry then shows 3D enabled)."""
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    b = _process(store or env.store)
    b.svc.get_setup(OPERATOR, SHOP)
    assert _state(b)[0] == "sandbox"
    return b


def _stale_test(b, result, kind):
    b.scripted.next = ProbeResult(result, kind, f"fx:stale:{result}", "Stale-process connection test.")
    run = b.svc.run_verification(OPERATOR, SHOP, "catalog.3d", "read_only_test")
    assert run["result"] == result  # the test itself is recorded
    assert any(r.evidence_ref == f"fx:stale:{result}" for r in b.store.recent_runs("development", SHOP, limit=20))
    return run


@pytest.mark.parametrize("result,kind", [("passed", "sandbox_operation"), ("failed", "none")])
def test_a_connection_test_in_a_stale_process_never_brings_back_a_capability_the_tier_removed(env, result, kind):
    b = _active_3d_with_a_stale_reader(env)
    env.svc.assign_tier(OPERATOR, SHOP, FLOOR)  # A downgrades; B's registry is now stale
    run = _stale_test(b, result, kind)
    assert env.store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "unconfigured"  # neither
    assert run["capability_state"]["state"] == "unconfigured"  # refreshed nor "degraded"
    assert _state(b) == ("unconfigured", "tier_excludes_capability")  # B caught up before testing
    assert _tier_lines(b.log) == []  # the store already said unconfigured: nothing for the tier to refuse


@pytest.mark.parametrize("result,kind", [("passed", "sandbox_operation"), ("failed", "none")])
def test_a_downgrade_landing_between_a_stale_processs_read_and_its_test_write_still_wins(env, result, kind):
    shared = _Interleave(env.store)
    b = _active_3d_with_a_stale_reader(env, shared)
    shared.before_next = lambda: env.svc.assign_tier(OPERATOR, SHOP, FLOOR)  # after B caught up, before B writes
    _stale_test(b, result, kind)
    assert shared.before_next is None  # the downgrade did land inside the window
    assert env.store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "unconfigured"
    assert _state(b) == ("unconfigured", "tier_excludes_capability")  # B applies the committed rows afterwards


def test_an_upgrade_after_a_downgrade_never_re_enables_through_a_stale_processs_passing_test(env):
    b = _active_3d_with_a_stale_reader(env)
    env.svc.assign_tier(OPERATOR, SHOP, FLOOR)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)  # back up: the tier allows 3D again, but nothing re-activated it
    _stale_test(b, "passed", "sandbox_operation")
    assert env.store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "unconfigured"
    assert _state(b)[0] == "unconfigured" and _state(env)[0] == "unconfigured"


@pytest.mark.parametrize("result,kind", [("passed", "sandbox_operation"), ("failed", "none")])
def test_a_downgrade_and_re_upgrade_landing_inside_a_stale_processs_test_never_re_enables(env, result, kind):
    """The test decides on the persisted state read in its own transaction. Here the tier allows 3D again when
    B's write runs, but nothing re-activated it: neither a passing nor a failing test may make it executable."""
    shared = _Interleave(env.store)
    b = _active_3d_with_a_stale_reader(env, shared)

    def down_and_up():
        env.svc.assign_tier(OPERATOR, SHOP, FLOOR)
        env.svc.assign_tier(OPERATOR, SHOP, CEILING)

    shared.before_next = down_and_up  # after B caught up, before B's test write
    _stale_test(b, result, kind)
    assert shared.before_next is None
    assert env.store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "unconfigured"
    assert _state(b)[0] == "unconfigured"


def test_a_downgrade_committed_right_after_an_activation_in_the_same_process_is_what_the_registry_shows(
        provider_setup_store):
    shared = _Interleave(provider_setup_store)
    a = _process(shared)
    _ready_for_activation(a)
    a.svc.assign_tier(OPERATOR, SHOP, CEILING)
    shared.after_next = lambda: a.svc.assign_tier(OPERATOR, SHOP, FLOOR)  # between the commit and the registry
    a.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert shared.after_next is None
    assert provider_setup_store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "unconfigured"
    assert _state(a) == ("unconfigured", "tier_excludes_capability")  # never the activation's pre-commit value


def test_a_snapshot_read_before_a_newer_write_never_overwrites_it(provider_setup_store):
    shared = _Interleave(provider_setup_store)
    a = _process(shared)
    _ready_for_activation(a)
    a.svc.assign_tier(OPERATOR, SHOP, CEILING)
    a.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    _process(provider_setup_store).svc.update_setup(OPERATOR, SHOP, {"account_ref": "fictional-fixture-account-2"})
    shared.after_read = lambda: a.svc.assign_tier(OPERATOR, SHOP, FLOOR)  # newer than the snapshot just read
    a.svc.list_runs(OPERATOR, SHOP)
    assert shared.after_read is None
    assert _state(a) == ("unconfigured", "tier_excludes_capability")


def test_a_suspension_in_this_process_survives_refreshes_and_connection_tests(env):
    env.scripted.next = ProbeResult("passed", "sandbox_operation", "fx:run:search", "Searched one listing.")
    env.svc.run_verification(OPERATOR, SHOP, "catalog.search", "read_only_test")
    assert env.store.snapshot("development", SHOP).capabilities["catalog.search"].state == "sandbox"
    env.w.registry.suspend(SHOP, "catalog.search", "operator_hold", env.w.clock.now)
    _process(env.store).svc.update_setup(OPERATOR, SHOP, {"account_ref": "fictional-fixture-account-2"})
    env.svc.list_runs(OPERATOR, SHOP)  # applies the newer version
    assert _state(env, "catalog.search") == ("suspended", "operator_hold")
    env.scripted.next = ProbeResult("passed", "sandbox_operation", "fx:run:search2", "Searched one listing.")
    env.svc.run_verification(OPERATOR, SHOP, "catalog.search", "read_only_test")
    assert _state(env, "catalog.search") == ("suspended", "operator_hold")  # a passing test never lifts it
    assert env.store.snapshot("development", SHOP).capabilities["catalog.search"].evidence_ref == "fx:run:search"


def test_a_suspension_landing_inside_a_refresh_is_kept(env, monkeypatch):
    env.scripted.next = ProbeResult("passed", "sandbox_operation", "fx:run:search", "Searched one listing.")
    env.svc.run_verification(OPERATOR, SHOP, "catalog.search", "read_only_test")
    _process(env.store).svc.update_setup(OPERATOR, SHOP, {"account_ref": "fictional-fixture-account-2"})
    real, fired = env.w.registry.set_capability, []

    def suspended_after_the_check(provider_id, status, **kwargs):
        if status.name == "catalog.search" and not fired:  # between _refresh's check and its write
            fired.append(True)
            env.w.registry.suspend(SHOP, "catalog.search", "operator_hold", env.w.clock.now)
        return real(provider_id, status, **kwargs)

    monkeypatch.setattr(env.w.registry, "set_capability", suspended_after_the_check)
    env.svc.list_runs(OPERATOR, SHOP)
    assert fired and _state(env, "catalog.search") == ("suspended", "operator_hold")


def test_a_strict_log_refusing_an_activation_refusal_line_never_replaces_the_refusal(env):
    def broken(record):
        raise RunLogViolation("provider.tier_decision: bad line")

    _ready_for_activation(env)
    env.svc.tier_audit = broken
    with pytest.raises(SetupRefused) as e:  # no tier assigned
        env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert e.value.code == "activation_tier_excludes_capability"
    assert any("tier decision log refused a line" in n for n in getattr(e.value, "__notes__", []))


def test_a_failed_read_after_a_committed_write_still_writes_its_decision_lines(provider_setup_store):
    shared = _Interleave(provider_setup_store)
    a = _process(shared)
    _ready_for_activation(a)
    a.svc.assign_tier(OPERATOR, SHOP, CEILING)
    shared.fail_read_after_commit = _StoreDown("snapshot unavailable")
    with pytest.raises(_StoreDown):
        a.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert _tier_lines(a.log)[-1] == ("activation", "customization", "allow", "tier_within_limits")
    shared.fail_read_after_commit = _StoreDown("snapshot unavailable")
    with pytest.raises(_StoreDown):
        a.svc.assign_tier(OPERATOR, SHOP, FLOOR)
    assert provider_setup_store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "unconfigured"
    assert _tier_lines(a.log)[-2:] == [("assignment", "assignment", "allow", "tier_assigned"),
                                       ("assignment", "customization", "refuse", "tier_reset_capability")]
    a.svc.get_setup(OPERATOR, SHOP)  # the next call catches up
    assert _state(a) == ("unconfigured", "tier_excludes_capability")


def test_a_failed_read_after_a_connection_test_still_writes_its_refusal_and_a_strict_refusal_is_a_note(env):
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    shared = _Interleave(env.store)
    swapped = _process(shared, StaticPricingTable("placeholder-2", PLACEHOLDER_PRICING_TABLE.tiers()))
    swapped.svc.get_setup(OPERATOR, SHOP)
    shared.fail_read_after_commit = _StoreDown("snapshot unavailable")
    with pytest.raises(_StoreDown):
        _stale_test(swapped, "failed", "none")
    assert _tier_lines(swapped.log)[-1] == ("verification", "customization", "refuse", "tier_unknown")

    def broken(record):
        raise RunLogViolation("provider.tier_decision: bad line")

    a = _process(shared)
    a.svc.get_setup(OPERATOR, SHOP)
    a.svc.tier_audit = broken
    shared.fail_read_after_commit = _StoreDown("snapshot unavailable")
    with pytest.raises(_StoreDown) as e:  # the read error propagates; the log's refusal rides on it
        a.svc.assign_tier(OPERATOR, SHOP, FLOOR)
    assert any("tier decision log refused a line" in n for n in getattr(e.value, "__notes__", []))


def test_a_hydrate_refusal_is_logged_once_however_often_the_version_moves(env):
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    swapped = _process(env.store, StaticPricingTable("placeholder-2", PLACEHOLDER_PRICING_TABLE.tiers()))
    for i in range(3):
        swapped.svc.get_setup(OPERATOR, SHOP)
        env.svc.update_setup(OPERATOR, SHOP, {"account_ref": f"fictional-fixture-account-{i}"})
    swapped.svc.get_setup(OPERATOR, SHOP)
    assert _tier_lines(swapped.log) == [("hydrate", "customization", "refuse", "tier_unknown")]
    assert _state(swapped) == ("unconfigured", "tier_excludes_capability")


@pytest.mark.parametrize("retest", [True, False])
@pytest.mark.parametrize("sees_the_reset", [True, False])
def test_a_fresh_activation_is_logged_again_whether_or_not_the_reset_was_seen(env, sees_the_reset, retest):
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    swapped = _process(env.store, StaticPricingTable("placeholder-2", PLACEHOLDER_PRICING_TABLE.tiers()))
    swapped.svc.get_setup(OPERATOR, SHOP)
    env.svc.assign_tier(OPERATOR, SHOP, FLOOR)  # resets the activation
    if sees_the_reset:
        swapped.svc.get_setup(OPERATOR, SHOP)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.w.clock.advance(minutes=1)
    if retest:
        _ready_for_activation(env)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})  # a new operator act (maybe the same test)
    swapped.svc.get_setup(OPERATOR, SHOP)
    assert _tier_lines(swapped.log) == [("hydrate", "customization", "refuse", "tier_unknown")] * 2


def test_a_re_test_elsewhere_never_logs_the_same_activations_hydrate_refusal_again(env):
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    swapped = _process(env.store, StaticPricingTable("placeholder-2", PLACEHOLDER_PRICING_TABLE.tiers()))
    swapped.svc.get_setup(OPERATOR, SHOP)
    for i, (result, kind) in enumerate([("passed", "sandbox_operation"), ("failed", "none")]):
        env.w.clock.advance(minutes=1)
        env.scripted.next = ProbeResult(result, kind, f"fx:retest:{i}", "Routine re-test.")
        env.svc.run_verification(OPERATOR, SHOP, "catalog.3d", "read_only_test")  # rewrites the capability row
        swapped.svc.get_setup(OPERATOR, SHOP)
    assert _tier_lines(swapped.log) == [("hydrate", "customization", "refuse", "tier_unknown")]


def test_a_connection_test_under_a_tier_that_excludes_a_persisted_activation_records_only_the_run(env):
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    swapped = _process(env.store, StaticPricingTable("placeholder-2", PLACEHOLDER_PRICING_TABLE.tiers()))
    _stale_test(swapped, "failed", "none")
    assert env.store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "sandbox"  # not degraded
    assert _state(swapped) == ("unconfigured", "tier_excludes_capability")
    assert _tier_lines(swapped.log) == [("hydrate", "customization", "refuse", "tier_unknown"),
                                        ("verification", "customization", "refuse", "tier_unknown")]


def test_a_stale_process_catches_up_on_its_next_setup_call(env):
    b = _active_3d_with_a_stale_reader(env)
    env.svc.assign_tier(OPERATOR, SHOP, FLOOR)
    assert _state(b)[0] == "sandbox"  # stale until it next touches setup
    b.svc.list_runs(OPERATOR, SHOP)
    assert _state(b) == ("unconfigured", "tier_excludes_capability")
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.w.clock.advance(minutes=1)
    _ready_for_activation(env)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    b.svc.get_setup(OPERATOR, SHOP)
    assert _state(b)[0] == "sandbox"  # a re-activation elsewhere reaches B the same way


def test_activation_reads_the_tier_inside_its_own_transaction(env):
    shared = _Interleave(env.store)
    b = _process(shared)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    _ready_for_activation(b)
    shared.before_next = lambda: env.svc.assign_tier(OPERATOR, SHOP, FLOOR)  # B already read the ceiling
    with pytest.raises(SetupRefused) as e:
        b.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert e.value.code == "activation_tier_excludes_capability" and shared.before_next is None
    assert "catalog.3d" not in env.store.snapshot("development", SHOP).capabilities
    assert _tier_lines(b.log)[-1] == ("activation", "customization", "refuse", "tier_excludes_capability")


def test_an_assignment_never_resets_a_capability_the_new_tier_still_includes(env):
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)  # re-assigned unchanged
    assert _state(env)[0] == "sandbox"
    assert env.store.snapshot("development", SHOP).items["activate:catalog.3d"].done is True
    assert ("assignment", "customization", "refuse", "tier_reset_capability") not in _tier_lines(env.log)


def test_reassigning_under_a_new_table_resets_an_activation_the_old_table_granted(env):
    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    table2 = StaticPricingTable("placeholder-2", PLACEHOLDER_PRICING_TABLE.tiers())
    swapped = _process(env.store, table2)
    swapped.svc.assign_tier(OPERATOR, SHOP, CEILING)  # ceiling@placeholder-2: allowed now, but never activated
    snap = env.store.snapshot("development", SHOP)
    assert snap.capabilities["catalog.3d"].state == "unconfigured" and snap.items["activate:catalog.3d"].done is False
    fresh = _process(env.store, table2)
    fresh.svc.get_setup(OPERATOR, SHOP)
    assert _state(fresh)[0] == "unconfigured"  # the old activation never comes back under the new table


def test_a_3d_tier_activates_3d_but_never_ar_try_on(provider_setup_store):
    studio = StaticPricingTable("placeholder-3d", (_placeholder("placeholder_3d", None, Customization.THREE_D),))
    env = _process(provider_setup_store, studio)
    env.svc.assign_tier(OPERATOR, SHOP, "placeholder_3d")
    _ready_for_activation(env, "tryon.photo")
    with pytest.raises(SetupRefused) as e:
        env.svc.update_setup(OPERATOR, SHOP, {"activate": "tryon.photo"})
    assert e.value.code == "activation_tier_excludes_capability" and _state(env, "tryon.photo")[0] == "unconfigured"
    env.w.clock.advance(minutes=1)
    _ready_for_activation(env)
    env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert _state(env)[0] == "sandbox"
    tier = T.resolve_from_items(env.store.snapshot("development", SHOP).items, studio)
    assert [T.check_capability(tier, c).allowed for c in ("catalog.3d", "tryon.photo", "tryon.live")] == [
        True, False, False]  # live try-on is AR too


def test_a_strict_tier_sink_raises_only_after_the_registry_and_store_are_updated(env):
    def broken(record):
        raise RunLogViolation("provider.tier_decision: bad line")

    _ready_for_activation(env)
    env.svc.assign_tier(OPERATOR, SHOP, CEILING)
    env.svc.tier_audit = broken
    with pytest.raises(RunLogViolation):
        env.svc.update_setup(OPERATOR, SHOP, {"activate": "catalog.3d"})
    assert _state(env)[0] == "sandbox"
    assert env.store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "sandbox"
    with pytest.raises(RunLogViolation):
        env.svc.assign_tier(OPERATOR, SHOP, FLOOR)
    assert _state(env) == ("unconfigured", "tier_excludes_capability")
    assert env.store.snapshot("development", SHOP).capabilities["catalog.3d"].state == "unconfigured"


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


@pytest.mark.parametrize("capability", sorted(T.GATED_CAPABILITIES))
def test_tier_gated_capabilities_never_become_executable_outside_the_tier_checked_setup_path(capability):
    w = world()
    conn = _shop(ScriptedProvider(), w.clock.now)

    def enabled():
        return CapabilityStatus(capability, "sandbox", "declared", w.clock.now, "fx:x", "sandbox_operation")

    conn.capabilities[capability] = enabled()
    with pytest.raises(RegistryError, match="tier_gated_capability_must_be_activated"):
        w.registry.register(conn)  # an adapter cannot declare it enabled
    conn.capabilities[capability] = CapabilityStatus(capability, "unconfigured", "activation_pending_verification")
    w.registry.register(conn)
    for bypass in (lambda: w.registry.set_capability(SHOP, enabled()),
                   lambda: w.registry.record_verification(SHOP, capability, evidence_ref="fx:x",
                                                          evidence_kind="sandbox_operation", checked_at=w.clock.now)):
        with pytest.raises(RegistryError, match="tier_gated_capability_must_be_activated"):
            bypass()
        assert w.registry.get(SHOP).capability(capability).state == "unconfigured"
    w.registry.set_capability(SHOP, enabled(), tier_checked=True)  # only the setup service passes the tier check
    assert w.registry.get(SHOP).capability(capability).state == "sandbox"
    w.registry.suspend(SHOP, capability, "operator_suspended", w.clock.now)  # never blocks a step down
    assert w.registry.get(SHOP).capability(capability).state == "suspended"


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


def test_updates_and_tombstones_are_never_refused_and_a_pages_tombstones_free_its_slots():
    ing = CatalogIngestor()
    _ingest(ing, [_variant(f"v{i}") for i in range(3)], 3)
    later = T0 + timedelta(hours=1)
    audit = _ingest(ing, [_variant(f"v{i}", price=4000, updated=later) for i in range(3)] + [_variant("v9", updated=later)],
                    3, run="r2", now=later, tombstones=[("p1", "v0")])
    # At the cap: price updates pass, and swapping v0 for v9 in one page stays within the limit.
    assert (audit.accepted, audit.new_listings, audit.quota_refused, audit.tombstoned) == (4, 1, 0, 1)
    assert ing.shelf_usage(SHOP) == 3
    swap = _ingest(ing, [_variant("v7", updated=later), _variant("v8", updated=later)], 3, run="r3", now=later,
                   tombstones=[("p1", "v1")])
    assert (swap.new_listings, swap.quota_refused, swap.admitted_refs) == (1, 1, ["v7"])  # one slot freed, one taken
    audit = _ingest(ing, [], 3, run="r4", now=later, tombstones=[("p1", "v2")])
    audit = _ingest(ing, [_variant("v8", updated=later)], 3, run="r5", now=later + timedelta(minutes=5))
    assert audit.accepted == 1 and ing.shelf_usage(SHOP) == 3  # an earlier page's tombstone freed v8's slot


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


def test_a_page_that_fails_part_way_still_logs_what_it_admitted(shelf):
    class FailsAfterOne(CatalogIngestor):
        def ingest_page(self, page, **kwargs):
            super().ingest_page(CatalogPage(page.items[:1], page.next_cursor, ()), **kwargs)
            raise RuntimeError("shelf write failed")

    ing = FailsAfterOne()
    shelf.svc.assign_tier(OPERATOR, SHOP, "placeholder_shelf5")
    with pytest.raises(RuntimeError):
        _load(shelf, ing, [_variant("v0"), _variant("v1")])
    pages = [ln for ln in shelf.log.events("provider.tier_decision") if ln["origin"] == "ingestion"]
    assert [(ln["outcome"], ln["units_requested"], ln["units_refused"]) for ln in pages] == [("allow", 1, 0)]


def test_overlapping_pages_sharing_one_audit_each_log_their_own_counts(shelf):
    class Lockstep(CatalogIngestor):
        """Both pages start before either ingests, and both have ingested before either logs its line."""

        def __init__(self):
            super().__init__()
            self.started, self.ingested = threading.Barrier(3, timeout=10), threading.Barrier(3, timeout=10)

        def ingest_page(self, page, **kwargs):
            self.started.wait()
            super().ingest_page(page, **kwargs)
            self.ingested.wait()

    ing = Lockstep()
    shelf.svc.assign_tier(OPERATOR, SHOP, "placeholder_shelf2")  # three pages, two slots: one is refused
    audit, errors = IngestionAudit("shared", SHOP), []

    def page(i):
        try:
            shelf.svc.load_shelf_page(ing, _page([_variant(f"x{i}")]), provider_id=SHOP, now=T0, audit=audit)
        except Exception as e:  # pragma: no cover - surfaced below
            errors.append(e)

    threads = [threading.Thread(target=page, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    pages = [ln for ln in shelf.log.events("provider.tier_decision") if ln["origin"] == "ingestion"]
    assert [ln["units_requested"] for ln in pages] == [1, 1, 1]  # never another page's addition or refusal
    assert sum(ln["units_refused"] for ln in pages) == 1 == audit.quota_refused
    assert audit.new_listings == 2 == ing.shelf_usage(SHOP)


def test_a_page_that_fails_part_way_changes_nothing_and_never_keeps_a_swap_over_the_limit(shelf):
    ing = CatalogIngestor()
    shelf.svc.assign_tier(OPERATOR, SHOP, "placeholder_shelf3")
    audit = IngestionAudit("multi-page", SHOP)  # one audit across pages, as a feed load keeps it
    shelf.svc.load_shelf_page(ing, _page([_variant(f"v{i}") for i in range(3)], cursor="c1"), provider_id=SHOP,
                              now=T0, audit=audit)
    before = replace(audit, rejections=list(audit.rejections), admitted_refs=list(audit.admitted_refs))
    lines = len(shelf.log.events("provider.tier_decision"))
    later = T0 + timedelta(hours=1)
    broken = replace(_variant("vx", updated=later), product_url=None)  # a malformed provider record
    with pytest.raises(AttributeError):
        shelf.svc.load_shelf_page(ing, _page([_variant("v9", updated=later), broken], [("p1", "v0")], cursor="c2"),
                                  provider_id=SHOP, now=later, audit=audit)
    assert {v.source_variant_id for v in ing.offers(SHOP)} == {"v0", "v1", "v2"}  # v9 kept nothing
    assert ing.cursors[SHOP] == "c1" and audit == before  # retried from the same place; nothing half-counted
    assert len(shelf.log.events("provider.tier_decision")) == lines  # no line: it would read as an empty page


def test_tombstones_are_read_once_from_any_iterable_and_a_malformed_one_refuses_the_page():
    ing = CatalogIngestor()
    _ingest(ing, [_variant(f"v{i}") for i in range(3)], 3)
    later = T0 + timedelta(hours=1)
    swap = CatalogPage((_variant("v9", updated=later),), "c2", (t for t in [("p1", "v0")]))  # a one-pass iterable
    audit = IngestionAudit("r2", SHOP)
    ing.ingest_page(swap, provider_id=SHOP, now=later, audit=audit, max_active_listings=3)
    assert (audit.new_listings, audit.tombstoned, ing.shelf_usage(SHOP)) == (1, 1, 3)
    decoded = CatalogPage((), "c3", [["p1", "v1"]])  # pairs decoded from the JSON wire arrive as lists
    ing.ingest_page(decoded, provider_id=SHOP, now=later, audit=IngestionAudit("r3", SHOP), max_active_listings=3)
    assert ing.shelf_usage(SHOP) == 2
    for bad in ([("p1",)], [("p1", 7)], ["p1v2"], [{"source_product_id": "p1", "source_variant_id": "v2"}],
                [frozenset({"p1", "v2"})], [("p1", "")]):
        with pytest.raises(ValueError):
            ing.ingest_page(CatalogPage((_variant("v8", updated=later),), "c4", bad), provider_id=SHOP, now=later,
                            audit=IngestionAudit("r4", SHOP), max_active_listings=3)
    assert "v8" not in {v.source_variant_id for v in ing.offers(SHOP)} and ing.cursors[SHOP] == "c3"


@pytest.mark.parametrize("second", ["stored", "in_the_page", "both_in_the_page", "rejected_in_the_page"])
def test_a_tombstone_matching_two_merchants_refuses_the_page_and_drops_neither_listing(second):
    """Tombstones carry no merchant on the wire. Two merchants at one provider may share source ids, so a
    tombstone that matches both, whether stored, arriving in the same page, or only seen in the page, is refused
    instead of discontinuing the other merchant's live listing. Nothing is written, counted or moved."""
    ing = CatalogIngestor()
    mine, theirs = _variant("1001-S"), replace(_variant("1001-S"), merchant_id="another-fictional-brand")
    stored = {"stored": [mine, theirs], "both_in_the_page": [_variant("v0")]}.get(second, [mine])
    in_page = {"in_the_page": [theirs], "both_in_the_page": [mine, theirs],
               "rejected_in_the_page": [replace(theirs, price=Money(0, "USD"))]}.get(second, [])
    audit = IngestionAudit("multi-page", SHOP)
    ing.ingest_page(_page(stored, cursor="c1"), provider_id=SHOP, now=T0, audit=audit)
    before_offers = sorted((v.merchant_id, v.source_variant_id) for v in ing.offers(SHOP))
    before = replace(audit, rejections=list(audit.rejections), admitted_refs=list(audit.admitted_refs))
    with pytest.raises(ValueError):
        ing.ingest_page(_page(in_page + [_variant("v9")], [("p1", "1001-S")], cursor="c2"), provider_id=SHOP,
                        now=T0 + timedelta(hours=1), audit=audit)
    assert sorted((v.merchant_id, v.source_variant_id) for v in ing.offers(SHOP)) == before_offers
    assert ing.cursors[SHOP] == "c1" and audit == before


def test_one_providers_tombstones_never_touch_another_providers_variants():
    ing, other = CatalogIngestor(), "another_fixture_shop"
    _ingest(ing, [_variant("v0")], None)
    ing.ingest_page(_page([_variant("v0", provider=other)]), provider_id=other, now=T0,
                    audit=IngestionAudit("o1", other))
    ing.ingest_page(_page([], [("p1", "v0")]), provider_id=other, now=T0, audit=IngestionAudit("o2", other))
    assert [v.provider_id for v in ing.offers(SHOP)] == [SHOP] and ing.offers(other) == []


def test_a_variant_a_page_adds_and_tombstones_takes_no_slot():
    ing = CatalogIngestor()
    _ingest(ing, [_variant("v0"), _variant("v1")], 3)
    audit = _ingest(ing, [_variant("x"), _variant("y")], 3, run="r2", tombstones=[("p1", "x")])
    assert (audit.new_listings, audit.quota_refused, audit.tombstoned) == (1, 0, 1)
    assert {v.source_variant_id for v in ing.offers(SHOP)} == {"v0", "v1", "y"}


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
    for truthy in (1, "yes", "true", [True], object()):  # only an explicit True is an opt-in
        assert T.check_member_connection(_resolved(CEILING), lambda v=truthy: v).code == "member_consent_required"


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
    {"origin": "hydrate", "actor_ref": None}, {"origin": "verification"}, {"capability": None},
    {"tier_source": "assigned_unknown", "tier_id": None},
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


def test_a_tier_line_from_an_http_request_carries_that_requests_id():
    from tests.test_commerce_http import Http
    h = Http()
    operator = h.bearer(["provider:admin"], client_id="ops-console")
    rid = "5d2e8a41-7c3b-4f90-9e16-0a4b8c2d6f17"
    version = h.call("provider.setup.get", {"provider_id": "demo_atelier"}, operator).json()["version"]
    ok = h.call("provider.tier.assign", {"provider_id": "demo_atelier", "tier_id": CEILING}, operator,
                {"If-Match": f'"{version}"', "X-Request-Id": rid})
    assert ok.status_code == 200, ok.text
    assert [ln["request_id"] for ln in h.tier_log.events("provider.tier_decision")] == [rid]
    h.tier_log.tier_decision({**GOOD_LINE, "request_id": "not-a-uuid; raw header"})
    assert h.tier_log.events("provider.tier_decision")[-1]["request_id"] is None  # never a raw header value
    assert T.decision_record(origin="assignment", dimension="assignment", outcome="allow", code="tier_cleared",
                             provider_id="demo_atelier", tier=T.resolve_from_items({}, PLACEHOLDER_PRICING_TABLE),
                             actor_ref="op")["request_id"] is None  # outside a request: none, never a stale one
