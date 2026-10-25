#!/usr/bin/env python3
"""Fetch Google's pinned Cloud Firestore emulator component and verify its published SHA256.

Version 1.22.0 (gcloud rapid channel components-2.json, checked 2026-10-23).
Requires Java 11+ to run. Prints the launcher path.
"""
from pathlib import Path
import sys
import tarfile
import tempfile

from _fetch import download_verified

URL = "https://dl.google.com/dl/cloudsdk/channels/rapid/components/google-cloud-sdk-cloud-firestore-emulator-20260717053915.tar.gz"
SHA256 = "e962450b637827664094959571fd92c3680de863936bd481bd0a050f76ca91ba"


def main():
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/firestore-emulator").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "firestore.tar.gz"
        download_verified(URL, SHA256, archive, timeout=60, label="Firestore emulator")
        with tarfile.open(archive) as package:
            package.extractall(destination, filter="data")
    print(destination / "platform/cloud-firestore-emulator/cloud_firestore_emulator")


if __name__ == "__main__":
    main()
