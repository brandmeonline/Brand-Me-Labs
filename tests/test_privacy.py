"""
W10 My Data framework against the Spanner emulator (real GoogleSQL, V008+V009).

Covers: inventory, export receipt + forbidden-content guard, deletion
propagation to projections/caches, truthful receipt with exceptions,
re-auth requirement, tombstone reapplication after restore from an older
backup, and account deletion racing a queued inference job.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("SPANNER_EMULATOR_HOST", "localhost:9010")

spanner = pytest.importorskip("google.cloud.spanner")

from brandme_core.domains.privacy.deletion import (  # noqa: E402
    DataCategory, DeletionOutcome, ExportSection, OnDelete, PrivacyRegistry, PrivacyRegistryError, ProcessingFrozenError,
    Supplier,
)
from brandme_core.domains.privacy.privacy import (  # noqa: E402
    ForbiddenExportContent, MyDataService, ReauthRequired, RestoreNotServing,
)
from tests.fixtures.privacy.persona_fixture import FIXTURE_DDL, PersonaFixtureHandler, ProjectionStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = [ROOT / "brandme-data/spanner/migrations/V008_rights.sql", ROOT / "brandme-data/spanner/migrations/V009_privacy.sql"]


def _ddl(path: Path) -> list[str]:
    sql = re.sub(r"--[^\n]*", "", path.read_text())
    return [s.strip() for s in sql.split(";") if s.strip()]


def _emulator_up() -> bool:
    import socket
    host, port = os.environ["SPANNER_EMULATOR_HOST"].split(":")
    try:
        socket.create_connection((host, int(port)), timeout=1).close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _emulator_up(), reason="Spanner emulator not running on SPANNER_EMULATOR_HOST")


@pytest.fixture()
def database():
    client = spanner.Client(project="test-project")
    inst = client.instance("privacy-tests", configuration_name="projects/test-project/instanceConfigs/emulator-config", node_count=1)
    if not inst.exists():
        inst.create().result(60)
    ddl = [s for m in MIGRATIONS for s in _ddl(m)] + FIXTURE_DDL
    db = inst.database("p" + uuid.uuid4().hex[:20], ddl_statements=ddl)
    db.create().result(120)
    yield db
    db.drop()


class MemoryObjectStore:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key, data, content_type):
        self.objects[key] = data
        return f"mem://{key}"

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture()
def setup(database):
    reg = PrivacyRegistry()
    projections = ProjectionStore()
    persona = PersonaFixtureHandler(projections)
    reg.register(persona)
    svc = MyDataService(database, MemoryObjectStore(), reg)
    return svc, persona, projections, reg, database


def now():
    return datetime.now(timezone.utc)


def test_registry_rejects_undeclared_or_unjustified_categories():
    reg = PrivacyRegistry()

    class Bad:
        domain = "wardrobe"
        def categories(self):
            return [DataCategory("wardrobe.receipts", "wardrobe", "Receipts", Supplier.PROVIDER, ("member",), "7 years",
                                 "n/a", OnDelete.RETAIN_LEGAL)]
        def export(self, *a): ...
        def delete(self, *a): ...
        def purge_derived(self, *a): ...
        def reapply_tombstone(self, *a): ...

    with pytest.raises(PrivacyRegistryError, match="retention_basis"):
        reg.register(Bad())

    class WrongPrefix(Bad):
        def categories(self):
            return [DataCategory("social.x", "wardrobe", "x", Supplier.MEMBER, ("member",), "r", "e", OnDelete.ERASE)]

    with pytest.raises(PrivacyRegistryError, match="prefixed"):
        reg.register(WrongPrefix())


def test_inventory_describes_supplier_visibility_retention(setup):
    svc, *_ = setup
    inv = {c["key"]: c for c in svc.inventory()}
    assert inv["persona.inferred"]["supplied_by"] == "inferred"
    assert inv["persona.declared"]["retention"]
    assert inv["persona.declared"]["on_delete"] == "erase"


def test_export_requires_reauth_and_produces_receipt(setup):
    svc, persona, _, _, db = setup
    persona.declare(db, "m1", "warm_cold", 0.7)
    with pytest.raises(ReauthRequired):
        svc.export("m1", now() - timedelta(hours=1))
    out = svc.export("m1", now())
    assert out["package"]["categories"]["persona.declared"]["records"][0]["trait"] == "warm_cold"
    assert "private_state_backup" in out["package"]
    assert len(out["sha256"]) == 64
    with db.snapshot() as s:
        row = list(s.execute_sql("SELECT state, package_sha256 FROM ExportJobs"))[0]
    assert row[0] == "ready" and row[1] == out["sha256"]


def test_export_refuses_secret_material(setup):
    svc, persona, _, reg, db = setup

    class Leaky:
        domain = "wallet"
        def categories(self):
            return [DataCategory("wallet.keys", "wallet", "Keys", Supplier.MEMBER, ("member",), "r", "e", OnDelete.ERASE)]
        def export(self, snap, ctx, cat):
            return ExportSection(cat, [{"mnemonic": "abandon abandon …"}])
        def delete(self, *a): return DeletionOutcome("wallet.keys", 0)
        def purge_derived(self, *a): return DeletionOutcome("wallet.keys", 0)
        def reapply_tombstone(self, *a): return 0

    reg.register(Leaky())
    with pytest.raises(ForbiddenExportContent):
        svc.export("m1", now())


def test_deletion_propagates_to_projections_and_caches(setup):
    svc, persona, proj, _, db = setup
    persona.declare(db, "m2", "sport_couture", 0.2)
    persona.write_inference(db, "m2", "warm_cold", 0.9, basis_time=now())
    assert proj.read_profile("m2") is not None
    job = svc.request_deletion("m2", now())
    receipt = svc.run_deletion(job)
    assert persona.count(db, "m2") == 0
    assert proj.read_profile("m2") is None            # old projection/cache no longer leaks
    assert receipt["categories"]["persona.declared"]["status"] == "deleted"
    assert receipt["categories"]["persona.inferred"]["rows_affected"] == 1
    assert "expires_no_later_than" in receipt["backups"]
    with db.snapshot() as s:
        assert list(s.execute_sql("SELECT state FROM DeletionJobs"))[0][0] == "completed"


def test_receipt_reports_not_erasable_and_retained_truthfully(setup):
    svc, _, _, reg, _ = setup

    class Chain:
        domain = "rightsfixture"
        def categories(self):
            return [
                DataCategory("rightsfixture.commitments", "rightsfixture", "Public ownership commitments", Supplier.SYSTEM,
                             ("public",), "Permanent (public ledger)", "Cannot be edited", OnDelete.NOT_ERASABLE_PUBLIC_LEDGER, personal=False),
                DataCategory("rightsfixture.invoices", "rightsfixture", "Reprint invoices", Supplier.SYSTEM, ("member",),
                             "7 years", "Cannot be edited", OnDelete.RETAIN_LEGAL, retention_basis="Tax record retention (7 years)"),
            ]
        def export(self, snap, ctx, cat):
            return ExportSection(cat, [], references=[{"network": "preprod", "entitlement_id": "ab" * 32}])
        def delete(self, txn, ctx, cat): return DeletionOutcome(cat, 0)
        def purge_derived(self, ctx, cat): return DeletionOutcome(cat, 0)
        def reapply_tombstone(self, txn, t): return 0

    reg.register(Chain())
    receipt = svc.run_deletion(svc.request_deletion("m3", now()))
    assert receipt["categories"]["rightsfixture.commitments"]["status"] == "not_erasable"
    assert receipt["categories"]["rightsfixture.invoices"]["status"] == "retained"
    assert "Tax record" in receipt["categories"]["rightsfixture.invoices"]["reason"]


def test_tombstones_reapply_after_restore_from_older_backup(setup):
    svc, persona, proj, _, db = setup
    persona.declare(db, "m4", "warm_cold", 0.5)
    svc.run_deletion(svc.request_deletion("m4", now(), ["persona.declared"]))
    assert persona.count(db, "m4") == 0

    # Simulate restoring an older backup: the member's rows and projections come back.
    persona.declare(db, "m4", "warm_cold", 0.5)
    proj.docs["profiles/m4"] = {"stale": True}
    assert persona.count(db, "m4") == 1

    # Restored DB must not serve until tombstones are reapplied.
    with db.batch() as b:
        b.insert("RestoreRuns", ["restore_id", "backup_ref", "backup_taken_at", "state", "started_at"],
                 [["r-blocking", "gs://backups/older", now() - timedelta(days=2), "restoring", now()]])
    with pytest.raises(RestoreNotServing):
        svc.assert_serving()
    result = svc.reapply_tombstones_after_restore("gs://backups/older", now() - timedelta(days=2))
    assert result["tombstones_applied"] >= 1
    assert persona.count(db, "m4") == 0
    assert proj.read_profile("m4") is None
    with db.batch() as b:
        b.update("RestoreRuns", ["restore_id", "state"], [["r-blocking", "serving"]])
    svc.assert_serving()


def test_account_deletion_racing_queued_inference_cannot_recreate_data(setup):
    """
    Both commit orders of the race are exercised. (The emulator permits one
    read/write transaction at a time, so a truly overlapping interleaving is
    not reproducible here; on Spanner the guard's read of ProcessingFreezes
    inside the writer's transaction conflicts with the deletion request's
    write of the same row, and serializable isolation orders them into one of
    these two cases.)
    """
    svc, persona, proj, _, db = setup
    persona.declare(db, "m5", "warm_cold", 0.4)
    basis = now()  # queued inference job read the profile here

    # Order A: deletion request commits before the queued job's transaction.
    job = svc.request_deletion("m5", now())
    with pytest.raises(ProcessingFrozenError):
        persona.write_inference(db, "m5", "warm_cold", 0.99, basis_time=basis)
    svc.run_deletion(job)
    assert persona.count(db, "m5") == 0
    # Still refused after the deletion job completes (account freeze is permanent).
    with pytest.raises(ProcessingFrozenError):
        persona.write_inference(db, "m5", "warm_cold", 0.5, basis_time=now())
    assert proj.read_profile("m5") is None

    # Order B: the job commits first, then deletion is requested and run:
    # the inferred data it wrote is deleted with everything else.
    persona.declare(db, "m7", "warm_cold", 0.4)
    persona.write_inference(db, "m7", "warm_cold", 0.8, basis_time=now())
    svc.run_deletion(svc.request_deletion("m7", now()))
    assert persona.count(db, "m7") == 0
    assert proj.read_profile("m7") is None
    with pytest.raises(ProcessingFrozenError):
        persona.write_inference(db, "m7", "warm_cold", 0.9, basis_time=now())


def test_category_deletion_blocks_stale_jobs_but_allows_fresh_ones(setup):
    svc, persona, _, _, db = setup
    stale_basis = now()
    persona.write_inference(db, "m6", "warm_cold", 0.3, basis_time=stale_basis)
    svc.run_deletion(svc.request_deletion("m6", now(), ["persona.inferred"]))
    with pytest.raises(ProcessingFrozenError, match="after this job's basis time"):
        persona.write_inference(db, "m6", "warm_cold", 0.31, basis_time=stale_basis)
    # A new inference computed from data observed after the deletion is permitted.
    persona.write_inference(db, "m6", "warm_cold", 0.6, basis_time=now() + timedelta(seconds=1))
    assert persona.count(db, "m6") == 1
