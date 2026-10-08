"""Persona service against the Spanner emulator (real transactions, real
ABORTED/retry semantics). Covers BM-PER-002/003/005/006/007/008/009/010/011
and the outbox-retry evidence."""

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest
from google.api_core.exceptions import Aborted

from brandme_core.domains.persona import deletion
from brandme_core.domains.persona.kernel import (
    FixedClock,
    InvalidTransition,
    NotFound,
    Principal,
    ValidationFailed,
    VersionConflict,
    new_id,
    query,
    run_txn,
)
from brandme_core.domains.persona.model import AXIS_KEYS
from brandme_core.domains.persona.recommender import Candidate
from brandme_core.domains.persona.service import PersonaService
from test_persona_harness import spanner_db  # noqa: F401  (fixture)

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "docs/design/brandme/contracts/domain.schema.json").read_text())
FIXTURE = Path(__file__).parent / "fixtures" / "persona" / "catalog_candidates.json"
NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
SCOPES = frozenset({"profile:read", "profile:write"})


def validate(defname, obj):
    schema = {"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"], "$ref": f"#/$defs/{defname}"}
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(obj)


def candidates(_principal=None):
    out = []
    for c in json.loads(FIXTURE.read_text())["candidates"]:
        out.append(
            Candidate(
                c["product_id"], c["title"], c["brand"], c["category"], c["color_family"], c["axes"], tuple(c["materials"]),
                frozenset(c["occasions"]), c["price_minor"], c["currency"], c.get("available", True), sponsored=c.get("sponsored", False),
            )
        )
    return out


@pytest.fixture
def svc(spanner_db):
    return PersonaService(spanner_db, clock=FixedClock(NOW), candidate_source=candidates)


@pytest.fixture
def member():
    return Principal(member_id=new_id(), scopes=SCOPES)


def seed(svc, member, **axes):
    changes = [{"axis": k, "value": v, "locked": False} for k, v in axes.items()]
    return svc.patch(member, '"0"', {"changes": changes, "client_revision": "seed"})


def outbox_count(db, aggregate_id, event_type=None):
    sql = "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@a"
    params = {"a": aggregate_id}
    if event_type:
        sql += " AND event_type=@t"
        params["t"] = event_type
    with db.snapshot() as s:
        return list(s.execute_sql(sql, params=params, param_types={k: __import__("google.cloud.spanner_v1", fromlist=["param_types"]).param_types.STRING for k in params}))[0][0]


def test_get_before_any_save_is_unknown_and_writes_nothing(svc, member, spanner_db):
    dto = svc.get(member)
    assert dto["exists"] is False and dto["profile"]["version"] == "0"
    assert all(v is None for v in dto["profile"]["effective_axes"].values())
    assert all(a["state"] == "unanswered" and a["display_position"] == 50 for a in dto["axes"])
    validate("PersonaProfile", dto["profile"])
    assert outbox_count(spanner_db, member.member_id) == 0


def test_change_lock_persist_reload(svc, member, spanner_db):
    """BM-PER-002."""
    seed(svc, member, expression=60, color=55)
    out = svc.patch(member, '"1"', {"changes": [{"axis": "expression", "value": 78, "locked": True}], "client_revision": "draft-17"})
    assert out["profile"]["version"] == "2" and out["client_revision"] == "draft-17"
    validate("PersonaProfile", out["profile"])
    fresh = PersonaService(spanner_db, clock=FixedClock(NOW)).get(member)  # a different service instance = "reload"
    assert fresh["profile"]["declared_axes"]["expression"] == 78
    assert "expression" in fresh["profile"]["locked_axes"]
    assert fresh["profile"]["version"] == "2"
    assert outbox_count(spanner_db, member.member_id, "persona.updated") == 2


def test_two_devices_same_version_one_wins_with_merge_guidance(svc, member):
    """BM-PER-005."""
    seed(svc, member, expression=60, color=55)
    svc.patch(member, '"1"', {"changes": [{"axis": "expression", "value": 70, "locked": True}], "client_revision": "phone"})
    with pytest.raises(VersionConflict) as same_axis:
        svc.patch(member, '"1"', {"changes": [{"axis": "expression", "value": 20, "locked": True}], "client_revision": "laptop"})
    assert same_axis.value.extra == {
        "current_version": "2",
        "mergeable": False,
        "conflicting_axes": ["expression"],
        "guidance": "reload",
    }
    with pytest.raises(VersionConflict) as other_axis:
        svc.patch(member, '"1"', {"changes": [{"axis": "color", "value": 80, "locked": False}], "client_revision": "laptop"})
    assert other_axis.value.extra["mergeable"] is True
    assert svc.get(member)["profile"]["declared_axes"]["expression"] == 70  # no silent last-write-wins


def test_concurrent_same_version_patches_exactly_one_commits(svc, member):
    seed(svc, member, expression=50)
    results, errors = [], []

    def go(v):
        try:
            results.append(svc.patch(member, '"1"', {"changes": [{"axis": "expression", "value": v, "locked": True}], "client_revision": str(v)}))
        except VersionConflict as e:
            errors.append(e)

    threads = [threading.Thread(target=go, args=(v,)) for v in (11, 22, 33, 44, 55)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(results) == 1 and len(errors) == 4
    final = svc.get(member)["profile"]
    assert final["version"] == "2"
    assert final["declared_axes"]["expression"] == results[0]["profile"]["declared_axes"]["expression"]


def test_lock_races_inference_and_lock_wins(svc, member):
    """BM-PER-003."""
    seed(svc, member, expression=60)
    barrier = threading.Barrier(2)
    dispositions = []

    def lock():
        barrier.wait()
        for _ in range(10):
            try:
                cur = svc.get(member)["profile"]["version"]
                svc.patch(member, f'"{cur}"', {"changes": [{"axis": "expression", "value": 78, "locked": True}], "client_revision": "lock"})
                return
            except VersionConflict:
                continue
        raise AssertionError("lock never committed")

    def infer():
        barrier.wait()
        for i in range(5):
            dispositions.append(
                svc.ingest_evidence(member_id=member.member_id, source_type="saved_look", source_ref=f"look-{i}", axis_contributions={"expression": 10})
            )

    ts = [threading.Thread(target=lock), threading.Thread(target=infer)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert dispositions == ["accepted"] * 5
    dto = svc.get(member)
    exp = next(a for a in dto["axes"] if a["axis"] == "expression")
    assert (exp["effective"], exp["effective_source"], exp["locked"]) == (78, "declared_locked", True)
    assert exp["inferred"] == 10 and exp["inferred_evidence_count"] == 5  # inference remains inspectable
    assert len(svc.list_evidence(member)) == 5


def test_suppression_changes_recommendations_and_blocks_reuse(svc, member, spanner_db):
    """BM-PER-006: deleting evidence changes recommendations and prevents immediate reuse."""
    svc.patch(member, '"0"', {"changes": [], "client_revision": "init"})
    before = svc.recommendations(member)
    assert before["basis"] == "neutral_start"
    assert svc.ingest_evidence(
        member_id=member.member_id, source_type="saved_look", source_ref="look-evening",
        axis_contributions={"sport_couture": 90, "expression": 85, "structure": 90, "finish": 80, "color": 75},
    ) == "accepted"
    learned = svc.recommendations(member)
    assert learned["basis"] == "learned_and_declared"
    assert learned["items"][0]["title"] == "Evening Fluid Dress"
    [ev] = svc.list_evidence(member)
    out = svc.suppress_evidence(member, ev["evidence_id"])
    assert all(v is None for v in out["profile"]["inferred_axes"].values())
    after = svc.recommendations(member)
    assert after["basis"] == "neutral_start" and after != learned
    # Re-ingesting the same observation is refused (suppression rule, not a deleted UI row)
    assert svc.ingest_evidence(
        member_id=member.member_id, source_type="saved_look", source_ref="look-evening", axis_contributions={"expression": 85}
    ) == "suppressed"
    assert svc.list_evidence(member)[0]["suppression_state"] == "suppressed"
    assert svc.list_evidence(member)[0]["axis_contributions"] == {}
    assert outbox_count(spanner_db, member.member_id, "persona.evidence.suppressed") == 1


def test_learning_disabled_blocks_new_inference(svc, member):
    """BM-PER-007."""
    svc.patch(member, '"0"', {"changes": [], "learning_enabled": False, "client_revision": "off"})
    assert svc.ingest_evidence(member_id=member.member_id, source_type="saved_product", source_ref="p1", axis_contributions={"color": 90}) == "learning_disabled"
    assert svc.list_evidence(member) == []
    assert svc.get(member)["profile"]["inferred_axes"]["color"] is None


def test_do_not_infer_axis_drops_contribution(svc, member):
    svc.patch(member, '"0"', {"changes": [], "axis_settings": {"color": {"inference_allowed": False}}, "client_revision": "x"})
    assert svc.ingest_evidence(member_id=member.member_id, source_type="saved_look", source_ref="l", axis_contributions={"color": 90, "detail": 20}) == "accepted"
    [ev] = svc.list_evidence(member)
    assert ev["axis_contributions"] == {"detail": 20}
    assert svc.get(member)["profile"]["inferred_axes"]["color"] is None


def test_reset_inference_only_keeps_declarations(svc, member):
    """BM-PER-008."""
    seed(svc, member, expression=72)
    svc.ingest_evidence(member_id=member.member_id, source_type="saved_look", source_ref="a", axis_contributions={"color": 90})
    out = svc.reset(member, '"2"', "inference", True)
    assert out["profile"]["declared_axes"]["expression"] == 72
    assert out["profile"]["inferred_axes"]["color"] is None
    assert svc.ingest_evidence(member_id=member.member_id, source_type="saved_look", source_ref="a", axis_contributions={"color": 90}) == "suppressed"
    with pytest.raises(ValidationFailed):
        svc.reset(member, '"3"', "inference", False)
    with pytest.raises(ValidationFailed):
        svc.reset(member, '"3"', "everything", True)


def test_snapshot_inspect_and_restore_as_new_version(svc, member, spanner_db):
    """BM-PER-009."""
    seed(svc, member, expression=72, color=40)
    snap = svc.create_snapshot(member, "Autumn me")
    svc.patch(member, '"1"', {"changes": [{"axis": "expression", "value": 20, "locked": True}], "client_revision": "c"})
    diff = svc.snapshot_diff(member, snap["snapshot_id"])
    assert diff["changes"] == [{"axis": "expression", "current": 20, "snapshot": 72, "current_locked": True, "snapshot_locked": False}]
    restored = svc.restore_snapshot(member, '"2"', snap["snapshot_id"])
    assert restored["profile"]["version"] == "3"
    assert restored["profile"]["declared_axes"]["expression"] == 72
    assert outbox_count(spanner_db, member.member_id, "persona.snapshot.saved") == 1
    with pytest.raises(NotFound):
        svc.restore_snapshot(Principal(new_id(), SCOPES), '"0"', snap["snapshot_id"])  # another member cannot see it


def test_budget_and_exclusions_flow_through_to_recommendations(svc, member):
    """BM-PER-010 through the persisted profile."""
    seed(svc, member, expression=72, sport_couture=65)
    svc.patch(
        member,
        '"1"',
        {"changes": [], "client_revision": "c", "constraints": {"budget_ceiling_minor": "12000", "budget_currency": "USD", "excluded_materials": ["wool"]}},
    )
    rec = svc.recommendations(member)
    by_id = {c.product_id: c for c in candidates()}
    assert rec["items"]
    for item in rec["items"]:
        c = by_id[item["product_id"]]
        assert c.price_minor <= 12000 and c.currency == "USD" and "wool" not in c.materials
        assert any(r["text"] == "Within your $120 limit" for r in item["reasons"])
    assert rec["exclusions_honored"]["budget_ceiling_minor"] == "12000"


def test_not_me_feedback_hides_product_and_is_idempotent(svc, member):
    seed(svc, member, expression=72)
    dress = "9572fdc7-31e0-5b80-be82-147ef4a5e69c"
    a = svc.record_feedback(member, dress, "dress", "not_me", "k1")
    b = svc.record_feedback(member, dress, "dress", "not_me", "k1")
    assert a == b
    assert dress not in {i["product_id"] for i in svc.recommendations(member)["items"]}


@pytest.mark.parametrize(
    "body",
    [
        {"changes": [], "client_revision": "x", "reward_points": 1000},
        {"changes": [], "client_revision": "x", "owner_id": "someone"},
        {"changes": [{"axis": "expression", "value": 50, "locked": False, "points": 9}], "client_revision": "x"},
        {"changes": [], "client_revision": "x", "constraints": {"lifetime_earned": "999"}},
        {"changes": [{"axis": "expression", "value": 50, "locked": False}, {"axis": "expression", "value": 51, "locked": False}], "client_revision": "x"},
        {"changes": [{"axis": "expression", "value": 72.5, "locked": False}], "client_revision": "x"},
        {"changes": [{"axis": "charisma", "value": 50, "locked": False}], "client_revision": "x"},
        {"changes": [{"axis": "expression", "value": None, "locked": True}], "client_revision": "x"},
    ],
)
def test_patch_allowlist_rejects_factual_or_invalid_fields(svc, member, body):
    """BM-PER-011 + duplicate-axis/finite/vocabulary invariants."""
    with pytest.raises(ValidationFailed):
        svc.patch(member, '"0"', body)
    assert svc.get(member)["exists"] is False


def test_preview_is_read_only(svc, member, spanner_db):
    seed(svc, member, expression=50)
    n = outbox_count(spanner_db, member.member_id)
    pv = svc.preview(member, {"changes": [{"axis": "expression", "value": 90, "locked": True}], "client_revision": "rev-9"})
    assert pv["client_revision"] == "rev-9" and pv["persisted"] is False
    assert pv["effective_axes"]["expression"] == 90
    assert svc.get(member)["profile"]["declared_axes"]["expression"] == 50
    assert svc.get(member)["profile"]["version"] == "1"
    assert outbox_count(spanner_db, member.member_id) == n


def test_context_override_takes_precedence_then_expires(svc, member):
    seed(svc, member, setting=20)
    svc.patch(member, '"1"', {"changes": [{"axis": "setting", "value": 20, "locked": True}], "client_revision": "l"})
    out = svc.add_context_override(member, '"2"', "Hiking trip", {"setting": 90}, NOW - timedelta(hours=1), NOW + timedelta(days=3))
    s = next(a for a in out["axes"] if a["axis"] == "setting")
    assert (s["effective"], s["effective_source"]) == (90, "context_override")
    svc.clock.set(NOW + timedelta(days=4))
    s2 = next(a for a in svc.get(member)["axes"] if a["axis"] == "setting")
    assert (s2["effective"], s2["effective_source"]) == (20, "declared_locked")


def test_adaptation_requires_first_confirmation_and_is_bounded(svc, member):
    seed(svc, member, color=40)
    svc.patch(member, '"1"', {"changes": [], "axis_settings": {"color": {"adapt_enabled": True}}, "client_revision": "adapt"})
    svc.ingest_evidence(member_id=member.member_id, source_type="saved_look", source_ref="c", axis_contributions={"color": 90})
    assert svc.run_weekly_adaptation(member.member_id) == []  # first step needs explicit acceptance
    [prop] = svc.get(member)["adaptation_proposals"]
    assert (prop["current"], prop["proposed"], prop["requires_confirmation"]) == (40, 45, True)
    v = svc.get(member)["profile"]["version"]
    out = svc.accept_adaptation(member, f'"{v}"', "color")
    assert out["profile"]["declared_axes"]["color"] == 45
    assert svc.run_weekly_adaptation(member.member_id) == []  # within 7 days
    svc.clock.set(NOW + timedelta(days=7))
    assert svc.run_weekly_adaptation(member.member_id) == ["color"]
    assert svc.get(member)["profile"]["declared_axes"]["color"] == 50


class AbortOnceDB:
    """Wraps a Database so the first attempt of each transaction raises ABORTED
    *after* the domain callback has buffered all its mutations (incl. outbox)."""

    def __init__(self, db):
        self._db = db
        self.attempts = 0

    def __getattr__(self, name):
        return getattr(self._db, name)

    def run_in_transaction(self, fn, *a, **kw):
        state = {"n": 0}

        def wrapped(txn):
            state["n"] += 1
            self.attempts += 1
            out = fn(txn)
            if state["n"] == 1:
                raise Aborted("injected abort after buffering mutations", errors=["injected"])
            return out

        return self._db.run_in_transaction(wrapped, *a, **kw)


def test_transaction_retry_does_not_duplicate_outbox(spanner_db, member):
    flaky = AbortOnceDB(spanner_db)
    svc = PersonaService(flaky, clock=FixedClock(NOW))
    svc.patch(member, '"0"', {"changes": [{"axis": "expression", "value": 60, "locked": True}], "client_revision": "r"})
    svc.ingest_evidence(member_id=member.member_id, source_type="saved_look", source_ref="z", axis_contributions={"color": 30})
    assert flaky.attempts == 4  # each command really ran twice
    assert outbox_count(spanner_db, member.member_id) == 2
    assert len(svc.list_evidence(member)) == 1
    assert svc.get(member)["profile"]["version"] == "2"


def test_deletion_tombstone_blocks_racing_inference(svc, member, spanner_db):
    seed(svc, member, expression=60)
    exported = None
    with spanner_db.snapshot(multi_use=True) as s:
        exported = deletion.export_member(s, member.member_id)
    assert exported["profile"]["version"] == "1" and len(exported["axes"]) == 12
    receipt = run_txn(spanner_db, lambda t: deletion.delete_member(t, member.member_id))
    assert receipt["tombstoned"] is True
    assert svc.ingest_evidence(member_id=member.member_id, source_type="saved_look", source_ref="late", axis_contributions={"color": 1}) == "tombstoned"
    with pytest.raises(NotFound):
        svc.get(member)
    with pytest.raises(NotFound):
        svc.patch(member, '"0"', {"changes": [], "client_revision": "zombie"})
    with spanner_db.snapshot() as s:
        assert query(s, "SELECT COUNT(*) FROM PersonaAxes WHERE member_id=@m", {"m": member.member_id}, {"m": __import__("google.cloud.spanner_v1", fromlist=["param_types"]).param_types.STRING})[0][0] == 0


def test_missing_scope_is_rejected(svc):
    ro = Principal(new_id(), frozenset({"profile:read"}))
    from brandme_core.domains.persona.kernel import Forbidden

    with pytest.raises(Forbidden):
        svc.patch(ro, '"0"', {"changes": [], "client_revision": "x"})
