"""Upgrade path for databases that already applied main's migrations.

The runner rejects checksum drift on applied files and, outside development,
refuses migrations numbered below the highest applied one. So this lane's
schema must arrive as new, higher-numbered files: V002 stays exactly as
existing databases applied it, and V016..V019 add the member link and the
wardrobe, social and rewards tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from google.cloud.spanner_v1 import param_types

from brandme_core.domains.persona.kernel import FixedClock, member_principal
from brandme_core.domains.persona.service import PersonaService
from test_persona_harness import INSTANCE, MEMBER_SCOPES, PROJECT, count, emulator_up, insert_member, load_runner

LANE_VERSIONS = (16, 17, 18, 19)


@pytest.fixture
def empty_db():
    if not emulator_up():
        pytest.skip("Spanner emulator not reachable; upgrade-path test NOT RUN")
    from google.cloud import spanner

    instance = spanner.Client(project=PROJECT).instance(INSTANCE)
    if not instance.exists():
        spanner.Client(project=PROJECT).instance(
            INSTANCE, configuration_name=f"projects/{PROJECT}/instanceConfigs/emulator-config", node_count=1
        ).create().result(120)
    db = instance.database("up" + uuid.uuid4().hex[:20])
    db.create().result(120)
    yield db
    db.drop()


def test_lane_migrations_follow_every_other_applied_version():
    versions = [m.version for m in load_runner().load_migrations()]
    others = [v for v in versions if v not in LANE_VERSIONS]
    assert set(LANE_VERSIONS) <= set(versions)
    # If this fails, another lane merged a higher version first: renumber this lane's files above it.
    assert min(LANE_VERSIONS) > max(others)


def test_database_on_main_upgrades_without_drift_or_out_of_order(empty_db):
    runner = load_runner()
    every = runner.load_migrations()
    base = [m for m in every if m.version not in LANE_VERSIONS]
    assert runner.migrate_up(empty_db, base, applied_by="upgrade-test", log=lambda *_: None) == [m.version for m in base]

    # Existing persona data written on the old schema survives the upgrade.
    member = member_principal(insert_member(empty_db), MEMBER_SCOPES)
    PersonaService(empty_db, clock=FixedClock(datetime(2026, 10, 5, tzinfo=timezone.utc))).patch(
        member, '"0"', {"changes": [{"axis": "expression", "value": 60, "locked": False}], "client_revision": "u"})

    applied = runner.migrate_up(empty_db, every, applied_by="upgrade-test", log=lambda *_: None)  # strict: no out-of-order
    assert applied == list(LANE_VERSIONS)
    assert runner.migrate_up(empty_db, every, applied_by="upgrade-test", log=lambda *_: None) == []
    assert count(empty_db, "SELECT COUNT(*) FROM PersonaAxes WHERE member_id=@m AND declared_value IS NOT NULL", m=member.member_id) == 1

    # V016's link: deleting the member removes the profile and its interleaved rows.
    empty_db.run_in_transaction(lambda t: t.execute_update(
        "DELETE FROM Members WHERE member_id=@m", params={"m": member.member_id}, param_types={"m": param_types.STRING}))
    assert count(empty_db, "SELECT COUNT(*) FROM PersonaProfiles WHERE member_id=@m", m=member.member_id) == 0
    assert count(empty_db, "SELECT COUNT(*) FROM PersonaAxes WHERE member_id=@m", m=member.member_id) == 0
