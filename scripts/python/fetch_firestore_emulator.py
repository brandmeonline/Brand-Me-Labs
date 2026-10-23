#!/usr/bin/env python3
"""Fetch Google's pinned Cloud Firestore emulator component and verify its published SHA256.

Version 1.22.0 (gcloud rapid channel components-2.json, checked 2026-10-23).
Requires Java 11+ to run. Prints the launcher path.
"""
import hashlib
from pathlib import Path
import sys
import tarfile
import tempfile
import urllib.request

URL = "https://dl.google.com/dl/cloudsdk/channels/rapid/components/google-cloud-sdk-cloud-firestore-emulator-20260717053915.tar.gz"
SHA256 = "e962450b637827664094959571fd92c3680de863936bd481bd0a050f76ca91ba"


def main():
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/firestore-emulator").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "firestore.tar.gz"
        digest = hashlib.sha256()
        with urllib.request.urlopen(URL, timeout=60) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != SHA256:
            raise RuntimeError("Firestore emulator archive checksum mismatch")
        with tarfile.open(archive) as package:
            package.extractall(destination, filter="data")
    print(destination / "platform/cloud-firestore-emulator/cloud_firestore_emulator")


if __name__ == "__main__":
    main()
