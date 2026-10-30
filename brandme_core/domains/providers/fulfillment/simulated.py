"""Deterministic in-process fulfillment — SIMULATION ONLY. Nothing ships.

The simulated merchant's warehouse: it records per-line ordered, shipped,
delivered, returned and cancelled units, keeps the counter invariants of
``FulfillmentLine.check``, and is idempotent on every mutating key. ``ship``,
``receive_return`` and ``pending_returns`` are simulator controls (a real
fulfillment provider reports these itself); they are not part of the protocol.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from ..contracts import ProviderError, ProviderErrorKind
from . import (CancellationResult, ExchangeRequest, FulfillmentEvent, FulfillmentLine, FulfillmentRecord,
               FulfillmentRequest, ReturnAuthorization)


class SimulatedFulfillment:
    fulfillment_id = "sim_fulfillment"
    simulation = True

    def __init__(self, clock: Callable[[], datetime]):
        self._clock = clock
        self._lock = threading.RLock()
        self._lines: Dict[str, List[FulfillmentLine]] = {}
        self._opened: Dict[str, str] = {}  # open key -> order ref
        self._cancels: Dict[str, CancellationResult] = {}
        self._returns: Dict[str, ReturnAuthorization] = {}
        self._exchanges: Dict[str, str] = {}  # exchange key -> order ref
        self._pending: Dict[Tuple[str, str], int] = {}  # (order ref, variant ref) -> units being returned
        self.calls: list = []  # (operation, key) — test evidence

    # -- helpers ---------------------------------------------------------------
    def _get(self, order_ref: str) -> List[FulfillmentLine]:
        lines = self._lines.get(order_ref)
        if lines is None:
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown order")
        return lines

    def _set(self, order_ref: str, lines: List[FulfillmentLine]) -> None:
        for line in lines:
            line.check()
        before = {l.source_variant_ref: l for l in self._lines.get(order_ref, [])}
        for line in lines:  # counters never decrease
            old = before.get(line.source_variant_ref)
            if old is not None and any(getattr(line, f) < getattr(old, f)
                                       for f in ("ordered", "shipped", "delivered", "returned", "cancelled")):
                raise ValueError("fulfillment counters only grow")
        self._lines[order_ref] = lines

    def _record(self, order_ref: str) -> FulfillmentRecord:
        return FulfillmentRecord(self.fulfillment_id, order_ref, tuple(self._get(order_ref)), self._clock(),
                                 f"sim:{self.fulfillment_id}:{order_ref}")

    # -- FulfillmentProvider -----------------------------------------------------
    def open(self, request: FulfillmentRequest) -> FulfillmentRecord:
        with self._lock:
            self.calls.append(("open", request.idempotency_key))
            prior = self._opened.get(request.idempotency_key)
            if prior is not None:
                return self._record(prior)
            if request.order_ref in self._lines:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "order already opened under another key")
            units: Dict[str, int] = {}
            for l in request.lines:
                units[l.source_variant_ref] = units.get(l.source_variant_ref, 0) + l.quantity
            if not units or any(not 1 <= q <= 99 for q in units.values()):
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "order lines out of range")
            self._set(request.order_ref, [FulfillmentLine(ref, q) for ref, q in units.items()])
            self._opened[request.idempotency_key] = request.order_ref
            return self._record(request.order_ref)

    def record(self, order_ref: str) -> FulfillmentRecord:
        with self._lock:
            return self._record(order_ref)

    def cancel_unshipped(self, order_ref: str, source_variant_ref: Optional[str], quantity: Optional[int], *,
                         idempotency_key: str) -> CancellationResult:
        with self._lock:
            self.calls.append(("cancel", idempotency_key))
            prior = self._cancels.get(idempotency_key)
            if prior is not None:
                return prior
            new, done = [], []
            for l in self._get(order_ref):
                if source_variant_ref is None or l.source_variant_ref == source_variant_ref:
                    n = min(l.open_units, quantity) if quantity else l.open_units
                    if n > 0:
                        done.append((l.source_variant_ref, n))
                        l = replace(l, cancelled=l.cancelled + n)
                new.append(l)
            self._set(order_ref, new)
            result = CancellationResult(order_ref, tuple(done), self._clock())
            self._cancels[idempotency_key] = result
            return result

    def authorize_return(self, order_ref: str, source_variant_ref: str, quantity: int, *,
                         idempotency_key: str) -> ReturnAuthorization:
        with self._lock:
            self.calls.append(("return", idempotency_key))
            prior = self._returns.get(idempotency_key)
            if prior is not None:
                return prior
            line = next((l for l in self._get(order_ref) if l.source_variant_ref == source_variant_ref), None)
            slot = (order_ref, source_variant_ref)
            # Units still owed and not already being returned. A request may precede delivery (the
            # member returns the parcel when it arrives); receipt is checked when it comes back.
            allowed = 0 if line is None else line.ordered - line.cancelled - line.returned - self._pending.get(slot, 0)
            ok = isinstance(quantity, int) and 1 <= quantity <= allowed
            if ok:
                self._pending[slot] = self._pending.get(slot, 0) + quantity
            ra = ReturnAuthorization(f"sim-return-{order_ref}-{source_variant_ref}", order_ref, source_variant_ref,
                                     quantity, "requested" if ok else "refused", self._clock())
            self._returns[idempotency_key] = ra
            return ra

    def request_exchange(self, request: ExchangeRequest) -> FulfillmentRecord:
        with self._lock:
            self.calls.append(("exchange", request.idempotency_key))
            if request.idempotency_key in self._exchanges:
                return self._record(request.order_ref)
            lines = self._get(request.order_ref)
            original = next((l for l in lines if l.source_variant_ref == request.from_ref), None)
            pending = self._pending.get((request.order_ref, request.from_ref), 0)  # units already being returned
            if original is None or request.from_ref == request.to_ref or not (
                    1 <= request.quantity <= original.delivered - original.returned - pending):
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "only delivered, unreturned units exchange")
            existing = next((l for l in lines if l.source_variant_ref == request.to_ref), None)
            if existing is not None and existing.ordered + request.quantity > 99:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "replacement quantity out of range")
            new = []
            for l in lines:
                if l.source_variant_ref == request.from_ref:
                    l = replace(l, returned=l.returned + request.quantity)
                elif l.source_variant_ref == request.to_ref:
                    # Back into a variant already on the order (e.g. M -> L -> M): the line grows; its
                    # earlier history (including its own return) is kept.
                    l = replace(l, ordered=l.ordered + request.quantity)
                new.append(l)
            if existing is None:
                new.append(FulfillmentLine(request.to_ref, request.quantity, exchanged_from_ref=request.from_ref))
            self._set(request.order_ref, new)
            self._exchanges[request.idempotency_key] = request.order_ref
            return self._record(request.order_ref)

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> Optional[FulfillmentEvent]:
        return None  # the simulated merchant's own signer covers simulated events

    # -- simulator controls ----------------------------------------------------------
    def ship(self, order_ref: str, partial: Optional[Mapping[str, object]] = None,
             deliver: bool = True) -> FulfillmentRecord:
        """Ship (and deliver) what is still owed; ``partial`` caps one line (or each line) at ``quantity``."""
        with self._lock:
            new = []
            for l in self._get(order_ref):
                qty = l.ordered - l.cancelled  # cancelled units never ship
                if partial is not None and l.source_variant_ref == partial.get("source_variant_ref",
                                                                                 l.source_variant_ref):
                    qty = min(qty, int(partial.get("quantity", 1)))
                new.append(replace(l, shipped=max(l.shipped, qty),
                                   delivered=max(l.delivered, qty if deliver else 0)))
            self._set(order_ref, new)
            return self._record(order_ref)

    def receive_return(self, order_ref: str, source_variant_ref: str, quantity: int) -> FulfillmentRecord:
        """Shipped units come back (delivered or refused at the door); requested returns are settled first."""
        with self._lock:
            new = []
            for l in self._get(order_ref):
                if l.source_variant_ref == source_variant_ref and quantity:
                    if not 0 < quantity <= l.shipped - l.returned:
                        raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "more units returned than shipped")
                    l = replace(l, returned=l.returned + quantity)
                    slot = (order_ref, source_variant_ref)
                    if self._pending.get(slot):
                        self._pending[slot] = max(0, self._pending[slot] - quantity)
                new.append(l)
            self._set(order_ref, new)
            return self._record(order_ref)

    def pending_returns(self, order_ref: str, source_variant_ref: str) -> int:
        with self._lock:
            return self._pending.get((order_ref, source_variant_ref), 0)
