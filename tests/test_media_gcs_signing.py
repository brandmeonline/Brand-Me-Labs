"""GCS adapter without a server: V4 signing against Google's conformance
vectors, the signed upload constraints, the bucket policy check and the
environment selection.

The vectors (tests/fixtures/media/gcs_v4_signing_vectors.json) are Google's
``signingV4Tests`` for the path-style URLs this adapter produces. Each must
match byte for byte: canonical request, string-to-sign and the full URL.
Google's expected signature must also verify, under the published dummy key's
public half, over the string-to-sign computed here. Real GCS enforcement of
the signed headers is NOT RUN here; that needs the dev bucket (ruling Q14).
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from brandme_core.domains.media import gcs_store
from brandme_core.domains.media.gcs_store import (
    LIFECYCLE_RULE,
    GcsMediaStore,
    GoogleAuthSigner,
    KeySigner,
    bucket_findings,
    sign_v4,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures/media/gcs_v4_signing_vectors.json").read_text(encoding="utf-8"))
VECTORS = FIXTURE["vectors"]


def _sign_vector(v, sign):
    host, scheme = "storage.googleapis.com", v.get("scheme", "https")
    if v.get("emulatorHostname"):
        parts = urlsplit(v["emulatorHostname"])
        host, scheme = parts.netloc, parts.scheme
    return sign_v4(method=v["method"], bucket=v["bucket"], obj=v.get("object"),
                   timestamp=datetime.fromisoformat(v["timestamp"].replace("Z", "+00:00")), expires=v["expiration"],
                   email=FIXTURE["client_email"], sign=sign, host=host, scheme=scheme, headers=v.get("headers"),
                   query=v.get("queryParameters"))


def test_vector_set_is_the_vendored_one():
    assert FIXTURE["source"].startswith("https://github.com/googleapis/conformance-tests/")
    assert len(VECTORS) == 18 and "PRIVATE KEY" not in json.dumps(FIXTURE)


@pytest.mark.parametrize("vector", VECTORS, ids=[v["description"] for v in VECTORS])
def test_v4_signing_matches_google_conformance_vectors(vector):
    expected_signature = parse_qs(urlsplit(vector["expectedUrl"]).query)["X-Goog-Signature"][0]
    signed = _sign_vector(vector, lambda _msg: bytes.fromhex(expected_signature))
    assert signed.canonical_request == vector["expectedCanonicalRequest"]
    assert signed.string_to_sign == vector["expectedStringToSign"]
    assert signed.url == vector["expectedUrl"]
    # Google's signature covers exactly the string-to-sign computed here.
    public = serialization.load_pem_public_key(FIXTURE["public_key_pem"].encode())
    public.verify(bytes.fromhex(expected_signature), signed.string_to_sign.encode(), padding.PKCS1v15(), hashes.SHA256())


def test_signing_refuses_out_of_range_expiry():
    for expires in (0, 604801):
        with pytest.raises(ValueError):
            sign_v4(method="PUT", bucket="b", obj="o", timestamp=datetime.now(timezone.utc), expires=expires, email="e", sign=bytes)


def test_upload_target_signs_every_constraint_and_caps_the_window():
    signer = KeySigner.ephemeral()
    t0 = datetime(2026, 10, 24, 3, 0, tzinfo=timezone.utc)
    store = GcsMediaStore("brandme-dev-media", session=None, signer=signer, clock=lambda: t0)
    target = store.upload_target("members/m/media/x", content_type="image/png", max_bytes=1234, expires_at=t0 + timedelta(hours=1))
    assert tuple(target["headers"]) == gcs_store.UPLOAD_HEADERS  # the bucket CORS check uses the same list
    assert target["method"] == "PUT" and target["simulated"] is False and target["max_bytes"] == 1234
    assert target["headers"] == {"Content-Type": "image/png", "x-goog-content-length-range": "0,1234",
                                 "x-goog-if-generation-match": "0", "x-goog-custom-time": "2026-10-24T03:00:00.000Z"}
    assert target["expires_at"] == t0 + timedelta(minutes=15)  # capped, whatever the upload window says
    url = urlsplit(target["url"])
    q = parse_qs(url.query)
    assert url.scheme == "https" and url.netloc == "storage.googleapis.com" and url.path == "/brandme-dev-media/members/m/media/x"
    assert q["X-Goog-SignedHeaders"] == ["content-type;host;x-goog-content-length-range;x-goog-custom-time;x-goog-if-generation-match"]
    assert q["X-Goog-Expires"] == ["900"]
    # The signature verifies over these exact headers; changing any one of them changes what is signed.
    again = sign_v4(method="PUT", bucket="brandme-dev-media", obj="members/m/media/x", timestamp=t0, expires=900, email=signer.email,
                    sign=signer.sign, headers=target["headers"])
    signer.public_key().verify(bytes.fromhex(q["X-Goog-Signature"][0]), again.string_to_sign.encode(), padding.PKCS1v15(), hashes.SHA256())
    looser = sign_v4(method="PUT", bucket="brandme-dev-media", obj="members/m/media/x", timestamp=t0, expires=900, email=signer.email,
                     sign=signer.sign, headers={**target["headers"], "x-goog-content-length-range": "0,99999999"})
    assert looser.string_to_sign != again.string_to_sign

    short = store.upload_target("members/m/media/y", content_type="image/png", max_bytes=1, expires_at=t0 + timedelta(minutes=2))
    assert short["expires_at"] == t0 + timedelta(minutes=2) and parse_qs(urlsplit(short["url"]).query)["X-Goog-Expires"] == ["120"]
    with pytest.raises(ValueError):
        store.upload_target("members/m/media/z", content_type="image/png", max_bytes=1, expires_at=t0)


GOOD_BUCKET = {
    "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True}, "publicAccessPrevention": "enforced"},
    "versioning": {"enabled": False},
    "softDeletePolicy": {"retentionDurationSeconds": "0"},
    "lifecycle": {"rule": [LIFECYCLE_RULE]},
    "cors": [{"origin": ["https://app.brandme.example"], "method": ["PUT"], "responseHeader": list(gcs_store.UPLOAD_HEADERS),
              "maxAgeSeconds": 300}],
}


def test_bucket_policy_check():
    assert bucket_findings(GOOD_BUCKET) == []
    cases = {
        "uniform_bucket_level_access_disabled": {"iamConfiguration": {"publicAccessPrevention": "enforced"}},
        "public_access_prevention_not_enforced": {"iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True},
                                                                       "publicAccessPrevention": "inherited"}},
        "object_versioning_enabled": {"versioning": {"enabled": True}},
        "soft_delete_not_disabled": {"softDeletePolicy": {"retentionDurationSeconds": "604800"}},
        "retention_policy_blocks_deletion": {"retentionPolicy": {"retentionPeriod": "86400"}},
        "event_based_hold_blocks_deletion": {"defaultEventBasedHold": True},
        "custom_time_backstop_missing": {"lifecycle": {"rule": []}},
        "cors_put_missing": {"cors": [{"origin": ["*"], "method": ["GET"]}]},
        # The browser preflight for the signed PUT names every signed header; GCS must allow each one.
        "cors_upload_headers_missing": {"cors": [{"origin": ["https://app.brandme.example"], "method": ["PUT"],
                                                  "responseHeader": ["Content-Type"]}]},
    }
    for finding, change in cases.items():
        assert finding in bucket_findings({**GOOD_BUCKET, **change}), finding
    assert "soft_delete_not_disabled" in bucket_findings({k: v for k, v in GOOD_BUCKET.items() if k != "softDeletePolicy"})
    # An age-based delete would also remove saved previews.
    aged = {"lifecycle": {"rule": [LIFECYCLE_RULE, {"action": {"type": "Delete"}, "condition": {"age": 30}}]}}
    assert bucket_findings({**GOOD_BUCKET, **aged}) == ["lifecycle_rule_may_delete_saved_media"]


def test_environment_selection():
    assert gcs_store.from_environment({"ENVIRONMENT": "development"}) is None
    with pytest.raises(ValueError):
        gcs_store.from_environment({"ENVIRONMENT": "production", "BRANDME_MEDIA_BUCKET": "b", "STORAGE_EMULATOR_HOST": "localhost:4443"})
    dev = gcs_store.from_environment({"ENVIRONMENT": "development", "BRANDME_MEDIA_BUCKET": "b", "STORAGE_EMULATOR_HOST": "localhost:4443"})
    assert dev.emulator is True and dev._api == "http://localhost:4443" and dev.signer.email.endswith(".invalid")


def test_key_file_credentials_sign_locally():
    """The service-account-key path of GoogleAuthSigner. The workload-identity
    path (IAM signBlob) needs real IAM: NOT RUN."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from google.oauth2 import service_account

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    # A key generated just above, never a credential; from_service_account_info needs no "type" field.
    creds = service_account.Credentials.from_service_account_info(
        {"client_email": "media@brandme-dev.iam.gserviceaccount.com", "private_key": pem, "private_key_id": "test",
         "token_uri": "https://oauth2.googleapis.com/token"})
    signer = GoogleAuthSigner(creds)
    assert signer.email == "media@brandme-dev.iam.gserviceaccount.com"
    key.public_key().verify(signer.sign(b"payload"), b"payload", padding.PKCS1v15(), hashes.SHA256())


def test_credential_shapes_choose_the_right_signer(monkeypatch):
    """Impersonated credentials sign via their own sign_bytes. Metadata-server
    (GKE workload identity) credentials go to IAM signBlob. User credentials
    are refused. The IAM call itself is stubbed: NOT RUN against real IAM."""
    from google.auth import iam

    class Impersonated:
        service_account_email = "media@brandme-dev.iam.gserviceaccount.com"

        def sign_bytes(self, message):
            return b"imp:" + message

    assert GoogleAuthSigner(Impersonated()).sign(b"m") == b"imp:m"

    calls = []

    class FakeIamSigner:
        def __init__(self, _request, credentials, email):
            calls.append(email)

        def sign(self, message):
            return b"iam:" + message

    class Metadata:
        service_account_email = "default"

        def refresh(self, _request):
            self.service_account_email = "dom-media@brandme-dev.iam.gserviceaccount.com"

    monkeypatch.setattr(iam, "Signer", FakeIamSigner)
    signer = GoogleAuthSigner(Metadata())
    assert (signer.email, signer.sign(b"m"), calls) == ("dom-media@brandme-dev.iam.gserviceaccount.com", b"iam:m",
                                                        ["dom-media@brandme-dev.iam.gserviceaccount.com"])

    class User:
        def refresh(self, _request):
            pass

    with pytest.raises(ValueError):
        GoogleAuthSigner(User())


def test_adc_requests_scopes_for_objects_and_iam_signing(monkeypatch):
    """Runtimes that honour requested scopes (Cloud Run, GKE workload identity)
    need the IAM scope for signBlob, as well as the storage scope."""
    import google.auth

    seen = {}

    class Creds:
        service_account_email = "dom-media@brandme-dev.iam.gserviceaccount.com"

        def sign_bytes(self, message):
            return message

    def fake_default(scopes=None):
        seen["scopes"] = scopes
        return Creds(), "brandme-dev"

    monkeypatch.setattr(google.auth, "default", fake_default)
    store = gcs_store.from_environment({"ENVIRONMENT": "development", "BRANDME_MEDIA_BUCKET": "brandme-dev-media"})
    assert store.emulator is False and set(seen["scopes"]) == {"https://www.googleapis.com/auth/devstorage.read_write",
                                                               "https://www.googleapis.com/auth/iam"}


def test_gzip_encoded_object_is_read_as_stored_bytes():
    """A client can add an unsigned Content-Encoding: gzip to its upload. Real
    GCS then stores the compressed bytes and serves them with that header. The
    store must return the stored bytes undecoded, so a tiny upload cannot expand
    in memory and fails the PNG magic-byte check. A local server plays that GCS
    behaviour here; the emulator decompresses on write instead."""
    import base64
    import gzip
    import hashlib
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import requests

    from brandme_core.domains.media.store import MAX_BYTES, sniff

    stored = gzip.compress(b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * MAX_BYTES))
    meta = {"size": str(len(stored)), "generation": "1", "contentEncoding": "gzip",
            "md5Hash": base64.b64encode(hashlib.md5(stored).digest()).decode()}  # noqa: S324 - GCS integrity field

    class Gcs(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = stored if "alt=media" in self.path else json.dumps(meta).encode()
            self.send_response(200)
            if "alt=media" in self.path:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Gcs)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        store = GcsMediaStore("b", session=requests.Session(), signer=KeySigner.ephemeral(),
                              api_endpoint=f"http://127.0.0.1:{server.server_port}")
        assert store.stat("members/m/media/x") == (len(stored), hashlib.sha256(stored).hexdigest())
        data = store.read("members/m/media/x")
        assert data == stored and not sniff(data[:16], "image/png")
    finally:
        server.shutdown()
