"""
App-owned media storage interface (ch.03: object storage holds media; signed,
short-lived, constrained upload URLs; never a public photo URL).

Production wires a private object-store adapter (e.g. GCS V4 signed URLs).
None is configured in this repository, so ``MemoryMediaStore`` is the only
implementation here. It is labelled ``simulated`` and exists for tests and
local demos; it is not evidence of production storage or deletion.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Dict, Optional, Protocol, Tuple

ALLOWED_TYPES = {"image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG\r\n\x1a\n",), "image/webp": (b"RIFF",)}
MAX_BYTES = 10 * 1024 * 1024


def storage_ref(member_id: str, media_id: str) -> str:
    """Private object path; contains no file name, EXIF or public token."""
    return f"members/{member_id}/media/{media_id}"


def sniff(data: bytes, content_type: str) -> bool:
    magics = ALLOWED_TYPES.get(content_type, ())
    if content_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return any(data.startswith(m) for m in magics)


class MediaStore(Protocol):
    name: str
    simulated: bool

    def upload_target(self, ref: str, *, content_type: str, max_bytes: int, expires_at: datetime) -> Dict[str, object]: ...
    def stat(self, ref: str) -> Optional[Tuple[int, str]]: ...
    def read(self, ref: str) -> bytes: ...
    def write(self, ref: str, data: bytes, content_type: str) -> None: ...
    def delete(self, ref: str) -> bool: ...


class MemoryMediaStore:
    """In-process store with constrained one-time upload tokens (simulation only)."""

    name = "memory"
    simulated = True

    def __init__(self) -> None:
        self.objects: Dict[str, Tuple[bytes, str]] = {}
        self._tokens: Dict[str, Tuple[str, str, int, datetime]] = {}
        self.deleted: list = []

    def upload_target(self, ref: str, *, content_type: str, max_bytes: int, expires_at: datetime) -> Dict[str, object]:
        token = secrets.token_urlsafe(24)
        self._tokens[token] = (ref, content_type, max_bytes, expires_at)
        return {"method": "PUT", "url": f"memory://upload/{token}", "headers": {"Content-Type": content_type},
                "max_bytes": max_bytes, "expires_at": expires_at, "simulated": True}

    def client_put(self, url: str, data: bytes, content_type: str, *, now: datetime) -> None:
        """What a browser does with the signed URL (test helper)."""
        token = url.rsplit("/", 1)[-1]
        ref, ctype, max_bytes, expires = self._tokens.pop(token)  # one use
        if now >= expires or content_type != ctype or len(data) > max_bytes:
            raise PermissionError("upload URL expired or constraints violated")
        self.objects[ref] = (data, content_type)

    def stat(self, ref: str) -> Optional[Tuple[int, str]]:
        o = self.objects.get(ref)
        return (len(o[0]), hashlib.sha256(o[0]).hexdigest()) if o else None

    def read(self, ref: str) -> bytes:
        return self.objects[ref][0]

    def write(self, ref: str, data: bytes, content_type: str) -> None:
        self.objects[ref] = (data, content_type)

    def delete(self, ref: str) -> bool:
        self.deleted.append(ref)
        return self.objects.pop(ref, None) is not None
