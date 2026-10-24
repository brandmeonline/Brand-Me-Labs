"""
Private Google Cloud Storage adapter for ``MediaStore`` (check-in ruling Q19).

* **Uploads** go straight from the client to GCS with a V4 signed ``PUT`` URL
  (GOOG4-RSA-SHA256, at most 15 minutes). The URL signs ``content-type``,
  ``x-goog-content-length-range: 0,<declared bytes>``,
  ``x-goog-if-generation-match: 0`` (create only, so a verified object cannot be
  replaced) and ``x-goog-custom-time``. A client that drops or changes any of
  them gets a signature failure from GCS. ``MediaService.complete_upload``
  still re-checks size, magic bytes and hash itself, so the emulator, which
  does not verify signatures or headers, cannot weaken the checks.
* **Reads and writes** use the JSON API through an authorized session. ``stat``
  hashes the bytes itself, since GCS reports MD5/CRC32C, not SHA-256. The
  download is pinned to the generation it just read and checked against the
  object's MD5. Downloads stream the stored bytes undecoded and stop at
  ``MAX_BYTES``, so a gzip-encoded upload cannot expand in memory.
* **Lifecycle backstop.** Every object starts with ``customTime`` = creation time.
  The bucket rule ``Delete if daysSinceCustomTime >= BACKSTOP_DAYS`` removes
  anything the app's 24 h sweeper missed. Saving a preview first moves its
  ``customTime`` to ``RETAINED_CUSTOM_TIME`` (GCS only lets it move later),
  so the rule never matches saved media. Only an explicit delete removes saved
  media.
* **Purge** is a JSON API delete. It is only a purge on a bucket with soft
  delete off, no object versioning, and no retention policy or holds.
  ``bucket_findings`` checks those, plus uniform access, public access
  prevention, the backstop rule and a CORS ``PUT`` entry that allows every
  signed upload header. Strict modes refuse to start against a bucket with
  findings. An unexpired upload URL can recreate a deleted input, so
  ``replay_window`` tells the media service to repeat a purge made inside it.

``STORAGE_EMULATOR_HOST`` selects a local emulator (fake-gcs-server). There a
throwaway RSA key signs the URLs, and the emulator enforces none of the signed
constraints: emulator runs prove the object flow, not GCS enforcement.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Tuple
from urllib.parse import quote, urlsplit

from brandme_core.domains.base import DomainError

from .store import MAX_BYTES

ALGORITHM = "GOOG4-RSA-SHA256"
GCS_HOST = "storage.googleapis.com"
MAX_SIGNED_SECONDS = 604800  # GCS limit for V4 signatures
UPLOAD_URL_MAX = timedelta(minutes=15)
# A deleted object can be recreated through its unexpired upload URL (create-only succeeds again once the
# object is gone), so a purge inside this window is repeated after it. One minute covers clock skew.
REPLAY_WINDOW = UPLOAD_URL_MAX + timedelta(minutes=1)
UPLOAD_HEADERS = ("Content-Type", "x-goog-content-length-range", "x-goog-if-generation-match", "x-goog-custom-time")
SCOPES = ("https://www.googleapis.com/auth/devstorage.read_write", "https://www.googleapis.com/auth/iam")  # objects + signBlob
BACKSTOP_DAYS = 2  # past the 24 h app retention, plus lifecycle's asynchronous lag
RETAINED_CUSTOM_TIME = "9999-12-31T00:00:00Z"
LIFECYCLE_RULE = {"action": {"type": "Delete"}, "condition": {"daysSinceCustomTime": BACKSTOP_DAYS}}
TIMEOUT = (5, 30)


class StorageUnavailable(DomainError):
    status, code, retryable = 503, "storage_unavailable", True


class Signer(Protocol):
    email: str

    def sign(self, message: bytes) -> bytes: ...


# --------------------------------------------------------------------- V4 signing


@dataclass(frozen=True)
class SignedRequest:
    url: str
    canonical_request: str
    string_to_sign: str


def _enc(value: str, safe: str = "") -> str:
    return quote(value, safe="-_.~" + safe)


def sign_v4(*, method: str, bucket: str, obj: Optional[str], timestamp: datetime, expires: int, email: str,
            sign: Callable[[bytes], bytes], host: str = GCS_HOST, scheme: str = "https",
            headers: Optional[Mapping[str, str]] = None, query: Optional[Mapping[str, str]] = None) -> SignedRequest:
    """Path-style V4 signed URL, following GCS's signing spec (checked against
    Google's conformance vectors in tests/test_media_gcs_signing.py)."""
    if not 1 <= expires <= MAX_SIGNED_SECONDS:
        raise ValueError("signed URL expiry must be 1..604800 seconds")
    stamp = timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scope = f"{stamp[:8]}/auto/storage/goog4_request"
    canon = {"host": host}
    for k, v in (headers or {}).items():
        canon[k.strip().lower()] = " ".join(str(v).split())
    signed = ";".join(sorted(canon))
    params = {"X-Goog-Algorithm": ALGORITHM, "X-Goog-Credential": f"{email}/{scope}", "X-Goog-Date": stamp,
              "X-Goog-Expires": str(expires), "X-Goog-SignedHeaders": signed, **(query or {})}
    canonical_query = "&".join(f"{_enc(k)}={_enc(v)}" for k, v in sorted(params.items()))
    path = f"/{bucket}" + (f"/{_enc(obj, '/')}" if obj else "")
    payload = canon.get("x-goog-content-sha256", "UNSIGNED-PAYLOAD")
    canonical_request = "\n".join(
        (method, path, canonical_query, "".join(f"{k}:{canon[k]}\n" for k in sorted(canon)), signed, payload))
    string_to_sign = "\n".join((ALGORITHM, stamp, scope, hashlib.sha256(canonical_request.encode()).hexdigest()))
    signature = sign(string_to_sign.encode()).hex()
    return SignedRequest(f"{scheme}://{host}{path}?{canonical_query}&X-Goog-Signature={signature}", canonical_request, string_to_sign)


class KeySigner:
    """RSA-SHA256 (PKCS#1 v1.5) with a local key: emulator runs and tests only."""

    def __init__(self, email: str, private_key: Any):
        self.email = email
        self._key = private_key

    @classmethod
    def ephemeral(cls, email: str = "emulator@brandme-dev.invalid") -> "KeySigner":
        from cryptography.hazmat.primitives.asymmetric import rsa

        return cls(email, rsa.generate_private_key(public_exponent=65537, key_size=2048))

    def public_key(self) -> Any:
        return self._key.public_key()

    def sign(self, message: bytes) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        return self._key.sign(message, padding.PKCS1v15(), hashes.SHA256())


class GoogleAuthSigner:
    """Signs with the runtime identity. A key file signs locally; impersonated
    credentials and workload identity sign through IAM ``signBlob``, which needs
    ``iam.serviceAccounts.signBlob`` on that service account. User credentials
    have no service-account identity and are refused."""

    def __init__(self, credentials: Any):
        from google.auth import iam
        from google.auth.transport.requests import Request

        if getattr(credentials, "service_account_email", None) in (None, "default"):
            credentials.refresh(Request())
        self.email = getattr(credentials, "service_account_email", None)
        if not self.email or self.email == "default":
            raise ValueError("signed upload URLs need a service-account identity")
        # Key files and impersonated credentials implement sign_bytes; GCE/GKE metadata credentials do not.
        self._sign = credentials.sign_bytes if hasattr(credentials, "sign_bytes") else iam.Signer(Request(), credentials, self.email).sign

    def sign(self, message: bytes) -> bytes:
        return self._sign(message)


# --------------------------------------------------------------------- bucket policy


def bucket_findings(meta: Mapping[str, Any]) -> List[str]:
    """What stops this bucket from holding private media that a delete truly
    removes. An empty list means fit for use."""
    found = []
    iam_cfg = meta.get("iamConfiguration") or {}
    if not (iam_cfg.get("uniformBucketLevelAccess") or {}).get("enabled"):
        found.append("uniform_bucket_level_access_disabled")
    if iam_cfg.get("publicAccessPrevention") != "enforced":
        found.append("public_access_prevention_not_enforced")
    if (meta.get("versioning") or {}).get("enabled"):
        found.append("object_versioning_enabled")  # noncurrent versions survive a delete
    soft = meta.get("softDeletePolicy")
    if soft is None or str(soft.get("retentionDurationSeconds", "")) != "0":
        found.append("soft_delete_not_disabled")  # soft-deleted objects stay restorable
    if meta.get("retentionPolicy"):
        found.append("retention_policy_blocks_deletion")
    if meta.get("defaultEventBasedHold"):
        found.append("event_based_hold_blocks_deletion")
    rules = (meta.get("lifecycle") or {}).get("rule") or []
    deletes = [r for r in rules if (r.get("action") or {}).get("type") == "Delete"]
    if not any((r.get("condition") or {}) == LIFECYCLE_RULE["condition"] for r in deletes):
        found.append("custom_time_backstop_missing")
    if any(set(r.get("condition") or {}) != {"daysSinceCustomTime"} for r in deletes):
        found.append("lifecycle_rule_may_delete_saved_media")
    puts = [c for c in meta.get("cors") or [] if "PUT" in (c.get("method") or [])]
    if not puts:
        found.append("cors_put_missing")
    elif not any({h.lower() for h in UPLOAD_HEADERS} <= {h.lower() for h in c.get("responseHeader") or []} for c in puts):
        found.append("cors_upload_headers_missing")  # the browser preflight for the signed PUT would fail
    return found


# --------------------------------------------------------------------- store


def _rfc3339(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


class GcsMediaStore:
    """``MediaStore`` on a private GCS bucket (or the local emulator)."""

    name = "gcs"
    simulated = False
    replay_window = REPLAY_WINDOW

    def __init__(self, bucket: str, *, session: Any, signer: Signer, api_endpoint: Optional[str] = None,
                 emulator: bool = False, clock: Optional[Callable[[], datetime]] = None):
        if not bucket or "/" in bucket:
            raise ValueError("a bucket name is required")
        self.bucket = bucket
        self.session = session
        self.signer = signer
        self.emulator = emulator
        self._api = (api_endpoint or f"https://{GCS_HOST}").rstrip("/")
        parts = urlsplit(self._api)
        self._scheme, self._host = parts.scheme, parts.netloc
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # -- HTTP

    def _object_url(self, ref: str) -> str:
        return f"{self._api}/storage/v1/b/{self.bucket}/o/{_enc(ref)}"

    def _call(self, method: str, url: str, *, ok: Tuple[int, ...] = (200,), missing_ok: bool = False, **kw: Any) -> Any:
        try:
            resp = self.session.request(method, url, timeout=TIMEOUT, **kw)
        except Exception as exc:  # noqa: BLE001 - connection or auth failure
            raise StorageUnavailable("media storage is unavailable") from exc
        if resp.status_code == 404 and missing_ok:
            resp.close()
            return None
        if resp.status_code not in ok:
            resp.close()
            raise StorageUnavailable(f"media storage refused {method} ({resp.status_code})")
        return resp

    def _meta(self, ref: str) -> Optional[Dict[str, Any]]:
        resp = self._call("GET", self._object_url(ref), missing_ok=True)
        return None if resp is None else resp.json()

    def _download(self, ref: str, generation: Optional[str] = None) -> Optional[bytes]:
        """The stored bytes, at most MAX_BYTES. A client can add an unsigned
        ``Content-Encoding`` to its upload. Asking for gzip stops GCS from
        transcoding, and nothing here decodes, so a compressed upload is read
        as its own small bytes and then fails the magic-byte check."""
        params = {"alt": "media", **({"ifGenerationMatch": generation} if generation else {})}
        resp = self._call("GET", self._object_url(ref), params=params, missing_ok=True, stream=True, headers={"Accept-Encoding": "gzip"})
        if resp is None:
            return None
        chunks, total = [], 0
        try:
            while chunk := resp.raw.read(1 << 16, decode_content=False):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise StorageUnavailable("media object exceeds the store's size limit")
                chunks.append(chunk)
        finally:
            resp.close()
        return b"".join(chunks)

    # -- MediaStore

    def upload_target(self, ref: str, *, content_type: str, max_bytes: int, expires_at: datetime) -> Dict[str, object]:
        now = self._clock()
        until = min(expires_at, now + UPLOAD_URL_MAX)
        seconds = int((until - now).total_seconds())
        if seconds < 1:
            raise ValueError("upload window already closed")
        headers = dict(zip(UPLOAD_HEADERS, (content_type, f"0,{max_bytes}", "0", _rfc3339(now))))
        signed = sign_v4(method="PUT", bucket=self.bucket, obj=ref, timestamp=now, expires=seconds, email=self.signer.email,
                         sign=self.signer.sign, host=self._host, scheme=self._scheme, headers=headers)
        return {"method": "PUT", "url": signed.url, "headers": headers, "max_bytes": max_bytes,
                "expires_at": now + timedelta(seconds=seconds), "simulated": False}

    def stat(self, ref: str) -> Optional[Tuple[int, str]]:
        meta = self._meta(ref)
        if meta is None:
            return None
        size = int(meta["size"])
        if size > MAX_BYTES:
            return size, ""  # rejected as too large without downloading it
        data = self._download(ref, str(meta["generation"]))
        if data is None:
            return None
        if meta.get("md5Hash") and base64.b64encode(hashlib.md5(data).digest()).decode() != meta["md5Hash"]:  # noqa: S324 - GCS integrity field
            raise StorageUnavailable("media storage returned bytes that do not match the object's MD5")
        return len(data), hashlib.sha256(data).hexdigest()

    def read(self, ref: str) -> bytes:
        data = self._download(ref)
        if data is None:
            raise KeyError(ref)
        return data

    def write(self, ref: str, data: bytes, content_type: str) -> None:
        if len(data) > MAX_BYTES:
            raise ValueError("media object exceeds the store's size limit")
        boundary = uuid.uuid4().hex
        meta = json.dumps({"name": ref, "contentType": content_type, "customTime": _rfc3339(self._clock())}).encode()
        body = b"".join((f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(), meta,
                         f"\r\n--{boundary}\r\nContent-Type: {content_type}\r\n\r\n".encode(), data, f"\r\n--{boundary}--\r\n".encode()))
        self._call("POST", f"{self._api}/upload/storage/v1/b/{self.bucket}/o", params={"uploadType": "multipart"}, data=body,
                   headers={"Content-Type": f"multipart/related; boundary={boundary}"})

    def retain(self, ref: str) -> None:
        """Take a saved object out of the lifecycle backstop."""
        if self._call("PATCH", self._object_url(ref), json={"customTime": RETAINED_CUSTOM_TIME}, missing_ok=True) is None:
            raise KeyError(ref)

    def delete(self, ref: str) -> bool:
        return self._call("DELETE", self._object_url(ref), ok=(200, 204), missing_ok=True) is not None

    # -- bucket

    def bucket_metadata(self) -> Dict[str, Any]:
        return self._call("GET", f"{self._api}/storage/v1/b/{self.bucket}").json()

    def check_bucket(self) -> List[str]:
        return bucket_findings(self.bucket_metadata())


def from_environment(env: Mapping[str, str]) -> Optional[GcsMediaStore]:
    """``BRANDME_MEDIA_BUCKET`` selects GCS. ``STORAGE_EMULATOR_HOST`` (allowed in
    demo/development only) selects the local emulator. Otherwise Application
    Default Credentials are used, and strict modes require a bucket with no
    findings. Returns None when no bucket is configured."""
    bucket = env.get("BRANDME_MEDIA_BUCKET", "").strip()
    if not bucket:
        return None
    strict = env.get("ENVIRONMENT") in ("sandbox", "production")
    emulator = env.get("STORAGE_EMULATOR_HOST", "").strip()
    if emulator:
        if strict:
            raise ValueError("the storage emulator is refused in sandbox/production")
        import requests

        return GcsMediaStore(bucket, session=requests.Session(), signer=KeySigner.ephemeral(),
                             api_endpoint=emulator if "://" in emulator else f"http://{emulator}", emulator=True)
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=list(SCOPES))
    store = GcsMediaStore(bucket, session=AuthorizedSession(credentials), signer=GoogleAuthSigner(credentials))
    if strict and store.check_bucket():
        raise ValueError("the media bucket is not fit for private, deletable media")
    return store
