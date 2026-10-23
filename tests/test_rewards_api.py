"""Rewards HTTP surface, disputes, operator boundaries and W10 privacy (BM-LOY-005, BM-LOY-010 server half)."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brandme_core.domains import data_categories
from brandme_core.domains.persona.kernel import member_principal, run_read, run_txn, service_principal
from brandme_core.domains.persona.privacy_guard import guard_enforced
from brandme_core.domains.rewards import deletion, ledger
from brandme_core.domains.rewards.api import create_rewards_ops_router, create_rewards_router
from brandme_core.domains.rewards.benefits import BenefitService
from brandme_core.domains.rewards.service import RewardsService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

ISSUER = "repairer:atelier-north"
OPS = frozenset({"moderation:admin"})
ROLES = {"member": MEMBER_SCOPES | {"rewards:write"}, "ops": OPS, "reader": frozenset({"rewards:read"})}


def key():
    return "k-" + uuid.uuid4().hex


def resolve(request):
    mid, role = request.headers.get("x-test-member"), request.headers.get("x-test-role", "member")
    return member_principal(mid, ROLES[role]) if mid else None


@pytest.fixture
def svc(spanner_db):
    return RewardsService(spanner_db, approved_repair_issuers=frozenset({ISSUER})), BenefitService(spanner_db)


@pytest.fixture
def client(svc):
    app = FastAPI()
    app.include_router(create_rewards_router(*svc, resolve))
    app.include_router(create_rewards_ops_router(*svc, resolve))
    return TestClient(app)


def h(mid, role="member", **kw):
    return {"x-test-member": mid, "x-test-role": role, **kw}


def earn(svc, m, n=1):
    for _ in range(n):
        svc[0].record_verified_repair(service_principal("repair-workflow"), m, repair_ref=str(uuid.uuid4()), issuer_ref=ISSUER)


def test_member_routes_and_no_award_route(spanner_db, svc, client):
    """BM-LOY-005: there is no member path that awards or edits points."""
    m = insert_member(spanner_db)
    assert client.get("/rewards").status_code == 401
    earn(svc, m, 2)
    s = client.get("/rewards", headers=h(m))
    assert s.status_code == 200 and s.headers["cache-control"] == "private, no-store"
    body = s.json()
    assert body["account"]["available"] == 100 and len(body["badges"]) == 6 and body["next_milestone"]["rule_id"] == "meaningful_style_setup"
    # Only wired rules are advertised; referral/research ids are reserved, not shown (Q21).
    assert {r["rule_id"] for r in body["rules"]} == {"meaningful_style_setup", "first_owned_item", "friend_decision_response",
                                                     "styling_proposal_accepted", "catalog_correction_accepted", "verified_repair"}
    assert "not currency" in body["points_are"]
    for method, path, payload in (("post", "/rewards", {"available": 1_000_000}), ("patch", "/rewards", {"available": 1}),
                                  ("put", "/rewards/entries", {}), ("post", "/rewards/entries", {"points": 500}),
                                  ("post", f"/rewards/members/{m}/entries", {"points": 500})):
        assert getattr(client, method)(path, json=payload, headers=h(m)).status_code in (404, 405)
    # Members cannot reach operator routes, even for themselves.
    assert client.post("/ops/rewards/contributions", json={"member_ref": m, "kind": "catalog_correction", "contribution_ref": str(uuid.uuid4()),
                                                           "evidence_ref": "x"}, headers=h(m)).status_code == 403
    assert client.get(f"/ops/rewards/members/{m}/ledger", headers=h(m)).status_code == 403
    assert run_read(spanner_db, lambda s_: ledger.load_account(s_, m)).available == 100
    page = client.get("/rewards/entries?limit=1", headers=h(m)).json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    assert client.get(f"/rewards/entries?limit=1&cursor={page['next_cursor']}", headers=h(m)).json()["items"][0]["entry_id"] != page["items"][0]["entry_id"]


def test_reserve_over_http(spanner_db, svc, client):
    m, ops = insert_member(spanner_db), insert_member(spanner_db)
    earn(svc, m)
    b = client.post("/ops/benefits", json={"kind": "composition_template", "title": "Extra template", "description": "One more saved composition",
                                           "cost_points": 30, "inventory_total": 10}, headers=h(ops, "ops"))
    assert b.status_code == 201, b.text
    bid = b.json()["benefit_id"]
    assert client.post(f"/benefits/{bid}/reservations", headers=h(m)).status_code == 400  # Idempotency-Key required
    assert client.post(f"/benefits/{bid}/reservations", headers=h(m, "reader", **{"Idempotency-Key": key()})).status_code == 403
    k = key()
    r1 = client.post(f"/benefits/{bid}/reservations", headers=h(m, **{"Idempotency-Key": k}))
    assert r1.status_code == 201 and r1.json()["state"] == "pending" and r1.json()["account"]["available"] == 20
    assert client.post(f"/benefits/{bid}/reservations", headers=h(m, **{"Idempotency-Key": k})).json()["reservation_id"] == r1.json()["reservation_id"]
    r2 = client.post(f"/benefits/{bid}/reservations", headers=h(m, **{"Idempotency-Key": key()}))
    assert r2.status_code == 422 and r2.json()["code"] == "insufficient_points" and r2.json()["available"] == 20
    assert [x["state"] for x in client.get("/rewards/reservations", headers=h(m)).json()["items"]] == ["pending"]


def test_dispute_and_operator_correction(spanner_db, svc, client):
    m, ops = insert_member(spanner_db), insert_member(spanner_db)
    earn(svc, m)
    entry_id = client.get("/rewards/entries", headers=h(m)).json()["items"][0]["entry_id"]
    d = client.post("/rewards/disputes", json={"entry_id": entry_id, "category": "missing_reward", "message": "My second repair is missing"},
                    headers=h(m))
    assert d.status_code == 201
    did = d.json()["dispute_id"]
    queue = client.get("/ops/rewards/disputes", headers=h(ops, "ops")).json()["items"]
    assert did in [x["dispute_id"] for x in queue]
    # An operator cannot resolve their own dispute.
    own = client.post("/rewards/disputes", json={"category": "other", "message": "me"}, headers=h(ops)).json()["dispute_id"]
    assert client.post(f"/ops/rewards/disputes/{own}/resolve", json={"outcome": "correction", "signed_points": 500, "note": "x", "evidence_ref": "y"},
                       headers=h(ops, "ops")).status_code == 403
    res = client.post(f"/ops/rewards/disputes/{did}/resolve", json={"outcome": "correction", "signed_points": 50, "note": "Repair 2 confirmed by issuer",
                                                                  "evidence_ref": "issuer-mail-2"}, headers=h(ops, "ops"))
    assert res.status_code == 200 and res.json()["state"] == "resolved_correction" and res.json()["correction_entry_id"]
    again = client.post(f"/ops/rewards/disputes/{did}/resolve", json={"outcome": "correction", "signed_points": 50, "note": "dup",
                                                                    "evidence_ref": "dup"}, headers=h(ops, "ops"))
    assert again.json()["correction_entry_id"] == res.json()["correction_entry_id"]  # resolved once
    audit = client.get(f"/ops/rewards/members/{m}/ledger", headers=h(ops, "ops")).json()
    assert audit["consistency"]["ok"] and audit["consistency"]["account"]["available"] == 100
    assert [e["kind"] for e in audit["entries"]].count("correction") == 1
    mine = client.get("/rewards/disputes", headers=h(m)).json()["items"][0]
    assert mine["state"] == "resolved_correction" and mine["resolution_note"] == "Repair 2 confirmed by issuer"
    # Reversal over the ops route is linked and reasoned.
    rev = client.post(f"/ops/rewards/members/{m}/entries/{entry_id}/reverse", json={"reason": "issuer withdrew attestation", "evidence_ref": "w-1"},
                      headers=h(ops, "ops"))
    assert rev.status_code == 200 and rev.json()["status"] == "reversed"


def test_categories_export_and_delete(spanner_db, svc):
    m = insert_member(spanner_db)
    earn(svc, m)
    ops = member_principal(insert_member(spanner_db), OPS)
    bsvc = svc[1]
    b = bsvc.create_benefit(ops, {"kind": "room_finish", "title": "Linen walls", "description": "Finish", "cost_points": 20, "inventory_total": 2})
    bsvc.reserve(member_principal(m, ROLES["member"]), b["benefit_id"], key())
    svc[0].open_dispute(member_principal(m, ROLES["member"]), {"category": "other", "message": "question"})
    assert {c.name for c in data_categories() if c.domain == "rewards"} == set(deletion.CATEGORIES)
    exported = {c: run_read(spanner_db, lambda s, c=c: deletion.export_category(s, m, c)) for c in deletion.CATEGORIES}
    assert exported["rewards.ledger"][0]["account"]["available"] == 30 and len(exported["rewards.ledger"][0]["entries"]) == 2
    assert exported["rewards.badges"][0]["badge_id"] == "care_keeper"
    assert exported["rewards.redemptions"][0]["state"] == "pending" and exported["rewards.disputes"][0]["message"] == "question"
    for c in deletion.CATEGORIES:
        run_txn(spanner_db, lambda t, c=c: deletion.delete_category(t, m, c))
    for table in ("RewardAccounts", "RewardEntries", "RewardFacts", "BadgeAwards", "BenefitReservations", "RewardDisputes"):
        assert count(spanner_db, f"SELECT COUNT(*) FROM {table} WHERE member_id=@m", m=m) == 0
    # The pending reservation's inventory unit went back to the benefit.
    listed = {x["benefit_id"]: x for x in bsvc.list_benefits(member_principal(insert_member(spanner_db), ROLES["member"]))["items"]}
    assert listed[b["benefit_id"]]["remaining"] == 2


@pytest.mark.skipif(not guard_enforced(), reason="privacy lane not on this branch; handler registration check NOT RUN")
def test_privacy_lane_handler_registered():
    assert deletion.PRIVACY_HANDLER is not None
    assert {c.key for c in deletion.PRIVACY_HANDLER.categories()} == set(deletion.CATEGORIES)
