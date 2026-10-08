"""Migration ledger/runner against the Spanner emulator (W02 exit: empty and baseline → V001)."""
import re
import shutil

import pytest

from .conftest import REPO, requires_spanner

pytestmark = requires_spanner

V001_TABLES = {"Members", "MemberSettings", "MemberIdentities", "Sessions", "ConsentGrants", "OutboxEvents",
               "InboxReceipts", "IdempotencyRecords", "AuditEntries", "SchemaMigrations"}


def _tables(db):
    with db.snapshot() as s:
        return {r[0] for r in s.execute_sql("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ''")}


RESERVED = {1: "identity", 2: "persona", 3: "wardrobe", 4: "social", 5: "rewards", 6: "providers",
            7: "commerce", 8: "rights", 9: "privacy"}


@pytest.fixture
def v001_only(runner, tmp_path):
    """Foundation behaviour is tested against V001 alone; lanes add their reserved numbers independently."""
    d = tmp_path / "v001"
    d.mkdir()
    shutil.copy(REPO / "brandme-data/spanner/migrations/V001_identity.sql", d)
    return runner.load_migrations(d), d


def test_only_reserved_numbers_are_used(runner):
    for m in runner.load_migrations():
        assert m.version in RESERVED, f"V{m.version:03d} is not a reserved migration number"
        assert RESERVED[m.version] in m.name, f"V{m.version:03d} must be the {RESERVED[m.version]} migration"


def test_empty_to_v001_and_rerun_is_noop(runner, empty_database, v001_only):
    ms, _ = v001_only
    assert runner.migrate_up(empty_database, ms, log=lambda *_: None) == [1]
    assert V001_TABLES <= _tables(empty_database)
    assert runner.migrate_up(empty_database, ms, log=lambda *_: None) == []
    assert runner.assert_schema_supported(empty_database, 1) == 1


def test_legacy_baseline_schema_then_v001(runner, empty_database, v001_only):
    """The legacy schema.sql (as far as GoogleSQL accepts it) followed by V001."""
    src = (REPO / "brandme-data/spanner/schema.sql").read_text()
    accepted = 0
    for stmt in runner.split_statements(src):
        try:
            empty_database.update_ddl([stmt]).result(60)
            accepted += 1
        except Exception:
            pass  # baseline defects are recorded in docs/build/evidence/w00
    assert accepted >= 70
    assert {"Users", "Assets", "ConsentPolicies"} <= _tables(empty_database)
    assert runner.migrate_up(empty_database, v001_only[0], log=lambda *_: None) == [1]
    assert V001_TABLES <= _tables(empty_database)


def test_checksum_drift_is_refused(runner, empty_database, tmp_path):
    runner.migrate_up(empty_database, log=lambda *_: None)
    d = tmp_path / "m"
    shutil.copytree(REPO / "brandme-data/spanner/migrations", d)
    f = d / "V001_identity.sql"
    f.write_text(f.read_text() + "\n-- edited after apply\n")
    with pytest.raises(runner.MigrationError, match="checksum drift"):
        runner.migrate_up(empty_database, runner.load_migrations(d), log=lambda *_: None)


def test_out_of_order_and_incomplete_are_refused(runner, empty_database, v001_only):
    _, d = v001_only
    (d / "V003_late.sql").write_text("CREATE TABLE LateThree (id STRING(36) NOT NULL) PRIMARY KEY (id);\n")
    runner.migrate_up(empty_database, runner.load_migrations(d), log=lambda *_: None)
    (d / "V002_gap.sql").write_text("CREATE TABLE GapTwo (id STRING(36) NOT NULL) PRIMARY KEY (id);\n")
    with pytest.raises(runner.MigrationError, match="out-of-order"):
        runner.migrate_up(empty_database, runner.load_migrations(d), log=lambda *_: None)
    (d / "V002_gap.sql").unlink()
    (d / "V004_broken.sql").write_text("CREATE TABLE Ok4 (id STRING(36) NOT NULL) PRIMARY KEY (id);\nCREATE INDEX Bad ON Missing(x);\n")
    with pytest.raises(runner.MigrationError, match="V004_broken failed"):
        runner.migrate_up(empty_database, runner.load_migrations(d), log=lambda *_: None)
    with pytest.raises(runner.MigrationError, match="state 'applying'"):
        runner.migrate_up(empty_database, runner.load_migrations(d), log=lambda *_: None)
    with pytest.raises(runner.MigrationError, match="incomplete"):
        runner.assert_schema_supported(empty_database, 1)


def test_split_statements_ignores_comments_and_quoted_semicolons(runner):
    sql = "-- a; comment\nCREATE TABLE A (x STRING(1)) PRIMARY KEY (x);\nALTER TABLE A ADD CONSTRAINT c CHECK (x != ';');\n"
    assert len(runner.split_statements(sql)) == 2
    assert all(not re.search(r"^--", s) for s in runner.split_statements(sql))
