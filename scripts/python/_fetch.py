"""Shared download for the pinned emulator fetchers: retried, then SHA256-verified.

A slow mirror is not a test result: CI once failed before any test ran because one 30 s read
timed out. Each attempt restarts the download; only a complete archive with the pinned digest
is returned. A checksum mismatch is never retried.
"""
import hashlib
import http.client
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ATTEMPTS = 4


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
