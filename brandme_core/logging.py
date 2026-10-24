# Brand.Me — structured logging with redaction
# brandme_core/logging.py
"""
Structured JSON logs with secret redaction and identifier pseudonymization.

This ports the gateway's ``REDACT_PATHS`` semantics
(brandme-gateway/src/config/logger.ts) to Python, without path lists: every
key at every depth of a log record is checked (spec ch.03 §8/§9, W02
"redacted logs").

Key matching
    A key is normalized to lowercase ASCII letters and digits
    (``"X-Api-Key"`` -> ``"xapikey"``, ``"scanner_user_id"`` ->
    ``"scanneruserid"``). A key whose normalized form *contains* one of the
    stems below matches.

Secrets -> ``"[REDACTED]"`` (the whole value, whatever its type)
    token, secret, password, passwd, authorization, cookie, apikey,
    credential, privatekey, seed, mnemonic, wallet, accesskey, signingkey,
    plus the legacy exact keys in ``LEGACY_SENSITIVE_KEYS``.

Personal identifiers -> stable pseudonym ``"h:" + 12 hex``
    email, phone, userid, memberid, subjectref, owner, scanneruserid,
    garmenttag, viewerid, actorref, and IP addresses. ``ip`` is matched as a
    whole word of the key (``ip``, ``client_ip``, ``clientIp``, ``ip_address``,
    ``x-real-ip``, ``x-forwarded-for``, ``remote_addr``) so ``zip`` or
    ``recipient`` do not match. Scalars under a matching key are pseudonymized;
    dicts and lists under it are walked and every scalar leaf is pseudonymized.
    ``None``, booleans and empty strings are kept so log shape stays readable.

Pseudonyms
    ``h:`` + the first 12 hex characters of HMAC-SHA256(salt, value). The
    salt is ``BRANDME_LOG_PSEUDONYM_KEY`` when it is set to at least 16
    characters (one deployment then correlates the same member across
    processes); otherwise a random per-process salt is drawn at import, so
    pseudonyms correlate only within one process lifetime. Treat a configured
    salt as a secret: anyone holding it can test a guessed identifier. A value
    that is already a pseudonym is left unchanged, so double redaction (for
    example ``redact_user_id`` output under an ``owner`` key) is stable.

Records are copied, never mutated: callers' dicts, lists and tuples are left as
they were. Nesting deeper than ``MAX_DEPTH`` is replaced by ``"[TRUNCATED]"`` and a
container that contains itself (a cycle) by ``"[CYCLE]"``.
Values that JSON cannot encode are logged with ``str()``.

Free text is not parsed: an identifier interpolated into a message string or an
``error`` value is not detected. Log identifiers as their own keys.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import traceback
import uuid
from typing import Any, Dict, Mapping, Optional

REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"
CYCLE = "[CYCLE]"
MAX_DEPTH = 32
SALT_ENV = "BRANDME_LOG_PSEUDONYM_KEY"

SECRET_STEMS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "authorization",
    "cookie",
    "apikey",
    "credential",
    "privatekey",
    "seed",
    "mnemonic",
    "wallet",
    "accesskey",
    "signingkey",
)

IDENTIFIER_STEMS: tuple[str, ...] = (
    "email",
    "phone",
    "userid",
    "memberid",
    "subjectref",
    "owner",
    "scanneruserid",
    "garmenttag",
    "viewerid",
    "actorref",
)

# Whole-word key tokens and whole normalized keys that name an IP address.
_IP_TOKENS = frozenset({"ip", "ipaddr", "ipaddress", "ipv4", "ipv6"})
_IP_KEYS = frozenset({"remoteaddr", "xforwardedfor", "forwardedfor", "xrealip", "clientaddr"})

# Exact keys redacted by the previous implementation; kept for its callers.
LEGACY_SENSITIVE_KEYS = frozenset({
    "wallet_key",
    "purchase_history",
    "ownership_lineage",
    "private_payload",
    "did_secret",
    "wallet_keys",
    "midnight_private_payload",
})
# Backwards-compatible name.
SENSITIVE_KEYS = LEGACY_SENSITIVE_KEYS
_LEGACY_NORMALIZED = frozenset(re.sub(r"[^a-z0-9]", "", k) for k in LEGACY_SENSITIVE_KEYS)

_PSEUDONYM_RE = re.compile(r"h:[0-9a-f]{12}")
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


def _load_salt() -> bytes:
    configured = os.environ.get(SALT_ENV, "")
    if len(configured) >= 16:
        return configured.encode("utf-8")
    return secrets.token_bytes(32)


_SALT = _load_salt()


def normalize_key(key: Any) -> str:
    """Lowercase alphanumerics only: ``"X-Api-Key"`` -> ``"xapikey"``."""
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _key_words(key: str) -> list[str]:
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", spaced)
    return [w for w in re.split(r"[^a-z0-9]+", spaced.lower()) if w]


def classify_key(key: Any) -> Optional[str]:
    """Return ``"secret"``, ``"identifier"`` or ``None`` for a log key."""
    text = str(key)
    norm = normalize_key(text)
    if not norm:
        return None
    if norm in _LEGACY_NORMALIZED or any(stem in norm for stem in SECRET_STEMS):
        return "secret"
    if any(stem in norm for stem in IDENTIFIER_STEMS):
        return "identifier"
    if norm in _IP_KEYS or any(word in _IP_TOKENS for word in _key_words(text)):
        return "identifier"
    return None


def pseudonymize(value: Any) -> Any:
    """Stable, non-reversible stand-in for an identifier (see module docstring)."""
    if value is None or isinstance(value, bool):
        return value
    text = str(value)
    if text == "" or text == REDACTED or _PSEUDONYM_RE.fullmatch(text):
        return value
    digest = hmac.new(_SALT, text.encode("utf-8", "surrogatepass"), hashlib.sha256).hexdigest()
    return "h:" + digest[:12]


def _walk(value: Any, depth: int, identifier: bool, path: frozenset = frozenset()) -> Any:
    if depth > MAX_DEPTH:
        return TRUNCATED
    if isinstance(value, (Mapping, list, tuple, set, frozenset)):
        # A container already on the current path is a cycle; without this a
        # payload with two back-references makes 2**MAX_DEPTH calls.
        if id(value) in path:
            return CYCLE
        path = path | {id(value)}
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            kind = classify_key(key)
            if kind == "secret":
                out[key] = REDACTED
            else:
                out[key] = _walk(item, depth + 1, identifier or kind == "identifier", path)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_walk(item, depth + 1, identifier, path) for item in value]
        return tuple(items) if isinstance(value, tuple) else items
    if identifier:
        return pseudonymize(value)
    return value


def redact(data: Any) -> Any:
    """Return a redacted copy of ``data``; the argument is never modified."""
    return _walk(data, 0, False)


class StructuredLogger:
    """Logger that emits one redacted JSON object per record.

    Each method accepts a dict, a message string, or both, plus keyword
    fields: ``logger.info({"event": "x", "user_id": u})``,
    ``logger.info("cube_started", port=8007)`` and
    ``logger.info("msg", extra={"task_id": t})`` all work.
    """

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(logging.DEBUG)

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            formatter = StructuredFormatter()
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _scrub(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redacted copy of ``data`` (kept for existing callers)."""
        return redact(data)

    def _record(self, data: Any, fields: Dict[str, Any]) -> Dict[str, Any]:
        record: Dict[str, Any] = {"service": self.service_name}
        if isinstance(data, Mapping):
            record.update(data)
        elif data is not None:
            record["message"] = str(data)
        extra = fields.pop("extra", None)
        if isinstance(extra, Mapping):
            record.update(extra)
        record.update(fields)
        return record

    def _emit(self, level: int, data: Any, fields: Dict[str, Any], exc_info: Any = None) -> None:
        if not self.logger.isEnabledFor(level):
            return
        exc_info = fields.pop("exc_info", exc_info)
        fields.pop("stack_info", None)
        if exc_info is True:
            exc_info = sys.exc_info()[1]
        elif isinstance(exc_info, tuple):
            exc_info = exc_info[1] if len(exc_info) > 1 else None
        record = self._record(data, fields)
        if isinstance(exc_info, BaseException):
            # Type and frame locations only: exception messages and source
            # lines can carry identifiers.
            record["exc_type"] = type(exc_info).__name__
            record["exc_frames"] = [
                f"{frame.filename}:{frame.lineno} in {frame.name}"
                for frame in traceback.extract_tb(exc_info.__traceback__)[-10:]
            ]
        try:
            line = json.dumps(redact(record), default=str, skipkeys=True)
        except (TypeError, ValueError):
            line = json.dumps({"service": self.service_name, "event": "log_record_unserializable"})
        self.logger.log(level, line)

    def debug(self, data: Any = None, /, **fields: Any) -> None:
        self._emit(logging.DEBUG, data, fields)

    def info(self, data: Any = None, /, **fields: Any) -> None:
        self._emit(logging.INFO, data, fields)

    def warning(self, data: Any = None, /, **fields: Any) -> None:
        self._emit(logging.WARNING, data, fields)

    warn = warning

    def error(self, data: Any = None, /, **fields: Any) -> None:
        self._emit(logging.ERROR, data, fields)

    def exception(self, data: Any = None, /, **fields: Any) -> None:
        """ERROR record with the active exception's type and frame locations."""
        self._emit(logging.ERROR, data, fields, True)

    def critical(self, data: Any = None, /, **fields: Any) -> None:
        self._emit(logging.CRITICAL, data, fields)

    fatal = critical


class StructuredFormatter(logging.Formatter):
    """Emit the already-redacted JSON message as is."""

    def format(self, record: logging.LogRecord) -> str:
        # TODO: forward to centralized logging / OTel
        return record.getMessage()


def get_logger(service_name: str) -> StructuredLogger:
    """Returns a structured logger for the given service."""
    return StructuredLogger(service_name)


def redact_user_id(user_id: Optional[str]) -> str:
    """Pseudonymize a user identifier for logs (``"unknown"`` when empty).

    Previously returned the first 8 characters, which logged short IDs in
    full; it now returns the same stable pseudonym the logger applies.
    """
    if not user_id:
        return "unknown"
    return pseudonymize(user_id)


def truncate_id(value: str) -> str:
    """Truncate a non-personal ID (asset, cube, transfer) to 8 chars + ellipsis.

    Use ``redact_user_id`` for anything that identifies a person.
    """
    if not value:
        return "unknown"
    if len(value) <= 8:
        return value + "…"
    return value[:8] + "…"


def ensure_request_id(request, response=None) -> str:
    """Return a safe request ID and echo it on ``response`` when given.

    An inbound ``X-Request-Id`` is reused only if it is 1-128 characters of
    ``[A-Za-z0-9._:-]`` starting with an alphanumeric; anything else is
    replaced with a new UUID so a client cannot inject text into logs. The ID
    is kept on ``request.state`` so every call for one request returns the same
    value (a generated ID otherwise differed between middleware and handler).
    """
    state = getattr(request, "state", None)
    request_id = getattr(state, "request_id", None) if state is not None else None
    if not (isinstance(request_id, str) and _REQUEST_ID_RE.fullmatch(request_id)):
        request_id = request.headers.get("X-Request-Id") or ""
        if not _REQUEST_ID_RE.fullmatch(request_id):
            request_id = str(uuid.uuid4())
        if state is not None:
            try:
                state.request_id = request_id
            except AttributeError:
                pass
    if response is not None:
        response.headers["X-Request-Id"] = request_id
    return request_id
