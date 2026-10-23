"""Card-number detection and payment-processor log redaction (leaf module: no Brand.Me imports).

* ``contains_card_number`` / ``mask_card_numbers``: Luhn-valid 13-19 digit runs.
  UUIDs are held aside first, so identifier digits cannot chain into a "card".
  ``brandme_core.mcp.tools`` re-exports them for the tool gate and the planner.
* ``redact_processor_text`` masks processor secrets, object ids and card numbers
  in free text. ``install_processor_log_redaction()`` applies it to the
  ``stripe``, ``httpx`` and ``httpcore`` loggers and silences the Stripe SDK's
  console logging, which would otherwise print request and response bodies.
* ``payment_log_record`` is the only shape a payment log line takes: a fixed
  vocabulary with no ids, keys, amounts, metadata, URLs or exception text.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional

_PAN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def mask_card_numbers(text: str) -> str:
    """``text`` with Luhn-valid 13-19 digit card numbers replaced (UUIDs are left intact)."""
    uuids: List[str] = []

    def _hold(m: "re.Match[str]") -> str:
        uuids.append(m.group())
        return f"\x00{len(uuids) - 1}\x00"

    held = _UUID_RE.sub(_hold, text)

    def _mask(m: "re.Match[str]") -> str:
        run = m.group()
        d = re.sub(r"\D", "", run)
        if not (13 <= len(d) <= 19 and _luhn(d)):
            return run
        return "[card number removed]" + run[len(run.rstrip(" -")):]  # keep the separator after it

    masked = _PAN_RE.sub(_mask, held)
    return re.sub("\x00(\\d+)\x00", lambda m: uuids[int(m.group(1))], masked)


def contains_card_number(value: Any) -> bool:
    if isinstance(value, str):
        # Identifiers are not card data: remove UUIDs so their digit runs cannot
        # chain across hyphens into a Luhn-valid 13-19 digit sequence.
        value = _UUID_RE.sub(" ", value)
        for m in _PAN_RE.finditer(value):
            d = re.sub(r"\D", "", m.group())
            if 13 <= len(d) <= 19 and _luhn(d):
                return True
        return False
    if isinstance(value, Mapping):
        return any(contains_card_number(k) or contains_card_number(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_card_number(v) for v in value)
    return False


# Order matters: secrets first, then client secrets (which contain an object id), then object ids.
_START = r"(?<![A-Za-z0-9])"
_SECRET_RE = re.compile(_START + r"(?:sk|rk|pk)_(?:test|live)_\w+")
_WHSEC_RE = re.compile(_START + r"whsec_\w+")
_CLIENT_SECRET_RE = re.compile(_START + r"(?:pi|seti)_\w+?_secret_\w+")
_OBJECT_ID_RE = re.compile(_START + r"(pi|ch|re|pm|evt|acct|cus|py|txn|src|tok|req)_[A-Za-z0-9_]{6,}")


def redact_processor_text(text: str) -> str:
    """Processor keys, webhook secrets, client secrets, object ids and card numbers, masked."""
    out = _SECRET_RE.sub("[processor key removed]", str(text))
    out = _WHSEC_RE.sub("[webhook secret removed]", out)
    out = _CLIENT_SECRET_RE.sub("[client secret removed]", out)
    out = _OBJECT_ID_RE.sub(lambda m: f"{m.group(1)}_…", out)
    return mask_card_numbers(out)


class ProcessorLogFilter(logging.Filter):
    """Rewrites every record to its redacted, fully formatted message (no lazy args survive)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = redact_processor_text(message)
        record.args = ()
        return True


_PROCESSOR_LOGGERS = ("stripe", "httpx", "httpcore")


def install_processor_log_redaction() -> None:
    """Idempotent. Redacts processor and HTTP-client loggers and keeps the Stripe SDK off the console."""
    for name in _PROCESSOR_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, ProcessorLogFilter) for f in logger.filters):
            logger.addFilter(ProcessorLogFilter())
    logging.getLogger("stripe").setLevel(logging.WARNING)
    stripe = sys.modules.get("stripe")
    if stripe is not None:
        # The SDK prints post params and full response bodies (client_secret included) to stderr
        # when ``stripe.log`` or the STRIPE_LOG it read at import is "debug"/"info".
        stripe.log = None
        util = sys.modules.get("stripe._util")
        if util is not None and getattr(util, "STRIPE_LOG", None) is not None:
            util.STRIPE_LOG = None


PaymentLogSink = Callable[[Dict[str, Any]], None]
LOG_OPS = ("authorize", "capture", "void", "refund", "lookup", "find", "effect", "webhook")
LOG_OUTCOMES = ("ok", "declined", "requires_action", "not_found", "unsettled", "refused", "unknown", "error",
                "ignored")
_LOG_KINDS = ("unsupported", "not_configured", "unauthorized", "contract_restricted", "throttled", "transient",
              "malformed_provider_response", "outcome_unknown")


def payment_log_record(processor: str, op: str, outcome: str, kind: Optional[str], duration_ms: int,
                       environment: str) -> Dict[str, Any]:
    """One payment log line. Fixed keys and values; never ids, keys, amounts, metadata, URLs or ``str(exc)``."""
    if op not in LOG_OPS or outcome not in LOG_OUTCOMES or (kind is not None and kind not in _LOG_KINDS):
        raise ValueError("payment log record outside its fixed vocabulary")
    return {"component": "commerce.payments", "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "environment": str(environment)[:16], "processor": str(processor)[:32], "op": op, "outcome": outcome,
            "kind": kind, "duration_ms": max(0, int(duration_ms))}


def default_payment_log(record: Dict[str, Any]) -> None:
    """Foundation structured logger (one JSON line); falls back to stderr if it is unavailable."""
    try:
        from brandme_core.logging import get_logger
    except Exception:  # pragma: no cover - the foundation logger is always present in this repo
        print(json.dumps(record, sort_keys=True), file=sys.stderr)
        return
    get_logger("brandme-commerce-payments").info(record)
