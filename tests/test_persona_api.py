"""HTTP contract of the (unmounted) persona router, mounted here in a test app
with a test-only principal resolver. Covers problem+json, If-Match (428/409),
Idempotency-Key, cursor pagination and guest migration (BM-ONB-004)."""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brandme_core.domains.persona.api import create_persona_router
from brandme_core.domains.persona.kernel import FixedClock, member_principal
from brandme_core.domains.persona.onboarding import GuestMigrationService
from brandme_core.domains.persona.recommender import Candidate
from brandme_core.domains.persona.service import PersonaService
from test_persona_harness import MEMBER_SCOPES, insert_member, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
FIXTURE = Path(__file__).parent / "fixtures" / "persona" / "catalog_candidates.json"


def candidates(_p=None):
    return [
        Candidate(c["product_id"], c["title"], c["brand"], c["category"], c["color_family"], c["axes"], tuple(c["materials"]),
                  frozenset(c["occasions"]), c["price_minor"], c["currency"], c.get("available", True), sponsored=c.get("sponsored", False))
        for c in json.loads(FIXTURE.read_text())["candidates"]
    ]


def resolve_test_principal(request):
    """TEST-ONLY: production resolution is injected by the integrator (PD-07)."""
    mid = request.headers.get("x-test-member")
    return member_principal(mid, MEMBER_SCOPES) if mid else None


@pytest.fixture
def client(spanner_db):
    svc = PersonaService(spanner_db, clock=FixedClock(NOW), candidate_source=candidates)
    app = FastAPI()
    app.include_router(create_persona_router(svc, GuestMigrationService(spanner_db, svc), resolve_test_principal))
    return TestClient(app)


@pytest.fixture
def mid(spanner_db):
    return insert_member(spanner_db)


def h(mid, **extra):
    out = {"x-test-member": mid}
    out.update({k.replace("_", "-"): v for k, v in extra.items()})
    return out


def key():
    return "k-" + uuid.uuid4().hex


def assert_problem(resp, status, code):
    assert resp.status_code == status, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    for f in ("type", "title", "status", "code", "detail", "instance", "request_id", "retryable"):
        assert f in body
    assert body["code"] == code and body["status"] == status
    return body


def test_unauthenticated_is_401(client):
    assert_problem(client.get("/me/persona"), 401, "unauthenticated")


def test_get_has_etag_and_private_headers(client, mid):
    r = client.get("/me/persona", headers=h(mid, x_request_id="0b6f1a3e-7f1d-4c55-9a0e-2f6b8c1d9e10"))
    assert r.status_code == 200 and r.headers["etag"] == '"0"'
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["x-request-id"] == "0b6f1a3e-7f1d-4c55-9a0e-2f6b8c1d9e10"
    assert r.headers["x-brandme-environment"] == "development"


def test_patch_if_match_rules(client, mid):
    body = {"changes": [{"axis": "expression", "value": 78, "locked": True}], "client_revision": "d1"}
    assert_problem(client.patch("/me/persona", json=body, headers=h(mid)), 428, "if_match_required")
    ok = client.patch("/me/persona", json=body, headers=h(mid, if_match='"0"'))
    assert ok.status_code == 200 and ok.headers["etag"] == '"1"'
    stale = assert_problem(client.patch("/me/persona", json=body, headers=h(mid, if_match='"0"')), 409, "revision_conflict")
    assert stale["current_version"] == "1" and stale["mergeable"] is False and stale["conflicting_axes"] == ["expression"]
    bad = assert_problem(
        client.patch("/me/persona", json={**body, "reward_points": 9}, headers=h(mid, if_match='"1"')), 422, "validation_failed"
    )
    assert bad["rejected_fields"] == ["reward_points"]
    raw = client.patch("/me/persona", content=b"{not json", headers={**h(mid, if_match='"1"'), "content-type": "application/json"})
    assert_problem(raw, 422, "validation_failed")


def test_idempotency_key_required_and_replayed(client, mid, spanner_db):
    client.patch("/me/persona", json={"changes": [], "client_revision": "x"}, headers=h(mid, if_match='"0"'))
    svc = PersonaService(spanner_db, clock=FixedClock(NOW))
    assert svc.ingest_evidence(member_id=mid, source_type="saved_look", source_ref="a", axis_contributions={"color": 90}) == "accepted"
    ev = client.get("/me/persona/evidence", headers=h(mid)).json()["items"][0]["evidence_id"]
    assert_problem(client.post(f"/me/persona/evidence/{ev}/suppress", headers=h(mid)), 422, "validation_failed")
    assert_problem(client.post(f"/me/persona/evidence/{ev}/suppress", headers=h(mid, idempotency_key="short")), 400, "idempotency_key_invalid")
    k = key()
    first = client.post(f"/me/persona/evidence/{ev}/suppress", headers=h(mid, idempotency_key=k))
    second = client.post(f"/me/persona/evidence/{ev}/suppress", headers=h(mid, idempotency_key=k))
    assert first.status_code == second.status_code == 200 and first.json() == second.json()
    snap = client.post("/me/persona/snapshots", json={"name": "Mine"}, headers=h(mid, idempotency_key=key()))
    assert snap.status_code == 201 and snap.json()["saved_name"] == "Mine"
    v = client.get("/me/persona", headers=h(mid)).headers["etag"]
    reset = client.post("/me/persona/reset", json={"scope": "inference", "confirm": True}, headers=h(mid, if_match=v, idempotency_key=key()))
    assert reset.status_code == 200


def test_evidence_cursor_pagination(client, mid, spanner_db):
    client.patch("/me/persona", json={"changes": [], "client_revision": "x"}, headers=h(mid, if_match='"0"'))
    svc = PersonaService(spanner_db, clock=FixedClock(NOW))
    for i in range(5):
        svc.ingest_evidence(member_id=mid, source_type="saved_look", source_ref=f"l{i}", axis_contributions={"color": 10 * i})
    seen, cursor = [], None
    while True:
        r = client.get("/me/persona/evidence", params={"limit": 2, **({"cursor": cursor} if cursor else {})}, headers=h(mid)).json()
        seen += [e["evidence_id"] for e in r["items"]]
        cursor = r["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 5 and len(set(seen)) == 5
    assert_problem(client.get("/me/persona/evidence", params={"cursor": "%%%"}, headers=h(mid)), 422, "validation_failed")
    assert_problem(client.get("/me/persona/evidence", params={"limit": 500}, headers=h(mid)), 422, "validation_failed")


def test_recommendations_and_feedback(client, mid):
    client.patch("/me/persona", json={"changes": [{"axis": "expression", "value": 80, "locked": True}], "client_revision": "x"},
                 headers=h(mid, if_match='"0"'))
    r = client.get("/recommendations", params={"limit": 4}, headers=h(mid)).json()
    assert r["rule_version"] == "det-rec-v1" and len(r["items"]) <= 4 and r["next_cursor"] is None
    pid = r["items"][0]["product_id"]
    cat = next(c.category for c in candidates() if c.product_id == pid)
    k = key()
    fb = client.post(f"/recommendations/{pid}/feedback", json={"category": cat, "signal": "not_me"}, headers=h(mid, idempotency_key=k))
    assert fb.status_code == 200
    again = client.get("/recommendations", params={"limit": 4}, headers=h(mid)).json()
    assert pid not in {i["product_id"] for i in again["items"]}


def guest_body(ns, **declared):
    return {
        "guest_namespace_id": ns,
        "persona": {"declared": {k: {"value": v, "locked": True} for k, v in declared.items()}, "onboarding_intent": "work"},
        "saved_look": True,
    }


def test_guest_migration_twice_migrates_once(client, mid, spanner_db):
    """BM-ONB-004: sign in twice after saving guest data → one profile, one migration."""
    ns = "guest-" + uuid.uuid4().hex
    first = client.post("/me/guest-migration", json=guest_body(ns, expression=72, color=40), headers=h(mid, idempotency_key=key()))
    assert first.status_code == 200 and first.json()["status"] == "migrated"
    assert first.json()["applied_axes"] == ["expression", "color"] or sorted(first.json()["applied_axes"]) == ["color", "expression"]
    second = client.post("/me/guest-migration", json=guest_body(ns, expression=72, color=40), headers=h(mid, idempotency_key=key()))
    assert second.json()["status"] == "already_migrated"
    prof = client.get("/me/persona", headers=h(mid))
    assert prof.headers["etag"] == '"1"' and prof.json()["profile"]["declared_axes"]["expression"] == 72
    from test_persona_harness import count

    assert count(spanner_db, "SELECT COUNT(*) FROM GuestMigrations WHERE member_id=@m", m=mid) == 1
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@m AND event_type='persona.guest.migrated'", m=mid) == 1
    other = insert_member(spanner_db)
    assert_problem(client.post("/me/guest-migration", json=guest_body(ns, expression=10), headers=h(other, idempotency_key=key())),
                   422, "guest_namespace_claimed")


def test_guest_migration_never_overwrites_account_choices(client, mid):
    client.patch("/me/persona", json={"changes": [{"axis": "expression", "value": 20, "locked": True}], "client_revision": "x"},
                 headers=h(mid, if_match='"0"'))
    r = client.post("/me/guest-migration", json=guest_body("guest-" + uuid.uuid4().hex, expression=90, detail=33),
                    headers=h(mid, idempotency_key=key())).json()
    assert r["applied_axes"] == ["detail"] and r["kept_account_axes"] == ["expression"]
    d = client.get("/me/persona", headers=h(mid)).json()["profile"]["declared_axes"]
    assert d["expression"] == 20 and d["detail"] == 33


def test_concurrent_guest_migrations_commit_once(client, mid, spanner_db):
    ns = "guest-" + uuid.uuid4().hex
    results = []

    def go():
        results.append(client.post("/me/guest-migration", json=guest_body(ns, expression=55), headers=h(mid, idempotency_key=key())).json())

    ts = [threading.Thread(target=go) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(r["status"] for r in results) == ["already_migrated"] * 4 + ["migrated"]
    from test_persona_harness import count

    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@m AND event_type='persona.guest.migrated'", m=mid) == 1


def test_guest_migration_rejects_unknown_sections_and_bad_values(client, mid):
    ns = "guest-" + uuid.uuid4().hex
    bad = assert_problem(client.post("/me/guest-migration", json={**guest_body(ns), "sections": {"wallet": {}}},
                                     headers=h(mid, idempotency_key=key())), 422, "validation_failed")
    assert bad["rejected_fields"] == ["wallet"]
    assert_problem(client.post("/me/guest-migration", json=guest_body(ns, expression=72.5), headers=h(mid, idempotency_key=key())),
                   422, "validation_failed")
    assert_problem(client.post("/me/guest-migration", json={**guest_body("short"), }, headers=h(mid, idempotency_key=key())),
                   422, "validation_failed")
