#!/usr/bin/env python3
"""Fetch Google's pinned emulator component and verify its published SHA256."""
import hashlib
from pathlib import Path
import sys
import tarfile
import tempfile
import urllib.request

URL = "https://dl.google.com/dl/cloudsdk/channels/rapid/components/google-cloud-sdk-pubsub-emulator-20261009074343.tar.gz"
SHA256 = "28f872a91407ff2a41e29fcf79567f9238322451ad4eb18fa541086ee9982fcf"


def main():
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/pubsub-emulator").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "pubsub.tar.gz"
        digest = hashlib.sha256()
        with urllib.request.urlopen(URL, timeout=30) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != SHA256:
            raise RuntimeError("Pub/Sub emulator archive checksum mismatch")
        with tarfile.open(archive) as package:
            package.extractall(destination, filter="data")
    print(destination / "platform/pubsub-emulator/bin/cloud-pubsub-emulator")


if __name__ == "__main__":
    main()
