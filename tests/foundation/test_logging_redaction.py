"""Python log redaction mirrors the gateway's REDACT_PATHS semantics (W02 redacted logs)."""
import copy
import json
import logging
import re

import pytest

from brandme_core import logging as bm_logging
from brandme_core.logging import (
    REDACTED,
    classify_key,
    ensure_request_id,
    get_logger,
    pseudonymize,
    redact,
    redact_user_id,
)

PSEUDONYM = re.compile(r"h:[0-9a-f]{12}")


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def capture():
    log = get_logger("redaction-test")
    handler = _Capture()
    log.logger.addHandler(handler)
    try:
        yield log, handler
    finally:
        log.logger.removeHandler(handler)


def _lines(handler):
    return [json.loads(r.getMessage()) for r in handler.records]


@pytest.mark.parametrize("key", [
    "token", "access_token", "csrf_token", "x-csrf-token", "refreshToken", "secret", "client_secret", "password",
    "Password", "authorization", "Authorization", "cookie", "set-cookie", "apiKey", "api_key", "X-Api-Key",
    "credential", "credentials", "private_key", "privateKey", "seed", "wallet_seed", "mnemonic", "wallet",
    "wallet_key", "did_secret", "midnight_private_payload", "purchase_history", "ownership_lineage",
])
def test_secret_stems(key):
    assert classify_key(key) == "secret"


@pytest.mark.parametrize("key", [
    "email", "email_address", "userEmail", "phone", "phone_number", "user_id", "userId", "userid", "member_id",
    "memberId", "subject_ref", "owner", "owner_id", "from_owner", "garment_owner", "scanner_user_id",
    "reviewer_user_id", "garment_tag", "ip", "client_ip", "clientIp", "IP", "ip_address", "IPAddress",
    "x-real-ip", "x-forwarded-for", "remote_addr", "viewer_id", "actor_ref",
])
def test_identifier_stems(key):
    assert classify_key(key) == "identifier"


@pytest.mark.parametrize("key", [
    "event", "scan_id", "request_id", "cube_id", "asset_id", "garment_id", "region_code", "zip", "zip_code",
    "recipient_count", "description", "shipping", "policy_version", "status", "count", "error",
])
def test_ordinary_keys_pass_through(key):
    assert classify_key(key) is None


def test_redacts_nested_secrets_and_pseudonymizes_identifiers():
    record = {
        "event": "scan",
        "scan_id": "s1",
        "scanner_user_id": "member-123",
        "garment_tag": "TAG-SECRET",
        "ctx": {"userId": "zu1", "email": "a@b.example", "member_id": "zm1", "csrf_token": "zc1"},
        "req": {"headers": {"cookie": "bm_session=abc", "authorization": "Bearer t", "x-csrf-token": "zc2"}},
        "items": [{"owner_id": "zo1"}, ({"api_key": "zk1"},)],
        "owners": ["zo2", "zo3"],
        "ip": "203.0.113.7",
    }
    out = redact(record)
    text = json.dumps(out)
    # Every planted value contains a non-hex letter, so it cannot occur inside a pseudonym.
    for leaked in ("member-123", "TAG-SECRET", "zu1", "a@b.example", "zm1", "zc1", "bm_session=abc", "Bearer t",
                   "zc2", "zo1", "zk1", "zo2", "zo3", "203.0.113.7"):
        assert leaked not in text
    assert out["scan_id"] == "s1" and out["event"] == "scan"
    assert out["req"]["headers"] == {"cookie": REDACTED, "authorization": REDACTED, "x-csrf-token": REDACTED}
    assert out["ctx"]["csrf_token"] == REDACTED
    assert PSEUDONYM.fullmatch(out["scanner_user_id"])
    assert isinstance(out["items"][1], tuple) and out["items"][1][0]["api_key"] == REDACTED
    assert all(PSEUDONYM.fullmatch(v) for v in out["owners"])


def test_secret_containers_are_redacted_whole():
    assert redact({"credentials": {"user": "x", "pw": "y"}}) == {"credentials": REDACTED}
    assert redact({"tokens": ["a", "b"]}) == {"tokens": REDACTED}


def test_identifier_containers_pseudonymize_every_leaf_but_keep_shape():
    out = redact({"owner": {"id": "o1", "verified": True, "since": None, "names": ["Ann"]}})
    assert PSEUDONYM.fullmatch(out["owner"]["id"])
    assert out["owner"]["verified"] is True and out["owner"]["since"] is None
    assert PSEUDONYM.fullmatch(out["owner"]["names"][0])
    assert redact({"email_verified": False, "user_id": ""}) == {"email_verified": False, "user_id": ""}


def test_pseudonyms_are_stable_distinct_and_idempotent():
    a, b = pseudonymize("member-123"), pseudonymize("member-124")
    assert PSEUDONYM.fullmatch(a) and a == pseudonymize("member-123") and a != b
    assert pseudonymize(a) == a, "already-pseudonymized values must not be re-hashed"
    assert pseudonymize(42) == pseudonymize("42")
    assert redact_user_id("member-123") == a
    assert redact({"from_owner": redact_user_id("member-123")}) == {"from_owner": a}


def test_short_user_ids_are_no_longer_logged_in_full():
    """The legacy redact_user_id returned IDs of 8 characters or fewer verbatim."""
    assert "abc" not in redact_user_id("abc")
    assert redact_user_id("") == "unknown" and redact_user_id(None) == "unknown"


def test_caller_data_is_never_mutated():
    record = {"user_id": "u1", "nested": {"token": "t", "list": [{"email": "e@x.example"}]}, "tup": ("a", {"seed": 1})}
    before = copy.deepcopy(record)
    redact(record)
    log = get_logger("redaction-test-mutation")
    log.info(record)
    log.warning(record)
    assert record == before


def test_configured_salt_controls_pseudonyms(monkeypatch):
    monkeypatch.setattr(bm_logging, "_SALT", b"a" * 32)
    first = pseudonymize("member-123")
    monkeypatch.setattr(bm_logging, "_SALT", b"b" * 32)
    assert pseudonymize("member-123") != first


def test_salt_env_is_used_only_when_long_enough(monkeypatch):
    monkeypatch.setenv(bm_logging.SALT_ENV, "short")
    assert bm_logging._load_salt() != b"short"
    monkeypatch.setenv(bm_logging.SALT_ENV, "x" * 16)
    assert bm_logging._load_salt() == b"x" * 16


def test_depth_is_bounded():
    deep = current = {}
    for _ in range(100):
        current["next"] = {}
        current = current["next"]
    assert bm_logging.TRUNCATED in json.dumps(redact(deep))


def test_logger_levels_and_call_styles(capture):
    log, handler = capture
    log.debug({"event": "d"})
    log.info({"event": "i", "user_id": "u1"})
    log.warning({"event": "w", "authorization": "Bearer t"})
    log.warn("legacy alias")
    log.error("e", port=8007, email="a@b.example")
    log.critical({"event": "c"})
    log.info("msg", extra={"task_id": "t1", "member_id": "m1"})
    levels = [r.levelno for r in handler.records]
    assert levels == [logging.DEBUG, logging.INFO, logging.WARNING, logging.WARNING, logging.ERROR,
                      logging.CRITICAL, logging.INFO]
    lines = _lines(handler)
    assert all(line["service"] == "redaction-test" for line in lines)
    assert lines[1]["event"] == "i" and PSEUDONYM.fullmatch(lines[1]["user_id"])
    assert lines[2]["authorization"] == REDACTED
    assert lines[3]["message"] == "legacy alias"
    assert lines[4] == {"service": "redaction-test", "message": "e", "port": 8007,
                        "email": pseudonymize("a@b.example")}
    assert lines[6]["task_id"] == "t1" and PSEUDONYM.fullmatch(lines[6]["member_id"])
    assert "u1" not in json.dumps(lines) and "Bearer t" not in json.dumps(lines)


def test_exception_logs_type_and_frames_but_not_the_message(capture):
    log, handler = capture
    try:
        raise ValueError("No asset found for tag: TAG-SECRET")
    except ValueError:
        log.exception({"event": "lookup_failed"})
        log.error({"event": "lookup_failed_again"}, exc_info=True)
    first, second = _lines(handler)
    assert handler.records[0].levelno == logging.ERROR
    assert first["exc_type"] == "ValueError" and first["exc_frames"]
    assert second["exc_type"] == "ValueError"
    assert "TAG-SECRET" not in json.dumps([first, second])


def test_unserializable_values_do_not_break_logging(capture):
    log, handler = capture
    log.info({"event": "x", "when": object(), (1, 2): "tuple key"})
    assert _lines(handler)[0]["event"] == "x"


def test_cors_config_warning_no_longer_crashes(monkeypatch):
    """cors_config called StructuredLogger.warning, which did not exist."""
    from brandme_core import cors_config

    monkeypatch.setattr(cors_config, "parse_cors_origins", lambda: ["*"])
    with pytest.raises(ValueError):
        cors_config.get_cors_config({"BRANDME_MODE": "production"})


class _Request:
    def __init__(self, request_id=None):
        self.headers = {"X-Request-Id": request_id} if request_id is not None else {}


class _Response:
    def __init__(self):
        self.headers = {}


def test_ensure_request_id_accepts_safe_ids_and_optional_response():
    response = _Response()
    assert ensure_request_id(_Request("req-1.a:b_c"), response) == "req-1.a:b_c"
    assert response.headers["X-Request-Id"] == "req-1.a:b_c"
    generated = ensure_request_id(_Request())  # brandme-cube calls it without a response
    assert re.fullmatch(r"[0-9a-f-]{36}", generated)


@pytest.mark.parametrize("hostile", ["a\nfake log line", "x" * 200, "-starts-with-dash", "{\"json\":1}", " "])
def test_ensure_request_id_replaces_unsafe_values(hostile):
    assert ensure_request_id(_Request(hostile)) != hostile


def test_cyclic_payload_is_bounded_and_marked():
    import time
    d = {}
    d["a"] = d
    d["b"] = d
    t0 = time.monotonic()
    out = bm_logging.redact({"event": "x", "ctx": d})
    assert time.monotonic() - t0 < 1.0
    assert out["ctx"]["a"] == bm_logging.CYCLE and out["ctx"]["b"] == bm_logging.CYCLE
    shared = {"user_id": "member-123"}
    out = bm_logging.redact({"x": shared, "y": shared})  # shared, not cyclic: both copies kept
    assert out["x"] == out["y"] and out["x"]["user_id"].startswith("h:")


def test_generated_request_id_is_stable_per_request():
    from types import SimpleNamespace
    request = SimpleNamespace(headers={}, state=SimpleNamespace())
    first = bm_logging.ensure_request_id(request)
    assert bm_logging.ensure_request_id(request) == first
    bad = SimpleNamespace(headers={"X-Request-Id": "bad id\n"}, state=SimpleNamespace())
    assert bm_logging.ensure_request_id(bad) == bm_logging.ensure_request_id(bad) != "bad id\n"
