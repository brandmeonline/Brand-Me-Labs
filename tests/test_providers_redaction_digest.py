"""Hex digests are never card numbers.

A random sha256 digest contains a Luhn-valid run of 13-19 digits about 0.75% of the time, which made
``contains_card_number`` (and therefore ``test_payment_identifiers_never_reach_models_events_or_wires``)
fail on payloads such as ``{"quote_hash": "sha256:..."}`` with no card number in them. Digests are masked
before the scan, like UUIDs; real card numbers, including one placed right after a ``sha256:`` prefix,
are still caught.
"""
import hashlib
import json
import random

from brandme_core.domains.providers.redaction import contains_card_number, mask_card_numbers

# Digests that failed CI: each holds a Luhn-valid 14-digit run (44095025254762, 00509399548379).
CI_DIGESTS = [
    "sha256:3a8d6c69b8823c654f72cb1e44095025254762a1ec8d0dbd5dab669fb49cdade",
    "sha256:e60cae427e5701e846b613d6970cc00509399548379b14cfb5cb95925ea28ae6",
]
PAN = "4242424242424242"


def test_digests_that_failed_ci_are_not_card_numbers():
    for digest in CI_DIGESTS:
        payload = json.dumps({"quote_id": "1f44e4bf-46be-439b-9d2e-000000000000", "quote_hash": digest, "cart_id": "x"})
        assert not contains_card_number(payload), digest
        assert mask_card_numbers(payload) == payload


def test_random_sha256_digests_are_never_flagged():
    rng = random.Random(20261102)
    for _ in range(20000):
        digest = hashlib.sha256(rng.randbytes(16)).hexdigest()
        assert not contains_card_number(f"sha256:{digest}"), digest
    assert not contains_card_number("SHA256:" + hashlib.sha256(b"upper").hexdigest().upper())
    assert not contains_card_number(hashlib.md5(b"md5").hexdigest())  # 32 hex characters


def test_card_numbers_are_still_caught():
    for text in (PAN, f"sha256:{PAN}", json.dumps({"card": PAN}), "4242 4242 4242 4242", "4242-4242-4242-4242",
                 f"{PAN} after a digest {CI_DIGESTS[0]}"):
        assert contains_card_number(text), text
        assert PAN[:6] not in mask_card_numbers(text).replace(" ", "").replace("-", "") or "4242" not in mask_card_numbers(PAN)
    assert mask_card_numbers(f"{CI_DIGESTS[0]} {PAN}").startswith(CI_DIGESTS[0])


def test_all_digit_runs_are_not_treated_as_digests():
    # No letter: not a hex digest, so the scanner sees it unchanged (a bare card number stays detectable).
    assert contains_card_number(f"ref 0000 {PAN} 0000")
