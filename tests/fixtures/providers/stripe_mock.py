"""stripe-mock fixture: Stripe's OpenAPI-driven mock server, for WIRE-SHAPE tests only.

stripe-mock validates every request against Stripe's published OpenAPI spec and
answers with canned fixtures (a confirmed or captured PaymentIntent still reads
``requires_payment_method``). A passing test here proves the adapter sends
requests Stripe's API accepts; it proves nothing about payment behaviour, which
is covered by the simulated processor and, with a test-mode key, the live suite.

Binary: ``go install github.com/stripe/stripe-mock@v0.206.0`` (module sum
``h1:vYmwCFXxDX5qSaSwFJDbciADVyE/EMhSXZosDPIbhGg=``), located through
``STRIPE_MOCK_BIN`` or ``PATH``. Without it the tests are skipped with that reason,
never reported as passed.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time

import pytest

PINNED_VERSION = "v0.206.0"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def stripe_mock_url():
    binary = os.environ.get("STRIPE_MOCK_BIN") or shutil.which("stripe-mock")
    if not binary or not os.access(binary, os.X_OK):
        pytest.skip(f"stripe-mock {PINNED_VERSION} not found (STRIPE_MOCK_BIN); wire-shape tests not run")
    http, https = _free_port(), _free_port()
    proc = subprocess.Popen([binary, "-http-port", str(http), "-https-port", str(https)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", http), timeout=0.5).close()
                break
            except OSError:
                if proc.poll() is not None:
                    pytest.fail("stripe-mock exited during startup")
                time.sleep(0.1)
        else:
            pytest.fail("stripe-mock did not start within 20 s")
        yield f"http://127.0.0.1:{http}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
