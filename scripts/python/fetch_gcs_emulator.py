#!/usr/bin/env python3
"""Fetch the pinned fake-gcs-server release (local GCS emulator) and verify its SHA256.

The SHA256 is the one published in the release's checksums.txt. Tests start the
binary themselves from GCS_EMULATOR_BIN (tests/test_media_gcs_store.py). A stamped
earlier extract of the same pin is reused without downloading (_fetch.cached).
"""
from pathlib import Path
import platform
import sys
import tarfile
import tempfile

from _fetch import cached, download_verified, forget, mark_verified

VERSION = "1.56.1"
ARCHIVES = {
    ("Linux", "x86_64"): ("Linux_amd64", "0f2f9f6884417acd5cc27126a9aa237ccc627372a4aa5008b399641de6db9469"),
    ("Linux", "aarch64"): ("Linux_arm64", "89a4b887a50834ce5844f47f9938a1203a89330e660b2af7851b858fa489fa96"),
    ("Darwin", "x86_64"): ("Darwin_amd64", "bbcbb78e57c4a7ad242bc971b70a57f963c8daa616ae649254562fbd7f2bc54d"),
    ("Darwin", "arm64"): ("Darwin_arm64", "039d7a520869115b9bc1b354f73612d2dad0aa27b22104f111d8c94985007fe1"),
}


def main():
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/gcs-emulator").resolve()
    target, sha256 = ARCHIVES[(platform.system(), platform.machine())]
    binary = destination / "fake-gcs-server"
    if cached(binary, sha256):
        print(binary)
        return
    destination.mkdir(parents=True, exist_ok=True)
    forget(binary)
    url = f"https://github.com/fsouza/fake-gcs-server/releases/download/v{VERSION}/fake-gcs-server_{VERSION}_{target}.tar.gz"
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "fake-gcs-server.tar.gz"
        download_verified(url, sha256, archive, timeout=60, label="fake-gcs-server")
        with tarfile.open(archive) as package:
            package.extract("fake-gcs-server", destination, filter="data")
    binary.chmod(0o755)
    mark_verified(binary, sha256)
    print(binary)


if __name__ == "__main__":
    main()
