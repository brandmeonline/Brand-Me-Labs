#!/usr/bin/env python3
"""Fetch Google's pinned emulator component and verify its published SHA256.

Prints the launcher path; a stamped earlier extract of the same pin is reused without
downloading (_fetch.cached).
"""
from pathlib import Path
import sys
import tarfile
import tempfile

from _fetch import cached, download_verified, forget, mark_verified

URL = "https://dl.google.com/dl/cloudsdk/channels/rapid/components/google-cloud-sdk-pubsub-emulator-20261009074343.tar.gz"
SHA256 = "28f872a91407ff2a41e29fcf79567f9238322451ad4eb18fa541086ee9982fcf"


def main():
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/pubsub-emulator").resolve()
    launcher = destination / "platform/pubsub-emulator/bin/cloud-pubsub-emulator"
    if cached(launcher, SHA256):
        print(launcher)
        return
    destination.mkdir(parents=True, exist_ok=True)
    forget(launcher)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "pubsub.tar.gz"
        download_verified(URL, SHA256, archive, timeout=30, label="Pub/Sub emulator")
        with tarfile.open(archive) as package:
            package.extractall(destination, filter="data")
    mark_verified(launcher, SHA256)
    print(launcher)


if __name__ == "__main__":
    main()
