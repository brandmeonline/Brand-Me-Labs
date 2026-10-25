"""Shared download for the pinned emulator fetchers: retried, then SHA256-verified, then stamped.

A slow mirror is not a test result: CI once failed before any test ran because one 30 s read
timed out. Each attempt restarts the download; only a complete archive with the pinned digest
is returned. A checksum mismatch is never retried.

Cache hit: after a verified extract, the fetcher writes the pinned SHA256 into a hidden stamp
file next to the binary (``.<binary>.brandme-sha256``). A later call with the same pin and an
executable binary prints the path without downloading (``scripts/brandme.mjs check`` calls the
fetchers on every run). The stamp is removed before any new extract, so an interrupted
extract is never a hit. A changed pin never matches an old stamp. The stamp records what was
verified at download time; it does not re-hash the extracted tree.
"""
import hashlib
import http.client
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ATTEMPTS = 4


def _stamp(binary: Path) -> Path:
    return binary.parent / f".{binary.name}.brandme-sha256"


def cached(binary: Path, sha256: str) -> bool:
    """True when a verified extract of exactly this pinned archive left an executable ``binary``."""
    try:
        return _stamp(binary).read_text().strip() == sha256 and os.access(binary, os.X_OK)
    except OSError:
        return False


def forget(binary: Path) -> None:
    """Drop the stamp before extracting, so a partial extract is never taken for a cache hit."""
    _stamp(binary).unlink(missing_ok=True)


def mark_verified(binary: Path, sha256: str) -> None:
    if not os.access(binary, os.X_OK):
        raise RuntimeError(f"{binary} is missing or not executable after extract")
    _stamp(binary).write_text(sha256 + "\n")


def download_verified(url: str, sha256: str, archive: Path, *, timeout: float, label: str) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response, archive.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
            break
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError) as error:
            if attempt == ATTEMPTS:
                raise
            delay = 2 ** attempt
            # stderr: callers capture stdout for the installed path (ci-cd.yml launcher=$(...)).
            print(f"{label}: download attempt {attempt} failed ({type(error).__name__}); retrying in {delay}s",
                  file=sys.stderr, flush=True)
            time.sleep(delay)
    if digest.hexdigest() != sha256:
        raise RuntimeError(f"{label} archive checksum mismatch")
