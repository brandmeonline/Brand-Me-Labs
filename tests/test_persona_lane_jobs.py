"""The lane's scheduled-jobs process against the Spanner emulator."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from google.cloud.spanner_v1 import param_types

from brandme_core.domains.persona.kernel import member_principal, run_read, run_txn, server_now, service_principal
from brandme_core.domains.rewards import ledger
from brandme_core.domains.rewards.benefits import BenefitService
from brandme_core.domains.rewards.service import RewardsService
from brandme_core.domains.social.decisions import DecisionService
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import INSTANCE, MEMBER_SCOPES, PROJECT, insert_member, spanner_db  # noqa: F401

ISSUER = "repairer:atelier-north"


def key():
    return "k-" + uuid.uuid4().hex


def jobs(db, **env):
    base = {**os.environ, "BRANDME_MODE": "development", "ENVIRONMENT": "development", "SPANNER_PROJECT_ID": PROJECT,
            "SPANNER_INSTANCE_ID": INSTANCE, "SPANNER_DATABASE_ID": db.database_id}
    return subprocess.run([sys.executable, "-m", "brandme_core.domains.persona.jobs", "--once"], env={**base, **env},
                          capture_output=True, text=True, timeout=120, cwd=Path(__file__).resolve().parents[1])


def move_past(db, table, member_id, id_col, id_value, col):
    def tx(t):
        t.execute_update(f"UPDATE {table} SET {col}=@e WHERE member_id=@m AND {id_col}=@i",
                         params={"e": server_now(t) - timedelta(seconds=1), "m": member_id, "i": id_value},
                         param_types={"e": param_types.TIMESTAMP, "m": param_types.STRING, "i": param_types.STRING})

    run_txn(db, tx)


def test_jobs_process_closes_due_decisions_and_releases_expired_reservations(spanner_db):  # noqa: F811
    db = spanner_db
    rel = RelationshipService(db)
    a, b = (member_principal(insert_member(db), MEMBER_SCOPES | {"rewards:write"}) for _ in range(2))
    rel.accept(b, rel.request(a, b.member_id)["relationship_id"])
    item = WardrobeService(db).create_items(a, {"source": "manual", "title": "Coat", "category": "outerwear"}, key())["items"][0]["id"]
    d = DecisionService(db).create(a, {"subject_type": "wardrobe_item", "subject_id": item, "prompt": "Keep?", "recipient_ids": [b.member_id],
                                       "duration_seconds": 300, "discussion_mode": "open"}, key())
    move_past(db, "Decisions", a.member_id, "decision_id", d["decision_id"], "closes_at")
    RewardsService(db, approved_repair_issuers=frozenset({ISSUER})).record_verified_repair(
        service_principal("repair-workflow"), a.member_id, repair_ref=str(uuid.uuid4()), issuer_ref=ISSUER)
    benefits = BenefitService(db)
    benefit = benefits.create_benefit(member_principal(insert_member(db), frozenset({"moderation:admin"})),
                                      {"kind": "room_finish", "title": "Finish", "description": "Cosmetic room finish", "cost_points": 50,
                                       "inventory_total": 3})
    r = benefits.reserve(a, benefit["benefit_id"], key())
    move_past(db, "BenefitReservations", a.member_id, "reservation_id", r["reservation_id"], "expires_at")

    run = jobs(db)
    assert run.returncode == 0, run.stdout + run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["status"] == "ran" and out["decisions"]["closed"] >= 1 and out["reservations"]["released"] >= 1
    assert out["media"] == "not_configured" and out["fulfillment"] == "not_configured"
    assert a.member_id not in run.stdout + run.stderr and d["decision_id"] not in run.stdout
    assert DecisionService(db).get(a, d["decision_id"])["state"] == "closed"
    assert run_read(db, lambda s: ledger.load_account(s, a.member_id)).available == 50  # points returned

    again = jobs(db)
    assert again.returncode == 0
    with db.snapshot() as s:
        closed_events = list(s.execute_sql("SELECT COUNT(*) FROM OutboxEvents WHERE event_type='decision.closed' AND aggregate_id=@d",
                                           params={"d": d["decision_id"]}, param_types={"d": param_types.STRING}))[0][0]
    assert closed_events == 1


def test_jobs_process_refuses_unsafe_configuration(spanner_db):  # noqa: F811
    for env in ({"ENVIRONMENT": "production", "BRANDME_MODE": "production"},  # emulator present in a strict mode
                {"BRANDME_MODE": "sandbox"},  # mode and environment disagree
                {"SPANNER_DATABASE_ID": ""}):
        run = jobs(spanner_db, **env)
        assert (run.returncode, run.stdout.strip()) == (2, '{"status":"startup_refused"}'), env
