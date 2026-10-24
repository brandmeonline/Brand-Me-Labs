"""Try-on server: consent, jobs, retention and deletion (BM-AR-007..010 server side, BM-DATA-009).

The provider and object store here are the labelled simulation doubles
(``SimulatedTryOnProvider``, ``MemoryMediaStore``). These tests prove the
server's consent/job/deletion/retention behaviour; they are not evidence of
a real provider integration or of production object-store deletion.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from google.cloud.spanner_v1 import param_types

from brandme_core.domains import data_categories
from brandme_core.domains.media import deletion
from brandme_core.domains.media.providers import ProviderRegistry, SimulatedTryOnProvider
from brandme_core.domains.media.service import MediaService
from brandme_core.domains.media.store import MemoryMediaStore
from brandme_core.domains.persona.kernel import (
    DetailedInvalidTransition,
    Forbidden,
    NotFound,
    RateLimited,
    ValidationFailed,
    member_principal,
    run_read,
    run_txn,
    server_now,
)
from brandme_core.domains.persona.privacy_guard import guard_enforced
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x01" * 100


def key():
    return "k-" + uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc)


# Workers scan the whole (session-shared) database, as in production, so every
# test shares one simulated store and provider and filters by its own ids.
STORE, PROVIDER = MemoryMediaStore(), SimulatedTryOnProvider()


@pytest.fixture
def env(spanner_db):
    store, provider = STORE, PROVIDER
    provider.fail_with = None
    svc = MediaService(spanner_db, store, ProviderRegistry([provider]))
    me = member_principal(insert_member(spanner_db), MEMBER_SCOPES)
    item = WardrobeService(spanner_db).create_items(me, {"source": "manual", "title": "Linen shirt", "category": "top"}, key())["items"][0]["id"]
    return svc, store, provider, me, item


def upload(svc, store, me, data=PNG, ctype="image/png"):
    u = svc.create_upload(me, {"kind": "tryon_input", "content_type": ctype, "bytes": len(data)}, key())
    store.client_put(u["upload"]["url"], data, ctype, now=now())
    return svc.complete_upload(me, u["media_id"])


def consent(provider, **kw):
    return {"accepted": True, "provider_id": provider.terms.provider_id, "terms_version": provider.terms.terms_version, **kw}


def job(svc, provider, me, item, **kw):
    photo = upload(svc, svc.store, me)
    body = {"mode": "photo_preview", "input_media_id": photo["media_id"], "item_id": item, "consent": consent(provider)}
    body.update(kw)
    return photo, svc.create_job(me, body, key())


def age(db, table, member_id, **ids):
    """Move a row's expiry to Spanner-now minus 1 µs (simulates 24 h passing)."""
    where = " AND ".join(f"{k}=@{k}" for k in ids)

    def tx(t):
        t.execute_update(f"UPDATE {table} SET expires_at=@e WHERE member_id=@m AND {where}",
                         params={"e": server_now(t) - timedelta(microseconds=1), "m": member_id, **ids},
                         param_types={"e": param_types.TIMESTAMP, "m": param_types.STRING, **{k: param_types.STRING for k in ids}})

    run_txn(db, tx)


def test_unavailable_modes_and_unconfigured_provider(spanner_db, env):
    """BM-AR-009 and the provider-less setup state."""
    svc, store, provider, me, item = env
    photo = upload(svc, store, me)
    for mode, code in (("calibrated_fit", "capability_unavailable"), ("live_overlay", "on_device_only")):
        with pytest.raises(DetailedInvalidTransition) as e:
            svc.create_job(me, {"mode": mode, "input_media_id": photo["media_id"], "item_id": item, "consent": consent(provider)}, key())
        assert e.value.code == code
    caps = svc.capabilities(me)
    assert caps["calibrated_fit"]["available"] is False and caps["live_overlay"]["server"] == "on_device_only"
    assert caps["photo_preview"]["available"] is True and caps["photo_preview"]["simulated"] is True
    assert count(spanner_db, "SELECT COUNT(*) FROM TryOnJobs WHERE member_id=@m", m=me.member_id) == 0
    unconfigured = MediaService(spanner_db, store, ProviderRegistry([]))
    assert unconfigured.capabilities(me)["photo_preview"]["reason"] == "No approved photo try-on provider is configured."
    with pytest.raises(DetailedInvalidTransition) as e:
        unconfigured.create_job(me, {"mode": "photo_preview", "input_media_id": photo["media_id"], "item_id": item, "consent": consent(provider)}, key())
    assert e.value.code == "photo_preview_not_configured"
    assert provider.uploads == []


def test_no_provider_upload_without_explicit_consent(spanner_db, env):
    """BM-AR-007."""
    svc, store, provider, me, item = env
    photo = upload(svc, store, me)
    base = {"mode": "photo_preview", "input_media_id": photo["media_id"], "item_id": item}
    for c, code in ((None, "consent_required"), ({"accepted": False}, "consent_required"), ({"accepted": "yes"}, "consent_required"),
                    (consent(provider, terms_version="old-terms"), "consent_outdated")):
        with pytest.raises(ValidationFailed) as e:
            svc.create_job(me, {**base, **({"consent": c} if c is not None else {})}, key())
        assert e.value.extra["code"] == code and e.value.extra.get("provider", {}).get("retention", "x")
    assert svc.jobs_for(me.member_id) == []  # refused requests create no job, so nothing can ever be dispatched
    # Consent given, then revoked before dispatch: the queued job is cancelled and nothing is uploaded.
    j = svc.create_job(me, {**base, "consent": consent(provider)}, key())
    assert j["state"] == "queued"
    svc.revoke_consent(me, j["consent_id"])
    svc.dispatch_queued()
    assert svc.get_job(me, j["job_id"])["state"] == "cancelled"
    assert all(u[0] != j["job_id"] for u in provider.uploads)
    assert store.stat(f"members/{me.member_id}/media/{photo['media_id']}") is None  # the photo was deleted too


def test_photo_job_is_labelled_and_saved_only_by_choice(spanner_db, env):
    """BM-AR-008 server half (simulated provider) and early input deletion."""
    svc, store, provider, me, item = env
    photo, j = job(svc, provider, me, item)
    assert j["fidelity_label"] == "generated_visual_preview_simulated" and "not a fit" in j["label_text"].lower() and "Simulated" in j["label_text"]
    svc.dispatch_queued()
    assert [u[0] for u in provider.uploads].count(j["job_id"]) == 1
    svc.collect_processing()
    done = svc.get_job(me, j["job_id"])
    assert done["state"] == "succeeded" and done["result_available"] and done["saved"] is False
    created = datetime.fromisoformat(done["expires_at"].replace("Z", "+00:00")) - timedelta(hours=24)
    assert abs((created - now()).total_seconds()) < 120  # unsaved result expires 24 h after creation (server time)
    # The raw input is deleted as soon as processing ended.
    assert store.stat(f"members/{me.member_id}/media/{photo['media_id']}") is None
    assert svc.get_media_job(me, photo["media_id"])["state"] == "deleted"
    # Protected retrieval: owner only.
    ctype, data = svc.result(me, j["job_id"])
    assert ctype == "image/png" and data.startswith(b"\x89PNG")
    with pytest.raises(NotFound):
        svc.result(member_principal(insert_member(spanner_db), MEMBER_SCOPES), j["job_id"])
    saved = svc.save_job(me, j["job_id"])
    assert saved["saved"] is True and saved["expires_at"] is None


def test_unsaved_media_expires_and_saved_media_stays(spanner_db, env):
    """BM-DATA-009: past the retention window the sweeper deletes unsaved inputs/outputs."""
    svc, store, provider, me, item = env
    _, keep = job(svc, provider, me, item)
    _, drop = job(svc, provider, me, item)
    stale = svc.create_upload(me, {"kind": "tryon_input", "content_type": "image/png", "bytes": len(PNG)}, key())  # never completed
    store.client_put(stale["upload"]["url"], PNG, "image/png", now=now())
    svc.dispatch_queued()
    svc.collect_processing()
    svc.save_job(me, keep["job_id"])
    out_drop = run_read(spanner_db, lambda s: [r for r in s.execute_sql(
        "SELECT media_id, storage_ref FROM MediaObjects WHERE member_id=@m AND job_id=@j AND kind='tryon_output'",
        params={"m": me.member_id, "j": drop["job_id"]}, param_types={"m": param_types.STRING, "j": param_types.STRING})])[0]
    assert store.stat(out_drop[1]) is not None
    # 24 hours pass (server-side expiry moved to Spanner-now - 1 µs).
    age(spanner_db, "MediaObjects", me.member_id, media_id=out_drop[0])
    age(spanner_db, "MediaObjects", me.member_id, media_id=stale["media_id"])
    age(spanner_db, "TryOnJobs", me.member_id, job_id=drop["job_id"])
    swept = svc.expire_due()
    assert swept["media_expired"] >= 2 and swept["blobs_purged"] >= 2
    assert store.stat(out_drop[1]) is None and store.stat(f"members/{me.member_id}/media/{stale['media_id']}") is None
    gone = svc.get_job(me, drop["job_id"])
    assert gone["state"] == "expired" and gone["result_available"] is False and gone["provider_deletion"] == "confirmed"
    with pytest.raises(NotFound):
        svc.result(me, drop["job_id"])
    # The saved preview is untouched and has no expiry.
    kept = svc.get_job(me, keep["job_id"])
    assert kept["state"] == "succeeded" and kept["saved"] and svc.result(me, keep["job_id"])[1].startswith(b"\x89PNG")
    assert count(spanner_db, "SELECT COUNT(*) FROM MediaObjects WHERE member_id=@m AND deleted_at IS NOT NULL AND purged_at IS NULL", m=me.member_id) == 0


def test_delete_saved_preview_follows_the_manifest(spanner_db, env):
    """BM-AR-010."""
    svc, store, provider, me, item = env
    photo, j = job(svc, provider, me, item)
    svc.dispatch_queued()
    svc.collect_processing()
    svc.save_job(me, j["job_id"])
    with spanner_db.snapshot() as s:
        refs = {r[0]: r[1] for r in s.execute_sql("SELECT media_id, storage_ref FROM MediaObjects WHERE member_id=@m AND job_id=@j",
                                                  params={"m": me.member_id, "j": j["job_id"]},
                                                  param_types={"m": param_types.STRING, "j": param_types.STRING})}
    assert len(refs) == 2  # input (already purged after processing) + output
    out = svc.delete_job(me, j["job_id"])
    assert out["state"] == "deleted" and out["blobs_purged"] == 1 and out["provider_deletion"] == "confirmed"
    assert all(store.stat(r) is None for r in refs.values())
    assert f"sim-{j['job_id']}" in provider.deleted
    assert "Simulated provider" in out["provider_retention"]
    with pytest.raises(NotFound):
        svc.result(me, j["job_id"])
    assert count(spanner_db, "SELECT COUNT(*) FROM MediaObjects WHERE member_id=@m AND job_id=@j AND (deleted_at IS NULL OR purged_at IS NULL)",
                 m=me.member_id, j=j["job_id"]) == 0
    again = svc.delete_job(me, j["job_id"])
    assert again["media_deleted"] == [] and again["blobs_purged"] == 0
    with pytest.raises(NotFound):  # another member cannot delete (or learn about) it
        svc.delete_job(member_principal(insert_member(spanner_db), MEMBER_SCOPES), j["job_id"])


def test_delete_while_processing_leaves_no_orphans(spanner_db, env):
    svc, store, provider, me, item = env
    _, j = job(svc, provider, me, item)
    svc.dispatch_queued()  # now processing at the provider
    out = svc.delete_job(me, j["job_id"])
    assert out["provider_deletion"] == "confirmed"
    mine = lambda: {r for r in store.objects if r.startswith(f"members/{me.member_id}/")}  # noqa: E731
    before = mine()
    svc.collect_processing()  # the provider finishes later; its output must not be kept
    assert mine() == before
    assert svc.get_job(me, j["job_id"])["state"] == "deleted"


def test_provider_failure_is_an_outcome(spanner_db, env):
    svc, store, provider, me, item = env
    photo, j = job(svc, provider, me, item)
    provider.fail_with = "unsuitable_photo"
    svc.dispatch_queued()
    svc.collect_processing()
    got = svc.get_job(me, j["job_id"])
    assert got["state"] == "failed" and got["error_code"] == "unsuitable_photo" and not got["result_available"]
    assert store.stat(f"members/{me.member_id}/media/{photo['media_id']}") is None
    provider.fail_with = None


def test_upload_constraints(spanner_db, env):
    svc, store, provider, me, item = env
    bad = upload(svc, store, me, data=JPEG_BYTES, ctype="image/png")  # bytes are not a PNG
    assert bad["state"] == "rejected" and bad["rejection_code"] == "unsupported_content"
    assert store.stat(f"members/{me.member_id}/media/{bad['media_id']}") is None
    ok = upload(svc, store, me, data=JPEG_BYTES, ctype="image/jpeg")
    assert ok["state"] == "verified"
    with pytest.raises(ValidationFailed):
        svc.create_upload(me, {"kind": "tryon_input", "content_type": "image/gif", "bytes": 10}, key())
    with pytest.raises(ValidationFailed):
        svc.create_upload(me, {"kind": "tryon_input", "content_type": "image/png", "bytes": 50 * 1024 * 1024}, key())
    u = svc.create_upload(me, {"kind": "tryon_input", "content_type": "image/png", "bytes": 10}, key())
    with pytest.raises(PermissionError):  # bigger than declared
        store.client_put(u["upload"]["url"], PNG, "image/png", now=now())
    k = key()
    a = svc.create_upload(me, {"kind": "tryon_input", "content_type": "image/png", "bytes": 10}, k)
    b = svc.create_upload(me, {"kind": "tryon_input", "content_type": "image/png", "bytes": 10}, k)
    assert a["media_id"] == b["media_id"] and a["upload"]["url"] != b["upload"]["url"]  # replay: same object, fresh URL
    assert "storage_ref" not in a and "members/" not in a["upload"]["url"]
    with pytest.raises(NotFound):
        svc.get_media_job(member_principal(insert_member(spanner_db), MEMBER_SCOPES), ok["media_id"])
    with pytest.raises(Forbidden):
        svc.create_upload(member_principal(me.member_id, {"wardrobe:read"}), {"kind": "tryon_input", "content_type": "image/png", "bytes": 1}, key())
    # An input can be used for one job only, and a product needs a wired catalog.
    photo, _ = job(svc, provider, me, item)
    with pytest.raises(DetailedInvalidTransition):
        svc.create_job(me, {"mode": "photo_preview", "input_media_id": photo["media_id"], "item_id": item, "consent": consent(provider)}, key())
    with pytest.raises(NotFound):
        svc.create_job(me, {"mode": "photo_preview", "input_media_id": upload(svc, store, me)["media_id"], "product_id": str(uuid.uuid4()),
                            "consent": consent(provider)}, key())


def test_daily_spend_limit(spanner_db):
    store, provider = STORE, PROVIDER
    svc = MediaService(spanner_db, store, ProviderRegistry([provider]), daily_job_limit=2)
    me = member_principal(insert_member(spanner_db), MEMBER_SCOPES)
    item = WardrobeService(spanner_db).create_items(me, {"source": "manual", "title": "Tee", "category": "top"}, key())["items"][0]["id"]
    job(svc, provider, me, item)
    job(svc, provider, me, item)
    with pytest.raises(RateLimited):
        job(svc, provider, me, item)


def test_privacy_export_and_delete_purges_blobs(spanner_db, env):
    svc, store, provider, me, item = env
    _, j = job(svc, provider, me, item)
    svc.dispatch_queued()
    svc.collect_processing()
    svc.save_job(me, j["job_id"])
    assert {c.name for c in data_categories() if c.domain == "media"} == set(deletion.CATEGORIES)
    exported = {c: run_read(spanner_db, lambda s, c=c: deletion.export_category(s, me.member_id, c)) for c in deletion.CATEGORIES}
    assert exported["media.tryon_consents"][0]["provider_id"] == provider.terms.provider_id
    assert exported["media.tryon_media"][0]["jobs"][0]["fidelity_label"] == "generated_visual_preview_simulated"
    mine = [r for r in store.objects if r.startswith(f"members/{me.member_id}/")]
    assert mine
    cats = {c.name: c for c in data_categories() if c.domain == "media"}
    for name in deletion.CATEGORIES:
        cats[name].delete(spanner_db, me.member_id)
    assert [r for r in store.objects if r.startswith(f"members/{me.member_id}/")] == []
    for table in ("TryOnConsents", "TryOnJobs", "MediaObjects"):
        assert count(spanner_db, f"SELECT COUNT(*) FROM {table} WHERE member_id=@m", m=me.member_id) == 0


def test_http_surface(spanner_db, env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from brandme_core.domains.media.api import create_media_router

    svc, store, provider, me, item = env
    app = FastAPI()
    app.include_router(create_media_router(svc, lambda r: member_principal(r.headers["x-test-member"], MEMBER_SCOPES)
                                           if r.headers.get("x-test-member") else None))
    c = TestClient(app)
    h = {"x-test-member": me.member_id}
    assert c.get("/try-on/capabilities").status_code == 401
    assert c.get("/try-on/capabilities", headers=h).json()["calibrated_fit"]["available"] is False
    u = c.post("/media/uploads", json={"kind": "tryon_input", "content_type": "image/png", "bytes": len(PNG)}, headers={**h, "Idempotency-Key": key()})
    assert u.status_code == 201 and u.json()["state"] == "awaiting_upload"
    store.client_put(u.json()["upload"]["url"], PNG, "image/png", now=now())
    mid = u.json()["media_id"]
    assert c.post(f"/media/uploads/{mid}/complete", headers=h).json()["state"] == "verified"
    assert c.get(f"/media/jobs/{mid}", headers=h).json()["state"] == "verified"
    body = {"mode": "photo_preview", "input_media_id": mid, "item_id": item}
    refused = c.post("/try-on/jobs", json=body, headers={**h, "Idempotency-Key": key()})
    assert refused.status_code == 422 and refused.json()["code"] == "validation_failed" and refused.json()["field"] == "consent"
    fit = c.post("/try-on/jobs", json={**body, "mode": "calibrated_fit", "consent": consent(provider)}, headers={**h, "Idempotency-Key": key()})
    assert fit.status_code == 422 and fit.json()["code"] == "capability_unavailable"
    j = c.post("/try-on/jobs", json={**body, "consent": consent(provider)}, headers={**h, "Idempotency-Key": key()})
    assert j.status_code == 202 and j.json()["state"] == "queued"
    jid = j.json()["job_id"]
    svc.dispatch_queued()
    svc.collect_processing()
    res = c.get(f"/try-on/jobs/{jid}/result", headers=h)
    assert res.status_code == 200 and res.headers["content-type"] == "image/png" and res.headers["cache-control"] == "private, no-store"
    assert c.get(f"/try-on/jobs/{jid}/result", headers={"x-test-member": insert_member(spanner_db)}).status_code == 404
    assert c.post(f"/try-on/jobs/{jid}/save", headers=h).json()["saved"] is True
    assert c.delete(f"/try-on/jobs/{jid}", headers=h).status_code == 204
    assert c.get(f"/try-on/jobs/{jid}", headers=h).json()["state"] == "deleted"
    assert c.get(f"/try-on/jobs/{jid}/result", headers=h).status_code == 404
    cid = c.get("/try-on/consents", headers=h).json()["items"][0]["consent_id"]
    assert c.delete(f"/try-on/consents/{cid}", headers=h).json()["revoked_at"]


@pytest.mark.skipif(not guard_enforced(), reason="privacy lane not on this branch; freeze/registration check NOT RUN")
def test_privacy_lane_freeze_stops_uploads_and_dispatch(spanner_db, env):
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    svc, store, provider, me, item = env
    assert deletion.PRIVACY_HANDLER is not None
    _, j = job(svc, provider, me, item)  # queued before the freeze
    run_txn(spanner_db, lambda t: t.insert("ProcessingFreezes", columns=("subject_ref", "category", "reason", "deletion_job_id", "created_at"),
                                           values=[(me.member_id, "*", "deletion", str(uuid.uuid4()), COMMIT_TIMESTAMP)]))
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.create_upload(me, {"kind": "tryon_input", "content_type": "image/png", "bytes": 10}, key())
    assert e.value.code == "processing_frozen"
    svc.dispatch_queued()
    got = svc.get_job(me, j["job_id"])
    assert got["state"] == "cancelled" and got["error_code"] == "processing_frozen"
    assert all(u[0] != j["job_id"] for u in provider.uploads)


def test_deletion_asks_the_provider_to_delete_an_in_flight_job(spanner_db, env, monkeypatch):
    svc, store, provider, me, item = env
    _, j = job(svc, provider, me, item)
    svc.dispatch_queued()  # the provider now holds a copy; the job is still processing
    ref = next(x["provider_job_ref"] for x in svc.jobs_for(me.member_id) if x["job_id"] == j["job_id"])
    assert ref
    calls = []
    monkeypatch.setattr(provider, "delete", lambda r: calls.append(r) or False)  # first attempt fails
    cats = {c.name: c for c in data_categories() if c.domain == "media"}
    cats["media.tryon_media"].delete(spanner_db, me.member_id)
    assert calls == [ref]
    (left,) = svc.jobs_for(me.member_id)
    assert (left["state"], left["provider_deletion"], left["input_media_ref"], left["item_id"]) == ("deleted", "requested", None, None)
    monkeypatch.undo()
    out = deletion.purge_provider_jobs(spanner_db, me.member_id)
    assert (out["done"], out["provider_deleted"], out["pending"]) == (True, 1, 0)
    assert ref in provider.deleted and svc.jobs_for(me.member_id) == []


def test_provider_without_deletion_is_reported_not_hidden(spanner_db, env, monkeypatch):
    svc, store, provider, me, item = env
    job(svc, provider, me, item)
    svc.dispatch_queued()

    class NoDelete:
        terms = type("T", (), {"supports_deletion": False})()

    monkeypatch.setattr(deletion, "_PROVIDERS", type("R", (), {"get": staticmethod(lambda _pid: NoDelete())})())
    run_txn(spanner_db, lambda t: deletion.delete_category(t, me.member_id, "media.tryon_media"))
    out = deletion.purge_all(spanner_db, me.member_id)
    assert out["done"] and out["exception"] == deletion.PROVIDER_RETAINS
    assert svc.jobs_for(me.member_id) == []


def test_failed_dispatch_deletes_the_input_now(spanner_db, env, monkeypatch):
    svc, store, provider, me, item = env
    photo, j = job(svc, provider, me, item)
    blob = next(r for r in store.objects if r.startswith(f"members/{me.member_id}/"))

    def boom(*_a, **_k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(provider, "submit", boom)
    svc.dispatch_queued()
    got = svc.get_job(me, j["job_id"])
    assert (got["state"], got["error_code"]) == ("failed", "provider_error")
    assert blob not in store.objects  # not left for the 24 h sweeper
    assert count(spanner_db, "SELECT COUNT(*) FROM MediaObjects WHERE member_id=@m AND media_id=@i AND deleted_at IS NULL",
                 m=me.member_id, i=photo["media_id"]) == 0
