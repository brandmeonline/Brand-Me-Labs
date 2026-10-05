"""
W09 rights domain (application side) against the Spanner emulator.
"""

from __future__ import annotations

import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("SPANNER_EMULATOR_HOST", "localhost:9010")
spanner = pytest.importorskip("google.cloud.spanner")

from brandme_core.domains.privacy.deletion import PrivacyRegistry  # noqa: E402
from brandme_core.domains.privacy.privacy import MyDataService  # noqa: E402
from brandme_core.domains.rights.passport import read_claims  # noqa: E402
from brandme_core.domains.rights.privacy_handler import RightsPrivacyHandler  # noqa: E402
from brandme_core.domains.rights.projection import FinalizedObservation, ProjectionRejected, apply_observation  # noqa: E402
from brandme_core.domains.rights.reprint import IllegalReprintTransition, ReprintService, blinded_job_commitment  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = [ROOT / "brandme-data/spanner/migrations/V008_rights.sql", ROOT / "brandme-data/spanner/migrations/V009_privacy.sql"]


def _emulator_up() -> bool:
    import socket
    host, port = os.environ["SPANNER_EMULATOR_HOST"].split(":")
    try:
        socket.create_connection((host, int(port)), timeout=1).close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _emulator_up(), reason="Spanner emulator not running")


@pytest.fixture()
def db():
    client = spanner.Client(project="test-project")
    inst = client.instance("rights-tests", configuration_name="projects/test-project/instanceConfigs/emulator-config", node_count=1)
    if not inst.exists():
        inst.create().result(60)
    ddl = []
    for m in MIGRATIONS:
        sql = re.sub(r"--[^\n]*", "", m.read_text())
        ddl += [s.strip() for s in sql.split(";") if s.strip()]
    d = inst.database("r" + uuid.uuid4().hex[:20], ddl_statements=ddl)
    d.create().result(120)
    yield d
    d.drop()


def now():
    return datetime.now(timezone.utc)


def _job(svc: ReprintService, qty=2):
    jid = svc.create(network="preprod", allowance_id="aa" * 32, entitlement_id="ee" * 32, manufacturer_id="mm" * 32,
                     member_subject_ref="member-1", quantity=qty, job_commitment=blinded_job_commitment("j", secrets.token_bytes(32)))
    for s in ("quoted", "approved", "reserved", "rights_consuming"):
        svc.transition(jid, s)
    return jid


def test_reprint_cannot_be_consumed_without_finalized_chain_evidence(db):
    svc = ReprintService(db)
    jid = _job(svc)
    with pytest.raises(IllegalReprintTransition, match="not finalized"):
        svc.record_rights_consumed(jid, nullifier="nf", operation_id="op", operation_state="Observed")
    # A failed/unsubmitted proof returns the job to reserved — never consumed.
    svc.transition(jid, "reserved")
    assert svc.get(jid)["state"] == "reserved"


def test_duplicate_manufacturer_callbacks_apply_exactly_once(db):
    svc = ReprintService(db)
    jid = _job(svc, qty=2)
    svc.record_rights_consumed(jid, nullifier="nf1", operation_id="op1", operation_state="Finalized")
    mfr = "mm" * 32
    assert svc.apply_callback(manufacturer_id=mfr, callback_id="cb-accept", job_id=jid, kind="accepted").outcome == "applied"
    r1 = svc.apply_callback(manufacturer_id=mfr, callback_id="cb-u0", job_id=jid, kind="unit_produced", unit_index=0)
    assert (r1.outcome, r1.units_attested) == ("applied", 1)
    # The same delivery five more times.
    for _ in range(5):
        d = svc.apply_callback(manufacturer_id=mfr, callback_id="cb-u0", job_id=jid, kind="unit_produced", unit_index=0)
        assert d.outcome == "duplicate" and d.units_attested == 1
    # A different callback id replaying unit 0 is rejected (out of order), not double-counted.
    r = svc.apply_callback(manufacturer_id=mfr, callback_id="cb-u0-again", job_id=jid, kind="unit_produced", unit_index=0)
    assert r.outcome == "rejected" and r.units_attested == 1
    r2 = svc.apply_callback(manufacturer_id=mfr, callback_id="cb-u1", job_id=jid, kind="unit_produced", unit_index=1)
    assert (r2.state, r2.units_attested) == ("quality_review", 2)
    r3 = svc.apply_callback(manufacturer_id=mfr, callback_id="cb-u2", job_id=jid, kind="unit_produced", unit_index=2)
    assert r3.outcome == "rejected"
    assert svc.get(jid)["units_attested"] == 2
    with db.snapshot() as s:
        n = list(s.execute_sql("SELECT COUNT(*) FROM ManufacturerCallbacks"))[0][0]
    assert n == 5  # accept, u0, u0-again(rejected), u1, u2(rejected): duplicates of cb-u0 recorded once


def test_callback_from_unassigned_manufacturer_rejected(db):
    svc = ReprintService(db)
    jid = _job(svc)
    svc.record_rights_consumed(jid, nullifier="nf", operation_id="op", operation_state="Finalized")
    r = svc.apply_callback(manufacturer_id="zz" * 32, callback_id="x", job_id=jid, kind="accepted")
    assert r.outcome == "rejected" and svc.get(jid)["state"] == "rights_consumed"


def test_illegal_transitions_rejected(db):
    svc = ReprintService(db)
    jid = _job(svc)
    with pytest.raises(IllegalReprintTransition):
        svc.transition(jid, "delivered")


def _obs(**kw):
    base = dict(network="preprod", contract_address="cc" * 32, operation_state="Finalized", tx_id="tx1", block_height=10,
                block_hash="bh10", finalized_at=now(), entitlement_id="ee" * 32, issuer_id="ii" * 32, epoch=1, status="active",
                transferable=True, reprintable=False)
    base.update(kw)
    return FinalizedObservation(**base)


def test_projection_accepts_only_finalized_evidence_and_is_monotonic(db):
    with pytest.raises(ProjectionRejected):
        apply_observation(db, _obs(operation_state="Observed"))
    with pytest.raises(ProjectionRejected):
        apply_observation(db, _obs(network="mainnet"))
    assert apply_observation(db, _obs(), controller_subject_ref="alice") == "inserted"
    assert apply_observation(db, _obs()) == "unchanged"                       # idempotent replay
    assert apply_observation(db, _obs(tx_id="tx2", block_height=20, block_hash="bh20", epoch=2)) == "advanced"
    with db.snapshot() as s:
        row = list(s.execute_sql("SELECT epoch, controller_subject_ref FROM RightsEntitlements"))[0]
    assert row[0] == 2 and row[1] is None                                     # control moved: old member link dropped
    assert apply_observation(db, _obs(tx_id="tx0", block_height=5, block_hash="bh5", epoch=1)) == "unchanged"  # stale cannot roll back
    apply_observation(db, _obs(tx_id="tx3", block_height=30, block_hash="bh30", epoch=2, status="revoked"))
    with pytest.raises(ProjectionRejected):
        apply_observation(db, _obs(tx_id="tx4", block_height=40, block_hash="bh40", epoch=2, status="active"))


def test_passport_claims_are_separate_and_visibility_filtered(db):
    t = now()
    rows = [
        ["a1", "c1", "product", "product_identified", "issuer_record", "Brand X catalog", "sandbox", None, None, "public", None, t, None, None],
        ["a1", "c2", "ownership", "entitlement_controlled", "midnight_control_proof", "brandme_rights", "sandbox", "preprod", "tx:abc", "owner", None, t, None, None],
        ["a1", "c3", "provenance", "tag_verified", "secure_nfc", "issuer NFC verifier", "sandbox", None, None, "public", None, t - timedelta(days=2), t - timedelta(days=1), None],
        ["a1", "c4", "social", "ownership_claim_reviewed", "member_entered", "member", "sandbox", None, None, "private", None, t, None, None],
    ]
    with db.batch() as b:
        b.insert("PassportClaims", ["asset_id", "claim_id", "facet", "claim_type", "assurance", "source", "environment", "network",
                                    "evidence_ref", "visibility", "value_json", "observed_at", "expires_at", "revoked_at"], rows)
    pub = read_claims(db, "a1", "public")
    assert {s["statement"] for s in pub["statements"]} == {"product_identified", "tag_verified"}
    assert next(s for s in pub["statements"] if s["statement"] == "tag_verified")["state"] == "expired"
    own = read_claims(db, "a1", "owner")
    ctl = next(s for s in own["statements"] if s["statement"] == "entitlement_controlled")
    assert ctl["test_network"] is True and "physical possession" in ctl["what_this_means"]
    assert not any(s["statement"] == "ownership_claim_reviewed" for s in own["statements"])
    assert len(read_claims(db, "a1", "supplier")["statements"]) == 4


class _Store:
    def put(self, key, data, content_type):
        return f"mem://{key}"

    def delete(self, key):
        pass


def test_rights_deletion_unlinks_member_and_reports_public_commitments(db):
    apply_observation(db, _obs(), controller_subject_ref="bob")
    svc = ReprintService(db)
    jid = svc.create(network="preprod", allowance_id="aa" * 32, entitlement_id="ee" * 32, manufacturer_id="mm" * 32,
                     member_subject_ref="bob", quantity=1, job_commitment="cc" * 32)
    reg = PrivacyRegistry()
    reg.register(RightsPrivacyHandler())
    my = MyDataService(db, _Store(), reg)
    export = my.export("bob", now())
    assert export["package"]["public_chain_references"][0]["entitlement_id"] == "ee" * 32
    receipt = my.run_deletion(my.request_deletion("bob", now()))
    assert receipt["categories"]["rights.chain_commitments"]["status"] == "not_erasable"
    assert receipt["categories"]["rights.reprint_jobs"]["status"] == "retained"
    assert receipt["categories"]["rights.control_links"]["status"] == "deleted"
    with db.snapshot(multi_use=True) as s:
        assert list(s.execute_sql("SELECT controller_subject_ref FROM RightsEntitlements"))[0][0] is None
        assert list(s.execute_sql("SELECT member_subject_ref FROM ReprintJobs WHERE job_id = @j",
                                  params={"j": jid}, param_types={"j": spanner.param_types.STRING}))[0][0] == "deleted-member"
