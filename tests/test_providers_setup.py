"""Operator provider setup and connection tests (ch.05 §8): in-memory and Spanner emulator stores.

All providers, accounts and secret names here are fictional; no secret values exist in this file
except deliberately fake ones that must be refused.
"""

import json
import secrets
from dataclasses import replace
from types import SimpleNamespace

import pytest

from brandme_core.domains.commerce.errors import Forbidden, InvalidRequest, VersionConflict
from brandme_core.domains.commerce.principal import Principal
from brandme_core.domains.providers import nordstrom
from brandme_core.domains.providers.contracts import ProbeResult, SETUP_SECTIONS
from brandme_core.domains.providers.local_atelier import PROBE_VARIANT, PROVIDER_ID, Behavior
from brandme_core.domains.providers.registry import CapabilityStatus, ProviderConnection
from brandme_core.domains.providers.setup import (
    ProviderSetupService, SetupRefused, looks_like_secret, operator_ref,
)
from tests.fixtures.commerce.harness import MEMBER, member_session, world
from tests.fixtures.commerce.stores import _spanner_db, provider_setup_store  # noqa: F401  (fixtures)

OPERATOR_MEMBER = "7c0b9a52-3f1e-5d2a-9e64-0b1d2c3e4f50"  # fictional operator account
OPERATOR = Principal(member_id=OPERATOR_MEMBER, subject="sub-operator", session_id=None, client_id="ops-console",
                     scopes=frozenset({"provider:admin"}), assurance_level="aal2", environment="development")
SECRET_REF = "projects/brandme-dev-fictional/secrets/impact-publisher/versions/3"
NORD = nordstrom.PROVIDER_ID
RIGHTS = {r: r != "derive_3d_or_ai" for r in nordstrom.DATA_USE_RIGHTS}


class ScriptedProvider:
    """A non-simulation fixture adapter whose connection test returns what the test scripts."""

    provider_id = "fixture_shop"

    def __init__(self):
        self.next = None
        self.calls = []

    def probe(self, capability, mode, now):
        self.calls.append((capability, mode))
        if isinstance(self.next, Exception):
            raise self.next
        return self.next


def _fixture_connection(adapter, now):
    caps = {"catalog.search": CapabilityStatus("catalog.search", "sandbox", "sandbox_evidence", now, "fx:1",
                                               "sandbox_operation"),
            "catalog.feed": CapabilityStatus("catalog.feed", "unconfigured", "activation_pending_verification")}
    return ProviderConnection(provider_id="fixture_shop", display_name="Fixture Shop (fictional)",
                              environment="development", simulation=False, country_codes=("US",),
                              disclosure="Fictional fixture provider.", capabilities=caps, adapter=adapter)


@pytest.fixture
def env(provider_setup_store):
    w = world()
    w.registry.register(nordstrom.connection("development"))
    scripted = ScriptedProvider()
    w.registry.register(_fixture_connection(scripted, w.clock.now))
    svc = ProviderSetupService(w.registry, provider_setup_store, clock=w.clock)
    return SimpleNamespace(w=w, svc=svc, store=provider_setup_store, scripted=scripted)


def _states(registry, provider_id):
    return {k: (s.state, s.reason_code) for k, s in registry.get(provider_id).capabilities.items()}


def _section(view, key):
    return {i["key"]: i for i in next(s for s in view["sections"] if s["key"] == key)["items"]}


# ------------------------------------------------------------------ sections
def test_six_sections_show_missing_prerequisites_as_actionable_rows(env):  # BM-PROV-001
    view = env.svc.get_setup(OPERATOR, NORD)
    assert [s["key"] for s in view["sections"]] == list(SETUP_SECTIONS)
    assert view["editable"] is True and view["simulation"] is False
    pre = _section(view, "prerequisites")
    assert pre["apply"]["state"] == "todo" and nordstrom.OFFICIAL_PROGRAM_URL in pre["apply"]["detail"]
    assert pre["approval"]["state"] == "blocked" and "Complete first" in pre["approval"]["detail"]
    creds = _section(view, "credentials")
    assert creds["secret"]["state"] == "blocked" and "Secret Manager" in creds["secret"]["detail"]
    assert all(i["state"] == "todo" for i in _section(view, "data_use").values())
    enables = _section(view, "enables")
    assert "checkout.submit" in enables["not_offered"]["detail"]  # capability limits are visible
    assert all(i["state"] == "todo" for i in _section(view, "tests").values())
    assert all(i["state"] in ("todo", "blocked") for i in _section(view, "activation").values())
    assert not any(env.w.registry.get(NORD).can_execute(c) for c in env.w.registry.get(NORD).capabilities)


def test_simulation_setup_needs_no_credentials_and_is_labeled(env):
    view = env.svc.get_setup(OPERATOR, PROVIDER_ID)
    assert view["simulation"] is True and "Simulated provider" in view["disclosure"]
    assert _section(view, "credentials")["credential"]["state"] == "not_needed"
    assert view["editable_fields"] == [] and view["connection_test_available"] is True
    with pytest.raises(InvalidRequest) as e:
        env.svc.update_setup(OPERATOR, PROVIDER_ID, {"access_level": "approved_publisher"})
    assert e.value.code == "setup_field_not_applicable"


# ----------------------------------------------------------- partial setup
def test_saving_partial_setup_never_changes_capability_state(env):
    before = _states(env.w.registry, NORD)
    steps = [{"program_application_opened": True}, {"approval_evidence_ref": "impact-approval-fictional-0001"},
             {"account_ref": "fictional-impact-account"}, {"credential_secret_ref": SECRET_REF},
             {"catalog_ref": "fictional-nordstrom-catalog"}, {"endpoint_descriptor_ref": "impact-docs-review-0001"},
             {"data_use": RIGHTS}, {"access_level": "approved_publisher"}]
    for step in steps:
        view = env.svc.update_setup(OPERATOR, NORD, step)
        assert _states(env.w.registry, NORD) == before
        assert env.store.snapshot("development", NORD).capabilities == {}  # no capability row was written
    pre, creds = _section(view, "prerequisites"), _section(view, "credentials")
    assert all(pre[k]["state"] == "done" for k in ("access_level", "apply", "approval", "catalog", "endpoint"))
    assert creds["secret"]["state"] == "done" and creds["account"]["state"] == "done"
    assert _section(view, "data_use")["use:derive_3d_or_ai"]["detail"] == "Not permitted"
    conn = env.w.registry.get(NORD)
    assert not conn.can_execute("catalog.feed") and conn.access_level == "approved_publisher"
    assert conn.credential_ref == SECRET_REF and conn.data_use == RIGHTS  # in-process, server-only
    assert conn.adapter.setup.approval_evidence_ref == "impact-approval-fictional-0001"
    assert conn.adapter.setup.impact_approval_recorded_by == operator_ref(OPERATOR)


def test_beyond_link_only_needs_approval_evidence(env):
    with pytest.raises(SetupRefused) as e:
        env.svc.update_setup(OPERATOR, NORD, {"access_level": "approved_publisher"})
    assert e.value.code == "approval_evidence_required" and e.value.status == 409
    view = env.svc.update_setup(OPERATOR, NORD, {"access_level": "link_only"})
    pre = _section(view, "prerequisites")
    assert pre["access_level"]["state"] == "done"
    assert pre["catalog"]["state"] == "not_needed"  # only needed for approved access
    both = env.svc.update_setup(OPERATOR, NORD, {"approval_evidence_ref": "impact-approval-fictional-0001",
                                                 "access_level": "approved_publisher"})
    assert both["access_level"] == "approved_publisher"


@pytest.mark.parametrize("bad", [
    "sk_live_51Hfictionalfictional", "rk_test_fictional", "pk_live_fictional", "whsec_fictionalfictional",
    "sk-ant-api03-fictional", "-----BEGIN PRIVATE KEY-----\nMIIEfictional\n-----END PRIVATE KEY-----",
    "projects/brandme-dev/secrets/sk_live_fictional/versions/1",
])
def test_secret_values_are_refused_in_every_field_and_never_echoed(env, bad):
    for field in ("credential_secret_ref", "account_ref", "approval_evidence_ref", "catalog_ref"):
        with pytest.raises(InvalidRequest) as e:
            env.svc.update_setup(OPERATOR, NORD, {field: bad})
        assert e.value.code == "secret_value_refused", (field, e.value.code)
        assert bad not in e.value.detail
    assert env.store.snapshot("development", NORD).connection is None  # nothing was stored


def test_random_tokens_look_like_secrets_but_references_do_not():
    for _ in range(20):
        assert looks_like_secret(secrets.token_urlsafe(32)) and looks_like_secret(secrets.token_hex(32))
    for ok in (SECRET_REF, "impact-approval-2026-10-05-nordstrom", "fictional-nordstrom-catalog",
               "approved-publisher-agreement-ref-0001", "9b1f3a52-3f1e-4d2a-9e64-0b1d2c3e4f50"):
        assert not looks_like_secret(ok), ok


def test_credential_ref_is_write_only_with_fingerprint_and_rotation(env):
    with pytest.raises(InvalidRequest) as e:
        env.svc.update_setup(OPERATOR, NORD, {"credential_secret_ref": "hunter2"})
    assert e.value.code == "invalid_secret_reference"
    view = env.svc.update_setup(OPERATOR, NORD, {"credential_secret_ref": SECRET_REF,
                                                 "account_ref": "fictional-impact-account",
                                                 "approval_evidence_ref": "impact-approval-fictional-0001"})
    blob = json.dumps(view)
    for leaked in (SECRET_REF, "impact-publisher", "brandme-dev-fictional", "fictional-impact-account",
                   "impact-approval-fictional-0001", OPERATOR_MEMBER):
        assert leaked not in blob, leaked
    assert view["credential_configured"] is True and view["credential_fingerprint"].startswith("ref:")
    assert view["credential_rotated_at"] == "2026-10-05T12:00:00Z"
    env.w.clock.advance(days=3)  # stays in the past: Spanner refuses future allow_commit_timestamp values
    rotated = env.svc.update_setup(OPERATOR, NORD, {"credential_secret_ref": SECRET_REF.replace("/3", "/4")})
    assert rotated["credential_rotated_at"] == "2026-10-08T12:00:00Z"
    assert rotated["credential_fingerprint"] != view["credential_fingerprint"]
    assert env.store.snapshot("development", NORD).connection.credential_secret_ref.endswith("/versions/4")
    assert "secrets" not in json.dumps(env.w.registry.get(NORD).to_public())


def test_invalid_data_use_and_unknown_fields_rejected(env):
    for bad in ({"display_images": True}, {**RIGHTS, "train_models": True}, {**RIGHTS, "display_images": "yes"}):
        with pytest.raises(InvalidRequest) as e:
            env.svc.update_setup(OPERATOR, NORD, {"data_use": bad})
        assert e.value.code == "invalid_data_use"
    with pytest.raises(InvalidRequest) as e:
        env.svc.update_setup(OPERATOR, NORD, {"capabilities": {"catalog.feed": "verified"}})
    assert e.value.code == "unexpected_field"
    with pytest.raises(InvalidRequest):
        env.svc.update_setup(OPERATOR, NORD, {})


def test_if_match_guards_against_lost_updates(env):
    assert env.svc.get_setup(OPERATOR, NORD)["version"] == "0"
    assert env.svc.update_setup(OPERATOR, NORD, {"program_application_opened": True}, if_match=0)["version"] == "1"
    with pytest.raises(VersionConflict):
        env.svc.update_setup(OPERATOR, NORD, {"account_ref": "fictional-impact-account"}, if_match=0)


# ------------------------------------------------------------ connection tests
@pytest.mark.parametrize("capability", ["catalog.search", "catalog.detail", "inventory.read", "price.quote",
                                        "orders.webhook"])
def test_demo_probe_passes_and_records_sandbox_never_verified(env, capability):
    submits = list(env.w.provider.submit_calls)
    run = env.svc.run_verification(OPERATOR, PROVIDER_ID, capability, "read_only_test")
    assert run["result"] == "passed" and run["evidence_kind"] == "conformance_suite"
    assert run["capability"] == capability and run["environment"] == "development" and run["mode"] == "read_only_test"
    assert run["ran_at"] == "2026-10-05T12:00:00Z" and "Simulation" in run["sanitized_summary"]
    assert run["evidence_ref"] == f"sim:{PROVIDER_ID}:probe:{capability}:20261005T120000Z"
    assert run["capability_state"]["state"] == "sandbox"
    assert run["capability_state"]["reason_code"] == "deterministic_local_simulation"
    persisted = env.store.snapshot("development", PROVIDER_ID).capabilities[capability]
    assert persisted.state == "sandbox" and persisted.evidence_ref == run["evidence_ref"]
    assert env.w.provider.submit_calls == submits  # a connection test never submits
    assert not any(s.state == "verified" for s in env.w.registry.get(PROVIDER_ID).capabilities.values())


def test_demo_state_changing_capabilities_have_no_probe(env):
    before = _states(env.w.registry, PROVIDER_ID)
    run = env.svc.run_verification(OPERATOR, PROVIDER_ID, "checkout.submit", "read_only_test")
    assert run["result"] == "blocked" and run["reason_code"] == "no_read_only_probe"
    staged = env.svc.run_verification(OPERATOR, PROVIDER_ID, "catalog.search", "staging_ingestion")
    assert staged["result"] == "blocked" and staged["reason_code"] == "staging_ingestion_not_built"
    assert _states(env.w.registry, PROVIDER_ID) == before


def test_failing_probe_degrades_and_a_later_pass_restores(env):
    env.w.provider.arm(Behavior.STOCK_LOSS, source_variant_ref=PROBE_VARIANT)
    run = env.svc.run_verification(OPERATOR, PROVIDER_ID, "price.quote", "read_only_test")
    assert run["result"] == "failed" and run["reason_code"] == "simulation_contract_restricted"
    assert run["capability_state"]["state"] == "degraded"
    assert env.store.snapshot("development", PROVIDER_ID).capabilities["price.quote"].state == "degraded"
    view = env.svc.get_setup(OPERATOR, PROVIDER_ID)
    assert _section(view, "tests")["test:price.quote"]["state"] == "todo"
    assert _section(view, "enables")["cap:price.quote"]["state"] == "blocked"
    env.w.provider._stock[PROBE_VARIANT] = 5  # restock the fictional variant
    env.w.clock.advance(minutes=1)
    again = env.svc.run_verification(OPERATOR, PROVIDER_ID, "price.quote", "read_only_test")
    assert again["result"] == "passed" and again["capability_state"]["state"] == "sandbox"


def test_scripted_provider_results_follow_the_evidence_rules(env):
    s = env.scripted
    s.next = ProbeResult("failed", "sandbox_operation", "fx:run:1", "Sandbox search answered 500.", "sandbox_error")
    assert env.svc.run_verification(OPERATOR, "fixture_shop", "catalog.search", "read_only_test")[
        "capability_state"]["state"] == "degraded"
    # A failure never enables a capability that was not enabled.
    assert env.svc.run_verification(OPERATOR, "fixture_shop", "catalog.feed", "read_only_test")[
        "capability_state"]["state"] == "unconfigured"
    # Reaching a host verifies nothing.
    s.next = ProbeResult("passed", "host_reachability", "fx:ping:1", "Host answered.")
    env.w.clock.advance(seconds=1)
    r = env.svc.run_verification(OPERATOR, "fixture_shop", "catalog.search", "read_only_test")
    assert r["result"] == "passed" and r["capability_state"]["state"] == "degraded"
    # A crashing test is a failed test; summaries are sanitized.
    s.next = RuntimeError("boom")
    env.w.clock.advance(seconds=1)
    assert env.svc.run_verification(OPERATOR, "fixture_shop", "catalog.feed", "read_only_test")[
        "reason_code"] == "probe_error"
    s.next = ProbeResult("passed", "sandbox_operation", "fx:run:2",
                         "Fetched 3 records with key sk_live_fictionalfictional for buyer@example.com")
    env.w.clock.advance(seconds=1)
    passed = env.svc.run_verification(OPERATOR, "fixture_shop", "catalog.search", "read_only_test")
    assert "sk_live" not in passed["sanitized_summary"] and "buyer@example.com" not in passed["sanitized_summary"]
    assert passed["capability_state"]["state"] == "sandbox"  # sandbox evidence in development, never verified
    assert passed["capability_state"]["reason_code"] == "sandbox_evidence"


def test_blocked_for_adapters_without_probes_and_unoffered_capabilities(env):
    plain = SimpleNamespace(provider_id="plain_shop")  # no probe()
    conn = _fixture_connection(plain, env.w.clock.now)
    conn.provider_id = "plain_shop"
    env.w.registry.register(conn)
    before = _states(env.w.registry, "plain_shop")
    run = env.svc.run_verification(OPERATOR, "plain_shop", "catalog.search", "read_only_test")
    assert run["result"] == "blocked" and run["reason_code"] == "no_connection_test_for_adapter"
    assert run["evidence_kind"] == "none" and _states(env.w.registry, "plain_shop") == before
    assert env.svc.get_setup(OPERATOR, "plain_shop")["connection_test_available"] is False
    not_offered = env.svc.run_verification(OPERATOR, NORD, "checkout.submit", "read_only_test")
    assert not_offered["result"] == "blocked" and not_offered["reason_code"] == "capability_not_offered"
    assert len(env.store.recent_runs("development", "plain_shop")) == 1  # blocked attempts are still recorded


def test_nordstrom_is_blocked_without_approval_and_never_calls_out(env):  # BM-PROV-002
    before = _states(env.w.registry, NORD)
    r = env.svc.run_verification(OPERATOR, NORD, "catalog.search", "read_only_test")
    assert r["result"] == "blocked" and r["reason_code"] == "publisher_approval_required"
    env.svc.update_setup(OPERATOR, NORD, {"approval_evidence_ref": "impact-approval-fictional-0001",
                                          "credential_secret_ref": SECRET_REF})
    env.w.clock.advance(seconds=1)
    r = env.svc.run_verification(OPERATOR, NORD, "catalog.feed", "read_only_test")
    assert r["result"] == "blocked" and r["reason_code"] == "impact_api_client_not_built"
    link = env.svc.run_verification(OPERATOR, NORD, "checkout.handoff", "read_only_test")
    assert link["result"] == "passed" and link["evidence_kind"] == "link_validation"
    assert "cannot verify" in link["sanitized_summary"]
    assert _states(env.w.registry, NORD) == before  # link validation never moves a capability
    view = env.svc.get_setup(OPERATOR, NORD)
    assert _section(view, "tests")["test:checkout.handoff"]["state"] == "blocked"
    env.svc.update_setup(OPERATOR, NORD, {"access_level": "link_only"})
    with pytest.raises(SetupRefused) as e:
        env.svc.update_setup(OPERATOR, NORD, {"activate": "checkout.handoff"})
    assert e.value.code == "activation_evidence_not_verifying"
    with pytest.raises(SetupRefused) as e:
        env.svc.update_setup(OPERATOR, NORD, {"activate": "catalog.feed"})
    assert e.value.code == "activation_prerequisites_missing"


# ------------------------------------------------------------------ activation
def test_activation_needs_a_fresh_passing_test(env):
    with pytest.raises(SetupRefused) as e:
        env.svc.update_setup(OPERATOR, PROVIDER_ID, {"activate": "catalog.search"})
    assert e.value.code == "activation_test_required" and e.value.status == 409
    env.svc.run_verification(OPERATOR, PROVIDER_ID, "catalog.search", "read_only_test")
    env.w.clock.advance(hours=25)
    with pytest.raises(SetupRefused) as e:
        env.svc.update_setup(OPERATOR, PROVIDER_ID, {"activate": "catalog.search"})
    assert e.value.code == "activation_test_stale"
    env.svc.run_verification(OPERATOR, PROVIDER_ID, "catalog.search", "read_only_test")
    env.w.clock.advance(minutes=5)
    view = env.svc.update_setup(OPERATOR, PROVIDER_ID, {"activate": "catalog.search"})
    item = _section(view, "activation")["activate:catalog.search"]
    assert item["state"] == "done" and "sandbox" in item["detail"]
    status = env.w.registry.get(PROVIDER_ID).capability("catalog.search")
    assert status.state == "sandbox" and status.evidence_kind == "conformance_suite"
    stored = env.store.snapshot("development", PROVIDER_ID).items["activate:catalog.search"]
    assert stored.recorded_by == operator_ref(OPERATOR) and OPERATOR_MEMBER not in stored.recorded_by


def test_activation_refused_after_a_failed_latest_test_and_must_be_sent_alone(env):
    env.svc.run_verification(OPERATOR, PROVIDER_ID, "price.quote", "read_only_test")
    env.w.clock.advance(seconds=10)
    env.w.provider.arm(Behavior.STOCK_LOSS, source_variant_ref=PROBE_VARIANT)
    env.svc.run_verification(OPERATOR, PROVIDER_ID, "price.quote", "read_only_test")
    with pytest.raises(SetupRefused) as e:
        env.svc.update_setup(OPERATOR, PROVIDER_ID, {"activate": "price.quote"})
    assert e.value.code == "activation_test_required"
    with pytest.raises(InvalidRequest) as e:
        env.svc.update_setup(OPERATOR, NORD, {"activate": "checkout.handoff", "access_level": "link_only"})
    assert e.value.code == "activation_must_be_sent_alone"


def test_activation_of_an_unconfigured_capability_needs_every_prerequisite(env):
    env.scripted.next = ProbeResult("passed", "sandbox_operation", "fx:run:feed", "Read one bounded page.")
    r = env.svc.run_verification(OPERATOR, "fixture_shop", "catalog.feed", "read_only_test")
    assert r["result"] == "passed" and r["capability_state"]["state"] == "unconfigured"  # a pass is not activation
    with pytest.raises(SetupRefused) as e:
        env.svc.update_setup(OPERATOR, "fixture_shop", {"activate": "catalog.feed"})
    assert e.value.code == "activation_prerequisites_missing"
    env.svc.update_setup(OPERATOR, "fixture_shop", {"account_ref": "fictional-fixture-account",
                                                    "credential_secret_ref": SECRET_REF})
    env.svc.update_setup(OPERATOR, "fixture_shop", {"data_use": RIGHTS})
    assert env.w.registry.get("fixture_shop").capability("catalog.feed").state == "unconfigured"
    env.svc.update_setup(OPERATOR, "fixture_shop", {"activate": "catalog.feed"})
    status = env.w.registry.get("fixture_shop").capability("catalog.feed")
    assert status.state == "sandbox" and status.evidence_ref == "fx:run:feed"


# ------------------------------------------------------------ authority, input
def test_operator_role_required(env):
    member = member_session()
    for call in (lambda p: env.svc.get_setup(p, NORD),
                 lambda p: env.svc.update_setup(p, NORD, {"program_application_opened": True}),
                 lambda p: env.svc.run_verification(p, PROVIDER_ID, "catalog.search", "read_only_test"),
                 lambda p: env.svc.list_runs(p, PROVIDER_ID)):
        with pytest.raises(Forbidden):
            call(member)
        with pytest.raises(Forbidden):
            call(replace(OPERATOR, environment="production"))
    assert env.store.recent_runs("development", PROVIDER_ID) == []
    assert MEMBER not in operator_ref(OPERATOR) and OPERATOR_MEMBER not in operator_ref(OPERATOR)


def test_unknown_capability_and_mode_rejected(env):
    for cap in ("checkout.buy_now", "", None, "catalog.search "):
        with pytest.raises(InvalidRequest) as e:
            env.svc.run_verification(OPERATOR, PROVIDER_ID, cap, "read_only_test")
        assert e.value.code == "unknown_capability"
    with pytest.raises(InvalidRequest) as e:
        env.svc.run_verification(OPERATOR, PROVIDER_ID, "catalog.search", "ping")
    assert e.value.code == "unknown_mode"
    with pytest.raises(InvalidRequest) as e:
        env.svc.update_setup(OPERATOR, PROVIDER_ID, {"activate": "checkout.buy_now"})
    assert e.value.code == "unknown_capability"


# ------------------------------------------------------------ records, restart
def test_run_records_round_trip_with_time_environment_capability_and_evidence(env):
    env.svc.run_verification(OPERATOR, PROVIDER_ID, "catalog.search", "read_only_test")
    env.w.clock.advance(seconds=30)
    env.svc.run_verification(OPERATOR, NORD, "catalog.search", "read_only_test")
    runs = env.svc.list_runs(OPERATOR, PROVIDER_ID)["items"]
    assert [r["capability"] for r in runs] == ["catalog.search"]
    nord = env.store.recent_runs("development", NORD)[0]
    assert (nord.mode, nord.reason_code, nord.result) == ("read_only_test", "publisher_approval_required", "blocked")
    assert nord.ran_by == operator_ref(OPERATOR) and nord.ran_at == env.w.clock.now
    view = env.svc.get_setup(OPERATOR, PROVIDER_ID)
    assert {"run_id", "environment", "capability", "result", "evidence_kind", "evidence_ref",
            "sanitized_summary", "ran_at"} <= set(view["recent_runs"][0])
    assert "ran_by" not in view["recent_runs"][0]


def test_saved_setup_and_evidence_survive_a_new_process(env):
    env.svc.update_setup(OPERATOR, NORD, {"approval_evidence_ref": "impact-approval-fictional-0001",
                                          "credential_secret_ref": SECRET_REF})
    env.w.provider.arm(Behavior.STOCK_LOSS, source_variant_ref=PROBE_VARIANT)
    env.svc.run_verification(OPERATOR, PROVIDER_ID, "price.quote", "read_only_test")
    # A fresh process: new registry and adapters, same store.
    w2 = world()
    w2.registry.register(nordstrom.connection("development"))
    svc2 = ProviderSetupService(w2.registry, env.store, clock=w2.clock)
    view = svc2.get_setup(OPERATOR, NORD)
    assert view["credential_configured"] is True
    assert w2.registry.get(NORD).credential_ref == SECRET_REF
    assert svc2.run_verification(OPERATOR, NORD, "catalog.feed", "read_only_test")[
        "reason_code"] == "impact_api_client_not_built"
    svc2.get_setup(OPERATOR, PROVIDER_ID)
    assert w2.registry.get(PROVIDER_ID).capability("price.quote").state == "degraded"
