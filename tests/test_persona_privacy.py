"""Persona W10 registrations.

* Foundation data-category registry (always on this branch): every persona
  category exports and deletes through the registered callables; deleting
  evidence keeps the suppression rule so a queued job cannot re-ingest it.
* Privacy-lane ``DomainPrivacyHandler`` + ``assert_processing_allowed``
  (opus-midnight-rights W10): exercised only where that module and V009 are
  present (the W11 integration branch); otherwise skipped as NOT RUN.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains import data_categories
from brandme_core.domains.persona import deletion
from brandme_core.domains.persona.kernel import FixedClock, member_principal, run_txn
from brandme_core.domains.persona.privacy_guard import guard_enforced
from brandme_core.domains.persona.service import PersonaService
from test_persona_harness import MEMBER_SCOPES, insert_member, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
PERSONA_CATEGORIES = {"persona.declared", "persona.inferred", "persona.evidence", "persona.snapshots", "persona.feedback", "persona.card"}


@pytest.fixture
def svc(spanner_db):
    return PersonaService(spanner_db, clock=FixedClock(NOW))


@pytest.fixture
def member(spanner_db):
    return member_principal(insert_member(spanner_db), MEMBER_SCOPES)


def _seed(svc, member):
    svc.patch(member, '"0"', {"changes": [{"axis": "expression", "value": 72, "locked": True}], "client_revision": "s"})
    assert svc.ingest_evidence(member_id=member.member_id, source_type="saved_look", source_ref="look-a", axis_contributions={"color": 80}) == "accepted"
    svc.create_snapshot(member, "Before")


def test_foundation_registry_lists_every_persona_category():
    cats = {c.name: c for c in data_categories() if c.domain == "persona"}
    assert set(cats) == PERSONA_CATEGORIES
    for c in cats.values():
        assert c.export is not None and c.delete is not None and c.tables


def test_export_then_category_delete_through_registered_callables(svc, member, spanner_db):
    _seed(svc, member)
    cats = {c.name: c for c in data_categories() if c.domain == "persona"}
    exported = {k: list(c.export(spanner_db, member.member_id)) for k, c in cats.items()}
    axes = {a["axis"]: a for a in exported["persona.declared"][0]["axes"]}
    assert len(axes) == 12 and axes["expression"]["declared"] == 72 and axes["expression"]["locked"] is True
    assert any(a["axis"] == "color" and a["inferred"] == 80 for a in exported["persona.inferred"])
    assert exported["persona.evidence"][0]["source_ref"] == "look-a"
    assert exported["persona.snapshots"][0]["saved_name"] == "Before"

    cats["persona.evidence"].delete(spanner_db, member.member_id)
    after = svc.get(member)
    assert after["profile"]["inferred_axes"]["color"] is None
    assert after["profile"]["declared_axes"]["expression"] == 72  # other categories untouched
    assert svc.list_evidence(member) == []
    # The suppression rule outlives the deleted row: same observation is refused.
    assert svc.ingest_evidence(member_id=member.member_id, source_type="saved_look", source_ref="look-a", axis_contributions={"color": 80}) == "suppressed"

    cats["persona.declared"].delete(spanner_db, member.member_id)
    after = svc.get(member)
    assert after["profile"]["declared_axes"]["expression"] is None and after["profile"]["locked_axes"] == []
    # Processing switches are reset to off, so the deleted declarations cannot resurface through learning.
    declared = list(cats["persona.declared"].export(spanner_db, member.member_id))[0]
    assert (declared["learning_enabled"], declared["social_signals_enabled"]) == (False, False)
    cats["persona.snapshots"].delete(spanner_db, member.member_id)
    assert list(cats["persona.snapshots"].export(spanner_db, member.member_id)) == []


def test_account_delete_is_idempotent(svc, member, spanner_db):
    _seed(svc, member)
    first = run_txn(spanner_db, lambda t: deletion.delete_member(t, member.member_id))
    second = run_txn(spanner_db, lambda t: deletion.delete_member(t, member.member_id))
    assert first["deleted"]["evidence"] == 1 and second["deleted"] == {"evidence": 0, "snapshots": 0}


privacy_lane = pytest.mark.skipif(
    not guard_enforced(), reason="privacy lane (brandme_core.domains.privacy) not on this branch; integration check NOT RUN"
)


@privacy_lane
def test_privacy_handler_registered_with_declared_categories():
    from brandme_core.domains.privacy.deletion import registry

    keys = {c.key for c in registry.categories() if c.domain == "persona"}
    assert keys == PERSONA_CATEGORIES
    assert deletion.PRIVACY_HANDLER is not None


@privacy_lane
def test_processing_freeze_blocks_inference_write(svc, member, spanner_db):
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    _seed(svc, member)
    run_txn(spanner_db, lambda t: t.insert(
        "ProcessingFreezes",
        columns=("subject_ref", "category", "reason", "deletion_job_id", "created_at"),
        values=[(member.member_id, "*", "deletion", str(uuid.uuid4()), COMMIT_TIMESTAMP)],
    ))
    assert svc.ingest_evidence(member_id=member.member_id, source_type="saved_look", source_ref="late", axis_contributions={"color": 1}) == "processing_frozen"


@privacy_lane
def test_tombstone_newer_than_job_basis_blocks_write(svc, member, spanner_db):
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    _seed(svc, member)
    basis = datetime.now(timezone.utc) - timedelta(minutes=5)  # job read its inputs before the deletion
    run_txn(spanner_db, lambda t: t.insert(
        "DeletionTombstones",
        columns=("subject_ref", "category", "tombstone_id", "deletion_job_id", "record_keys", "created_at"),
        values=[(member.member_id, "persona.inferred", str(uuid.uuid4()), str(uuid.uuid4()), [], COMMIT_TIMESTAMP)],
    ))
    assert svc.ingest_evidence(
        member_id=member.member_id, source_type="saved_look", source_ref="stale", axis_contributions={"color": 1}, basis_time=basis
    ) == "processing_frozen"
