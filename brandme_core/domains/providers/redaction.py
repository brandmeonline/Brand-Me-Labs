"""Card-number detection and payment-processor log redaction (leaf module: no Brand.Me imports).

* ``contains_card_number`` / ``mask_card_numbers``: Luhn-valid 13-19 digit numbers, written
  as one run, as groups of any size joined by single spaces or hyphens, or as groups of 4+
  digits (the last may have 3) joined by any 1-3 non-alphanumeric characters ("4111/1111/...",
  "4111.1111...", "4111, 1111, ..."). UUIDs are blanked first, so identifier digits cannot
  chain into a "card". ``brandme_core.mcp.tools`` re-exports them for the tool gate and the planner.
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
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

_PAN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_DIGITS_RE = re.compile(r"\d+")
_GAP_RE = re.compile(r"[^\w]{1,3}")  # any short non-alphanumeric separator; "_" and letters break a number


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def _card_spans(text: str) -> List[Tuple[int, int]]:
    """Character spans of card numbers in ``text``, merged and in order."""
    scan = _UUID_RE.sub(lambda m: "u" * len(m.group()), text)  # same length: spans still index ``text``
    spans: List[Tuple[int, int]] = []
    for m in _PAN_RE.finditer(scan):  # groups of any size, single space or hyphen between them
        d = re.sub(r"\D", "", m.group())
        if 13 <= len(d) <= 19 and _luhn(d):
            spans.append((m.start(), m.start() + len(m.group().rstrip(" -"))))
    groups = [(m.start(), m.end()) for m in _DIGITS_RE.finditer(scan)]
    for i, (start, _end) in enumerate(groups):  # groups of 4+ digits (the last may have 3), any short separator
        digits = ""
        for j in range(i, len(groups)):
            s, e = groups[j]
            if e - s < 3 or (j > i and not _GAP_RE.fullmatch(scan[groups[j - 1][1]:s])):
                break
            digits += scan[s:e]
            if len(digits) > 19:
                break
            if len(digits) >= 13 and _luhn(digits):
                spans.append((start, e))
            if e - s < 4:
                break
    merged: List[Tuple[int, int]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def mask_card_numbers(text: str) -> str:
    """``text`` with card numbers replaced (UUIDs and the separators around a number are left intact)."""
    out, last = [], 0
    for s, e in _card_spans(text):
        out.append(text[last:s])
        out.append("[card number removed]")
        last = e
    out.append(text[last:])
    return "".join(out)


def contains_card_number(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_card_spans(value))
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
