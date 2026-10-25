"""Keyed references for audit records and run logs (ch.03 §11; no raw ids in logs).

A ref is ``HMAC-SHA256(key, kind NUL value)`` cut to 16 hex characters. Records about the same
task or member join across the audit log and the assistant run log, and a short value (a
two-word catalog query, a member id) cannot be recovered by hashing guesses without the key.
``kind`` separates domains: a task ref never equals a member ref for the same string.

* The key is random per process unless ``configure_from_env`` installs ``BRANDME_LOG_REF_KEY``
  (base64url, at least 32 bytes, from the platform secret store) at startup; refs written by
  different processes then join.
* Nothing here reads the environment at import, and the key is never logged.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import threading
from typing import Any, Mapping, Optional

KEY_ENV = "BRANDME_LOG_REF_KEY"
MIN_KEY_BYTES = 32
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")

_lock = threading.Lock()
_key = secrets.token_bytes(32)
_configured: Optional[bytes] = None
_used = False


class LogRefKeyError(ValueError):
    """``code`` is ``log_ref_key_invalid`` or ``log_ref_key_already_in_use``; never the key."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def configure_from_env(env: Mapping[str, str]) -> None:
    """Install ``BRANDME_LOG_REF_KEY`` if set. Unset keeps the per-process random key.

    Idempotent for the same key. A different key after one was configured, or after any ref was
    already written with the random key, raises ``log_ref_key_already_in_use``: refs from before
    and after would silently stop joining."""
    global _key, _configured
    raw = env.get(KEY_ENV)
    if not raw:
        return
    if not _B64URL_RE.match(raw):
        raise LogRefKeyError("log_ref_key_invalid")
    body = raw.rstrip("=")
    try:
        key = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except (binascii.Error, ValueError):
        raise LogRefKeyError("log_ref_key_invalid") from None
    if len(key) < MIN_KEY_BYTES:
        raise LogRefKeyError("log_ref_key_invalid")
    with _lock:
        if _configured is not None and hmac.compare_digest(_configured, key):
            return
        if _configured is not None or _used:
            raise LogRefKeyError("log_ref_key_already_in_use")
        _key, _configured = key, key


def log_ref(kind: str, value: Any) -> str:
    global _used
    data = value if isinstance(value, str) else canonical_json(value)
    _used = True
    return hmac.new(_key, f"{kind}\x00{data}".encode(), hashlib.sha256).hexdigest()[:16]
