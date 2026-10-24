"""GcsMediaStore against a local GCS emulator (pinned fake-gcs-server, started
here from GCS_EMULATOR_BIN; CI fetches it with scripts/python/fetch_gcs_emulator.py).

What this proves: the try-on object flow through the JSON and XML APIs. Signed
client PUT, stat with SHA-256 pinned to the generation, provider output
writes with ``customTime``, retain-on-save, delete and purge. Also the jobs
process sweeping unsaved media on this store.

What the emulator cannot prove: it checks no signature or signed header
(create-only, size range, ``x-goog-custom-time``), runs no lifecycle rules and
has no soft delete. ``test_media_gcs_signing.py`` covers the signing itself
against Google's vectors. GCS's own enforcement needs the dev bucket (Q14):
NOT RUN. The tests use their own migrated Spanner database, because the media
workers scan the whole database.
"""

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from google.cloud.spanner_v1 import param_types

from brandme_core.domains.media.gcs_store import RETAINED_CUSTOM_TIME, GcsMediaStore, KeySigner, StorageUnavailable
from brandme_core.domains.media.providers import ProviderRegistry, SimulatedTryOnProvider
from brandme_core.domains.media.service import MediaService
from brandme_core.domains.media.store import MAX_BYTES
from brandme_core.domains.persona.kernel import member_principal, run_read, run_txn, server_now
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import INSTANCE, MEMBER_SCOPES, PROJECT, insert_member, new_migrated_database

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPEG = b"\xff\xd8\xff\xe0" + b"\x01" * 100


def key():
    return "k-" + uuid.uuid4().hex


@pytest.fixture(scope="module")
def gcs_api():
    binary = os.environ.get("GCS_EMULATOR_BIN")
    if not binary or not os.access(binary, os.X_OK):
        pytest.skip("GCS_EMULATOR_BIN required; CI fetches the pinned fake-gcs-server. GCS store suite NOT RUN")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    api = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([binary, "-scheme", "http", "-host", "127.0.0.1", "-port", str(port), "-backend", "memory",
                             "-external-url", api, "-public-host", f"127.0.0.1:{port}", "-log-level", "error"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                requests.get(f"{api}/storage/v1/b", timeout=1)
                break
            except requests.ConnectionError:
                time.sleep(0.1)
        else:
            pytest.fail("fake-gcs-server did not start")
        yield api
    finally:
        proc.terminate()
        proc.wait(10)


@pytest.fixture(scope="module")
def media_db():
    database = new_migrated_database()
    yield database
    database.drop()


def new_store(api):
    bucket = "bm-" + uuid.uuid4().hex[:20]
    requests.post(f"{api}/storage/v1/b", params={"project": "brandme-dev"}, json={"name": bucket}, timeout=10).raise_for_status()
    return GcsMediaStore(bucket, session=requests.Session(), signer=KeySigner.ephemeral(), api_endpoint=api, emulator=True)


@pytest.fixture
def env(gcs_api, media_db):
    store, provider = new_store(gcs_api), SimulatedTryOnProvider()
    svc = MediaService(media_db, store, ProviderRegistry([provider]))
    me = member_principal(insert_member(media_db), MEMBER_SCOPES)
    item = WardrobeService(media_db).create_items(me, {"source": "manual", "title": "Linen shirt", "category": "top"}, key())["items"][0]["id"]
    return svc, store, provider, me, item


def put(target, data):
    """What the browser does with the signed target."""
    r = requests.put(target["url"], data=data, headers=target["headers"], timeout=10)
    assert r.status_code == 200, r.text


def upload(svc, me, data=PNG, ctype="image/png", declared=None):
    u = svc.create_upload(me, {"kind": "tryon_input", "content_type": ctype, "bytes": declared or len(data)}, key())
    put(u["upload"], data)
    return svc.complete_upload(me, u["media_id"])


def ref(me, media_id):
    return f"members/{me.member_id}/media/{media_id}"


def test_store_contract(gcs_api):
    store = new_store(gcs_api)
    now = datetime.now(timezone.utc)
    store.write("members/m/media/out", PNG, "image/png")
    meta = store._meta("members/m/media/out")
    assert meta["contentType"] == "image/png" and abs(datetime.fromisoformat(meta["customTime"].replace("Z", "+00:00")) - now) < timedelta(minutes=1)
    assert store.read("members/m/media/out") == PNG
    store.retain("members/m/media/out")
    assert store._meta("members/m/media/out")["customTime"] == RETAINED_CUSTOM_TIME
    assert store.delete("members/m/media/out") is True and store.delete("members/m/media/out") is False
    assert store.stat("members/m/media/out") is None
    for missing in (store.read, store.retain):
        with pytest.raises(KeyError):
            missing("members/m/media/out")
    # An oversized object is reported by size, never downloaded.
    store.write("members/m/media/big", b"\x00" * (MAX_BYTES + 1), "image/png")
    assert store.stat("members/m/media/big") == (MAX_BYTES + 1, "")


def test_try_on_flow_on_the_emulator(media_db, env):
    """Upload → verify → dispatch → result → save (retain) → delete, with every byte in the bucket."""
    svc, store, provider, me, item = env
    photo = upload(svc, me)
    assert photo["state"] == "verified" and store.stat(ref(me, photo["media_id"]))[1] == svc_hash(media_db, me, photo["media_id"])
    consent = {"accepted": True, "provider_id": provider.terms.provider_id, "terms_version": provider.terms.terms_version}
    j = svc.create_job(me, {"mode": "photo_preview", "input_media_id": photo["media_id"], "item_id": item, "consent": consent}, key())
    svc.dispatch_queued()
    svc.collect_processing()
    done = svc.get_job(me, j["job_id"])
    assert done["state"] == "succeeded" and done["result_available"] is True
    assert store.stat(ref(me, photo["media_id"])) is None  # the input is deleted as soon as processing ends
    out_ref = run_read(media_db, lambda s: svc._job(s, me.member_id, j["job_id"]))["output_media_ref"]
    assert store._meta(ref(me, out_ref))["customTime"] != RETAINED_CUSTOM_TIME  # unsaved: in the lifecycle backstop
    ctype, data = svc.result(me, j["job_id"])
    assert ctype == "image/png" and data == store.read(ref(me, out_ref))

    svc.save_job(me, j["job_id"])
    assert store._meta(ref(me, out_ref))["customTime"] == RETAINED_CUSTOM_TIME  # saved: out of the backstop

    svc.delete_job(me, j["job_id"])
    assert store._meta(ref(me, out_ref)) is None
    purged = run_read(media_db, lambda s: list(s.execute_sql(
        "SELECT COUNT(*) FROM MediaObjects WHERE member_id=@m AND purged_at IS NULL", params={"m": me.member_id},
        param_types={"m": param_types.STRING})))[0][0]
    assert purged == 0


def svc_hash(db, me, media_id):
    return run_read(db, lambda s: list(s.execute_sql(
        "SELECT content_hash FROM MediaObjects WHERE member_id=@m AND media_id=@i", params={"m": me.member_id, "i": media_id},
        param_types={"m": param_types.STRING, "i": param_types.STRING})))[0][0]


def test_service_rejects_what_the_emulator_lets_through(env):
    """The emulator accepts bytes that GCS would refuse under the signed headers
    (oversize, wrong type). The service's own checks still reject them and purge."""
    svc, store, _provider, me, _item = env
    big = upload(svc, me, data=PNG + b"\x00" * 500, declared=len(PNG))
    assert (big["state"], big["rejection_code"]) == ("rejected", "too_large") and store.stat(ref(me, big["media_id"])) is None
    spoof = upload(svc, me, data=JPEG, ctype="image/png")
    assert (spoof["state"], spoof["rejection_code"]) == ("rejected", "unsupported_content") and store.stat(ref(me, spoof["media_id"])) is None


def test_save_fails_closed_when_storage_is_down(media_db, env):
    """Retain runs before the save commits: if storage is down, the preview stays unsaved and keeps expiring."""
    svc, store, provider, me, item = env
    photo = upload(svc, me)
    consent = {"accepted": True, "provider_id": provider.terms.provider_id, "terms_version": provider.terms.terms_version}
    j = svc.create_job(me, {"mode": "photo_preview", "input_media_id": photo["media_id"], "item_id": item, "consent": consent}, key())
    svc.dispatch_queued()
    svc.collect_processing()
    store._api = "http://127.0.0.1:9"  # nothing listens on the discard port
    with pytest.raises(StorageUnavailable) as err:
        svc.save_job(me, j["job_id"])
    assert (err.value.status, err.value.retryable) == (503, True)
    assert svc.get_job(me, j["job_id"])["saved"] is False


def test_jobs_process_sweeps_unsaved_media_on_gcs(media_db, gcs_api, env):
    svc, store, _provider, me, _item = env
    u = svc.create_upload(me, {"kind": "tryon_input", "content_type": "image/png", "bytes": len(PNG)}, key())
    put(u["upload"], PNG)  # uploaded but never completed: expires with the upload record

    def age(t):
        t.execute_update("UPDATE MediaObjects SET expires_at=@e WHERE member_id=@m AND media_id=@i",
                         params={"e": server_now(t) - timedelta(seconds=1), "m": me.member_id, "i": u["media_id"]},
                         param_types={"e": param_types.TIMESTAMP, "m": param_types.STRING, "i": param_types.STRING})

    run_txn(media_db, age)
    env_vars = {**os.environ, "BRANDME_MODE": "development", "ENVIRONMENT": "development", "SPANNER_PROJECT_ID": PROJECT,
                "SPANNER_INSTANCE_ID": INSTANCE, "SPANNER_DATABASE_ID": media_db.database_id,
                "BRANDME_MEDIA_BUCKET": store.bucket, "STORAGE_EMULATOR_HOST": gcs_api}
    run = subprocess.run([sys.executable, "-m", "brandme_core.domains.persona.jobs", "--once"], env=env_vars, capture_output=True,
                         text=True, timeout=120, cwd=Path(__file__).resolve().parents[1])
    assert run.returncode == 0, run.stdout + run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["status"] == "ran" and out["media"]["media_expired"] >= 1 and out["media"]["blobs_purged"] >= 1
    assert me.member_id not in run.stdout + run.stderr
    assert store.stat(ref(me, u["media_id"])) is None


def test_bucket_check_flags_an_unprepared_bucket(gcs_api):
    """A default bucket is not fit for private media: the check says so instead of passing silently."""
    findings = new_store(gcs_api).check_bucket()
    assert {"soft_delete_not_disabled", "custom_time_backstop_missing", "public_access_prevention_not_enforced"} <= set(findings)
