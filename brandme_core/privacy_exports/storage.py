"""Bounded GCS JSON API adapter. Never mint public or signed download URLs."""
from __future__ import annotations

import ipaddress
import json
import re
import time
from urllib.parse import quote, urlsplit
from uuid import uuid4

import requests

MAX_PACKAGE = 2 * 1024 * 1024


class StorageError(Exception):
    def __init__(self):
        super().__init__("export_storage_unavailable")


class CredentialSession(requests.Session):
    """ADC refresh has a separate transport; harden it as well as object I/O."""
    def __init__(self):
        super().__init__()
        self.trust_env = False

    def request(self, *args, **kwargs):
        kwargs["allow_redirects"] = False
        return super().request(*args, **kwargs)


class PrivateStore:
    def __init__(self, config):
        self.config = config
        self.auth_session = None
        self.emulated = bool(config.storage_emulator)
        if self.emulated:
            p = urlsplit("http://" + config.storage_emulator)
            local = p.hostname in {"localhost", "storage-emulator"}
            try:
                local = local or ipaddress.ip_address(p.hostname).is_loopback
            except ValueError:
                pass
            if (config.environment not in {"demo", "development"} or not local or not p.port
                    or p.username or p.password or p.path or p.query or p.fragment):
                raise ValueError("local storage emulator required")
            self.base = "http://" + config.storage_emulator
            self.session = requests.Session()
        else:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession, Request
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/devstorage.read_write"])
            self.auth_session = CredentialSession()
            self.session = AuthorizedSession(credentials, auth_request=Request(self.auth_session),
                                             refresh_timeout=5, max_refresh_attempts=0)
            self.base = "https://storage.googleapis.com"
        self.session.trust_env = False
        self.bucket_path = f"/storage/v1/b/{config.bucket}"

    def request(self, method, path, *, params=None, data=None, headers=None, limit=16384, absent=False):
        deadline = time.monotonic() + 8
        try:
            extra = {} if self.emulated else {"max_allowed_time": 8}
            with self.session.request(method, self.base + path, params=params, data=data, headers=headers,
                                      timeout=5, allow_redirects=False, stream=True, **extra) as response:
                if absent and response.status_code == 404:
                    return None
                if not 200 <= response.status_code < 300:
                    raise StorageError()
                length = response.headers.get("Content-Length")
                if length and int(length) > limit:
                    raise StorageError()
                out = bytearray()
                # read1 returns currently available bytes; a trickled response
                # cannot reset our absolute deadline until a large chunk fills.
                while True:
                    chunk = response.raw.read1(16384, decode_content=True)
                    if time.monotonic() >= deadline:
                        raise StorageError()
                    if not chunk:
                        return bytes(out)
                    out.extend(chunk)
                    if len(out) > limit:
                        raise StorageError()
        except Exception:
            raise StorageError() from None

    def metadata(self, path, **kwargs):
        data = self.request("GET", path, **kwargs)
        if data is None:
            return None
        try:
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except Exception:
            raise StorageError() from None

    def check(self):
        b = self.metadata(self.bucket_path)
        iam = b.get("iamConfiguration", {})
        rules = b.get("lifecycle", {}).get("rule", [])
        # Require an unconditional age-only deletion rule. Additional narrower
        # rules must not be mistaken for a cleanup guarantee for every object.
        lifecycle = any(r == {"action": {"type": "Delete"}, "condition": {"age": 1}} for r in rules)
        if (b.get("name") != self.config.bucket or iam.get("publicAccessPrevention") != "enforced"
                or iam.get("uniformBucketLevelAccess", {}).get("enabled") is not True
                or b.get("versioning", {}).get("enabled", False) is not False
                or str(b.get("softDeletePolicy", {}).get("retentionDurationSeconds", "")) != "0"
                or b.get("retentionPolicy") or b.get("defaultEventBasedHold")
                or b.get("objectRetention", {}).get("mode") == "Enabled" or not lifecycle):
            raise StorageError()

    def key(self, job_id, attempt_id):
        for value in (job_id, attempt_id):
            if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
                raise StorageError()
        return f"exports/{self.config.environment}/{job_id}/{attempt_id}.json"

    def path(self, key):
        if not re.fullmatch(r"exports/" + re.escape(self.config.environment) +
                            r"/[0-9a-f-]{36}/[0-9a-f-]{36}\.json", key):
            raise StorageError()
        return self.bucket_path + "/o/" + quote(key, safe="")

    @staticmethod
    def generation(value):
        if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,31}", value):
            raise StorageError()
        return value

    def put(self, key, content):
        self.path(key)
        if not isinstance(content, bytes) or not 0 < len(content) <= MAX_PACKAGE:
            raise StorageError()
        boundary = "export_" + uuid4().hex
        metadata = json.dumps({"name": key, "contentType": "application/json", "cacheControl": "private, no-store"}).encode()
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + metadata +
                f"\r\n--{boundary}\r\nContent-Type: application/json\r\n\r\n".encode() + content + f"\r\n--{boundary}--\r\n".encode())
        data = self.request("POST", "/upload" + self.bucket_path + "/o", data=body,
                            params={"uploadType": "multipart", "ifGenerationMatch": "0"},
                            headers={"Content-Type": f"multipart/related; boundary={boundary}"})
        try:
            info = json.loads(data)
            if info.get("name") != key or str(info.get("size")) != str(len(content)):
                raise StorageError()
            return self.generation(info.get("generation"))
        except Exception:
            raise StorageError() from None

    def get(self, key, generation):
        return self.request("GET", self.path(key), params={"alt": "media", "generation": self.generation(generation)}, limit=MAX_PACKAGE)

    def delete(self, key):
        info = self.metadata(self.path(key), absent=True)
        if info is not None:
            generation = self.generation(info.get("generation"))
            self.request("DELETE", self.path(key), params={"ifGenerationMatch": generation}, absent=True)

    def close(self):
        self.session.close()
        if self.auth_session is not None:
            self.auth_session.close()
