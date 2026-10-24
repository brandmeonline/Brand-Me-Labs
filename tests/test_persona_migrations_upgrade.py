"""Upgrade path for databases that already applied main's migrations.

V002 must stay byte-identical to what those databases applied: the runner
rejects checksum drift on an applied file. This lane's schema arrives in its
reserved V003-V005 (the persona member link opens V003). Those numbers sit below
main's V006-V014, so a database that applied main first can take them only with
``--allow-out-of-order``, which the runner refuses in sandbox/production. That
ordering rule belongs to the foundation runner; the test pins today's behaviour
so a change on either side is noticed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from google.cloud.spanner_v1 import param_types

from brandme_core.domains.persona.kernel import FixedClock, member_principal
from brandme_core.domains.persona.service import PersonaService
from test_persona_harness import INSTANCE, MEMBER_SCOPES, PROJECT, count, emulator_up, insert_member, load_runner

LANE_VERSIONS = (3, 4, 5)


@pytest.fixture
def empty_db():
    if not emulator_up():
        pytest.skip("Spanner emulator not reachable; upgrade-path test NOT RUN")
    from google.cloud import spanner

    client = spanner.Client(project=PROJECT)
    instance = client.instance(INSTANCE)
    if not instance.exists():
        client.instance(INSTANCE, configuration_name=f"projects/{PROJECT}/instanceConfigs/emulator-config", node_count=1).create().result(120)
    db = instance.database("up" + uuid.uuid4().hex[:20])
    db.create().result(120)
    yield db
    db.drop()


def test_database_on_main_upgrades_without_checksum_drift(empty_db):
    runner = load_runner()
    every = runner.load_migrations()
    base = [m for m in every if m.version not in LANE_VERSIONS]
    quiet = {"applied_by": "upgrade-test", "log": lambda *_: None}
    assert runner.migrate_up(empty_db, base, **quiet) == [m.version for m in base]

    # Existing persona data written on main's V002 survives the upgrade.
    member = member_principal(insert_member(empty_db), MEMBER_SCOPES)
    PersonaService(empty_db, clock=FixedClock(datetime(2026, 10, 5, tzinfo=timezone.utc))).patch(
        member, '"0"', {"changes": [{"axis": "expression", "value": 60, "locked": False}], "client_revision": "u"})

    # Strict mode refuses the reserved gap (not checksum drift: V002 is unchanged).
    with pytest.raises(runner.MigrationError, match="out-of-order"):
        runner.migrate_up(empty_db, every, **quiet)
    assert runner.migrate_up(empty_db, every, allow_out_of_order=True, **quiet) == list(LANE_VERSIONS)
    assert runner.migrate_up(empty_db, every, **quiet) == []
    assert count(empty_db, "SELECT COUNT(*) FROM PersonaAxes WHERE member_id=@m AND declared_value IS NOT NULL", m=member.member_id) == 1

    # V003's member link: deleting the member removes the profile and its interleaved rows.
    empty_db.run_in_transaction(lambda t: t.execute_update(
        "DELETE FROM Members WHERE member_id=@m", params={"m": member.member_id}, param_types={"m": param_types.STRING}))
    assert count(empty_db, "SELECT COUNT(*) FROM PersonaProfiles WHERE member_id=@m", m=member.member_id) == 0
    assert count(empty_db, "SELECT COUNT(*) FROM PersonaAxes WHERE member_id=@m", m=member.member_id) == 0
