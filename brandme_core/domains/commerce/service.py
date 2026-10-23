"""Commerce application service (ch.05 §5–§6, ch.03 §5–§6).

Invariants enforced here:

* Identity comes only from the foundation ``Principal``; no method accepts a
  member/user id. Every public method binds the principal first: a first-party
  session acts as the member; any other caller is an agent and is resolved to
  its one active delegation for (member, client). Agent scopes are the
  intersection of token scopes and delegation scopes.
* An agent can research and prepare carts; it cannot approve, and it can only
  execute a purchase that a first-party trusted surface approved for the exact
  canonical quote hash.
* Budget reservation, approval consumption, idempotency record and the durable
  submission intent commit in one transaction *before* provider network I/O.
* Every write happens inside ``store.run(fn)``; ``fn`` may be retried by
  Spanner, so it only reads and writes rows and emits events — provider calls
  happen before or after it, never inside.
* A transmitted-but-unanswered submission becomes ``outcome_unknown`` and is
  reconciled through the same provider idempotency key; it is never blindly
  re-sent and the same quote cannot be purchased again meanwhile.
* Order, payment and fulfillment facts stay separate; webhooks are verified,
  deduplicated, and applied by re-reading the source of truth.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import rfc8785

from brandme_core.domains.providers.contracts import (
    CartLineRequest, CheckoutProvider, OrderObservation, OrderProvider, ProviderError,
    ProviderErrorKind, ReturnsProvider, SubmitRequest,
)
from brandme_core.domains import base as _foundation
from brandme_core.domains.privacy.deletion import ProcessingFrozenError
from brandme_core.domains.providers.registry import ProviderRegistry, RegistryError
from brandme_core.events import EventEnvelope

from . import events as _events  # noqa: F401  (registers commerce event types)
from .delegation import (
    DEFAULT_EXCLUDED_CATEGORIES, AgentDelegation, AssistanceMode, DelegationLimits, build_delegation,
)
from .errors import (
    ApprovalInvalid, BudgetExceeded, CapabilityUnavailable, CommerceError, DelegationConflict,
    DelegationInvalid, Forbidden, IdempotencyConflict, InvalidQuote, InvalidRequest, NotFound, ProcessingRestricted,
    VersionConflict,
)
from .money import Money, sum_money
from .principal import Principal, is_agent, is_first_party, meets_assurance, validate_principal
from .privacy_handler import AGENT_GRANTS, CARTS_QUOTES, ORDERS
from .quote import MATERIALITY_RULE, CheckoutQuote, QuoteLine
from .records import (
    IN_FLIGHT, ApprovalChallenge, BudgetEntry, Cart, IdempotencyRecord, Order, OrderLine,
    PurchaseApproval, PurchaseOperation, ReturnRequest, WebhookReceipt, check_transition,
)
from .store import new_id

Clock = Callable[[], datetime]

APPROVAL_CHALLENGE_TTL = timedelta(minutes=5)
STALE_SUBMITTING = timedelta(minutes=2)
MAX_CART_LINES = 50
# Payment status only moves forward. captured, voided and failed are alternative outcomes of an
# authorization (same rank: the first one observed stands); refunds follow a capture.
_PAYMENT_RANK = {"unknown": 0, "authorized": 1, "captured": 2, "voided": 2, "failed": 2,
                 "partially_refunded": 3, "refunded": 4}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# When the data a write is based on was read: the start of a queued assistant task, else "now".
_PROCESSING_BASIS: ContextVar[Optional[datetime]] = ContextVar("commerce_processing_basis", default=None)
# The request or task id that commerce events emitted in this context share (a UUID).
_CORRELATION: ContextVar[Optional[str]] = ContextVar("commerce_correlation", default=None)


def _uuid_or_none(value: Optional[str]) -> Optional[str]:
    try:
        return str(uuid.UUID(str(value))) if value else None
    except ValueError:
        return None


@contextmanager
def correlation(correlation_id: Optional[str]) -> Iterator[None]:
    """Events emitted inside this block carry ``correlation_id`` (ignored unless it is a UUID)."""
    token = _CORRELATION.set(_uuid_or_none(correlation_id))
    try:
        yield
    finally:
        _CORRELATION.reset(token)


@contextmanager
def processing_basis(at: datetime) -> Iterator[None]:
    """Writes made inside this block are refused if a deletion of their category committed after ``at``."""
    token = _PROCESSING_BASIS.set(at)
    try:
        yield
    finally:
        _PROCESSING_BASIS.reset(token)


def _digest(doc: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(doc)).hexdigest()


def _owner_only(principal: Principal, owner_member_id: Optional[str], detail: str) -> None:
    """Foundation object authorization (deny by default, 404 so existence does not leak).

    Commerce objects have no sharing grants: an agent reaches them only as the member,
    through its delegation, and delegation scope is checked before this.
    """
    try:
        if owner_member_id is None:
            raise _foundation.NotFound(detail)
        _foundation.authorize(principal, "commerce.read", owner_member_id)
    except _foundation.NotFound:
        raise NotFound(detail) from None


def _nonce_hash(nonce: str) -> str:
    return "sha256:" + hashlib.sha256(nonce.encode("utf-8")).hexdigest()


class CommerceService:
    def __init__(self, *, store: Any, registry: ProviderRegistry,
                 environment: str, clock: Clock = _utcnow,
                 approval_requires_assurance: str = "aal2"):
        self.store = store  # InMemoryCommerceStore or SpannerCommerceStore
        self.registry = registry
        self.environment = environment
        self.clock = clock
        self.approval_requires_assurance = approval_requires_assurance

    # ------------------------------------------------------------------ utils
    def _event(self, tx: Any, event_type: str, aggregate_type: str, aggregate_id: str, version: int,
               actor: Principal | str, payload: Dict[str, Any], correlation_id: Optional[str] = None,
               privacy_class: str = "member_private") -> None:
        tx.emit(EventEnvelope(
            event_type=event_type, schema_version="1", aggregate_type=aggregate_type,
            aggregate_id=aggregate_id, aggregate_version=version, environment=self.environment,
            actor_ref=actor if isinstance(actor, str) else actor.actor_ref,
            correlation_id=correlation_id or _CORRELATION.get() or new_id(), privacy_class=privacy_class,
            payload=payload,
            occurred_at=self.clock()))

    def _guard(self, tx: Any, member_id: str, category: str) -> None:
        """My Data processing guard for a member or agent write, read inside that write's transaction.

        Refused while a deletion of the member's data in ``category`` is pending (or after an
        account deletion), and after a category deletion newer than the processing basis.
        Provider settlement writes (acks, reconciliation, webhooks, observations) are not
        guarded: they record what a provider did with the member's money and are retained
        financial evidence of ``commerce.orders``.
        """
        try:
            tx.assert_processing_allowed(member_id, category, _PROCESSING_BASIS.get() or self.clock())
        except ProcessingFrozenError:
            raise ProcessingRestricted("this data is being deleted or its processing is restricted") from None

    def bind(self, principal: Principal) -> Principal:
        """Resolve who is acting: first-party sessions pass through; agents get their delegation."""
        return self._bind(principal)[0]

    def _bind(self, principal: Principal) -> Tuple[Principal, Optional[AgentDelegation]]:
        try:
            validate_principal(principal)
        except (TypeError, ValueError) as exc:
            raise Forbidden(str(exc), code="invalid_principal") from None
        if principal.environment != self.environment:
            raise Forbidden("principal environment mismatch")
        if is_first_party(principal):
            return principal, None
        if not principal.client_id:
            raise DelegationInvalid("agent principal without a client", code="delegation_required")
        now = self.clock()
        if principal.delegation_id is not None:
            d = self.store.get("delegations", principal.delegation_id)
            if d is None:
                raise DelegationInvalid("unknown delegation")
        else:
            d = self._active_delegation(self.store, principal.member_id, principal.client_id, now)
            if d is None:
                raise DelegationInvalid("no active delegation for this client", code="delegation_required")
        bound = replace(principal, delegation_id=d.id)
        d.require_active_for(bound, now)
        return bound, d

    @staticmethod
    def _active_delegation(reader: Any, member_id: str, client_id: str, now: datetime) -> Optional[AgentDelegation]:
        active = reader.active_delegations(member_id, client_id, now)
        if len(active) > 1:  # prevented by create_delegation; refuse rather than guess
            raise DelegationInvalid("ambiguous delegation for this client", code="delegation_ambiguous")
        return active[0] if active else None

    def _authorize(self, principal: Principal, scope: str) -> Tuple[Principal, Optional[AgentDelegation]]:
        """Bind, then gate agents on ``scope`` in both the token and the delegation.

        A first-party session is the member acting on Brand.Me's own UI; its
        authority is the member's, not an OAuth scope.
        """
        principal, d = self._bind(principal)
        if d is not None and (scope not in principal.scopes or scope not in d.scopes):
            raise Forbidden(f"missing scope {scope}", code="insufficient_scope")
        return principal, d

    def _require_first_party(self, principal: Principal, detail: str, code: str) -> Principal:
        if is_agent(principal):
            raise Forbidden(detail, code=code)
        return self._bind(principal)[0]

    def _require_capability(self, provider_id: str, capability: str) -> Any:
        try:
            conn = self.registry.get(provider_id)
        except RegistryError:
            raise NotFound("unknown provider") from None
        if not conn.can_execute(capability):
            st = conn.capability(capability)
            raise CapabilityUnavailable(f"{provider_id} {capability} is {st.state}",
                                        code=f"capability_{st.state}")
        return conn

    @staticmethod
    def _own(reader: Any, table: str, key: str, principal: Principal) -> Any:
        row = reader.get(table, key)
        _owner_only(principal, getattr(row, "member_id", None), f"{table[:-1]} not found")
        return row

    @staticmethod
    def _quote(reader: Any, principal: Principal, quote_id: str) -> CheckoutQuote:
        row = reader.get("quotes", quote_id)
        _owner_only(principal, row[0] if row is not None else None, "quote not found")
        return row[1]

    def _idempotent(self, principal: Principal, operation: str, key: Optional[str],
                    request: Mapping[str, Any]) -> Tuple[Optional[Tuple], Optional[str], str]:
        digest = _digest(dict(request))
        if not key:
            return None, None, digest
        if not 16 <= len(key) <= 128:  # foundation Idempotency-Key contract
            raise InvalidRequest("Idempotency-Key must be 16-128 characters", code="idempotency_key_invalid")
        # (member, environment, operation, delegation|"-", key): the same scope as foundation's
        # actor_ref-based key, laid out as the CommerceIdempotencyKeys primary key.
        scope = (principal.member_id, self.environment, operation, principal.delegation_id or "-", key)
        rec = self.store.get("idempotency", scope)
        if rec is None:
            return scope, None, digest
        if rec.request_digest != digest:
            raise IdempotencyConflict("idempotency key reused with a different request")
        return scope, rec.result_ref, digest

    # ------------------------------------------------------------- delegation
    def create_delegation(self, principal: Principal, *, client_id: str, mode: AssistanceMode,
                          allowed_providers: Iterable[str], limits: Optional[DelegationLimits],
                          expires_at: datetime) -> AgentDelegation:
        principal = self._require_first_party(principal, "agents cannot create or widen delegations",
                                              "not_trusted_surface")
        now = self.clock()
        d = build_delegation(granting=principal, delegation_id=new_id(), client_id=client_id,
                             mode=mode, allowed_providers=frozenset(allowed_providers),
                             limits=limits, now=now, expires_at=expires_at)

        def _tx(tx):
            self._guard(tx, principal.member_id, AGENT_GRANTS)
            # One active grant per (member, client): an agent's authority is never ambiguous.
            if self._active_delegation(tx, principal.member_id, client_id, now) is not None:
                raise DelegationConflict("this client already has an active delegation; revoke it first")
            tx.put("delegations", d.id, d)
            self._event(tx, "commerce.delegation.created", "AgentDelegation", d.id, 1, principal,
                        {"delegation_id": d.id, "mode": d.mode.value, "client_id": client_id})
            return d
        return self.store.run(_tx)

    def revoke_delegation(self, principal: Principal, delegation_id: str) -> AgentDelegation:
        principal = self._require_first_party(principal, "agents cannot revoke delegations",
                                              "not_trusted_surface")

        def _tx(tx):
            d = self._own(tx, "delegations", delegation_id, principal)
            if d.revoked_at is not None:
                return d
            d = replace(d, revoked_at=self.clock(), version=d.version + 1)
            tx.put("delegations", d.id, d)
            # Cancel unsent work immediately; submitted work keeps reconciling.
            for op in tx.operations_for_delegation(d.id):
                if op.state in ("draft", "quoting", "awaiting_approval", "approved"):
                    self._transition(tx, op, "cancelled", reason="delegation_revoked")
                    self._release_budget(tx, op.id)
                    self._void_approval(tx, op.approval_id)
            self._event(tx, "commerce.delegation.revoked", "AgentDelegation", d.id, d.version, principal,
                        {"delegation_id": d.id})
            return d
        return self.store.run(_tx)

    def list_delegations(self, principal: Principal) -> List[AgentDelegation]:
        principal = self._require_first_party(principal, "only the member can list their grants", "not_trusted_surface")
        return sorted(self.store.for_member("delegations", principal.member_id), key=lambda d: d.created_at,
                      reverse=True)

    # ------------------------------------------------------------------ carts
    def create_cart(self, principal: Principal, *, provider_id: str, merchant_id: str,
                    lines: Sequence[CartLineRequest], idempotency_key: Optional[str] = None) -> Cart:
        principal, d = self._authorize(principal, "commerce:cart")
        if d is not None:
            if d.mode is AssistanceMode.RESEARCH:
                raise Forbidden("research delegation cannot build carts")
            if provider_id not in d.allowed_providers:
                raise Forbidden("provider not allowed by delegation")
        self._validate_lines(lines)
        request = {"provider_id": provider_id, "merchant_id": merchant_id,
                   "lines": [[l.variant_id, l.source_variant_ref, l.quantity] for l in lines]}
        scope, prior, digest = self._idempotent(principal, "cart.create", idempotency_key, request)
        if prior:
            return self.store.get("carts", prior)
        conn = self._require_capability(provider_id, "cart.create")
        provider_cart = conn.adapter.create_cart(merchant_id, list(lines))  # provider I/O outside txn
        cart = Cart(id=new_id(), member_id=principal.member_id, provider_id=provider_id,
                    merchant_id=merchant_id, provider_cart_ref=provider_cart.provider_cart_ref,
                    lines=tuple(lines), revision=1, created_by_client=principal.client_id or "")

        def _tx(tx):
            self._guard(tx, principal.member_id, CARTS_QUOTES)
            if scope:
                winner = tx.get("idempotency", scope)
                if winner is not None:  # lost a race: return the winner
                    return tx.get("carts", winner.result_ref)
                tx.put("idempotency", scope, IdempotencyRecord(scope, digest, cart.id, self.clock()))
            tx.put("carts", cart.id, cart)
            return cart
        return self.store.run(_tx)

    @staticmethod
    def _guard_agent_cart(principal: Principal, d: Optional[AgentDelegation], cart: Cart) -> None:
        """An agent edits or quotes only carts its own client built, at providers its grant allows."""
        if d is None:
            return
        if d.mode is AssistanceMode.RESEARCH:
            raise Forbidden("research delegation cannot change or quote carts")
        if cart.provider_id not in d.allowed_providers:
            raise Forbidden("provider not allowed by delegation")
        if cart.created_by_client != principal.client_id:
            raise Forbidden("this cart was built by someone else", code="cart_not_yours")

    def update_cart(self, principal: Principal, cart_id: str, *, if_match: int,
                    lines: Sequence[CartLineRequest]) -> Cart:
        principal, d = self._authorize(principal, "commerce:cart")
        self._validate_lines(lines)
        cart = self._own(self.store, "carts", cart_id, principal)
        self._guard_agent_cart(principal, d, cart)
        if cart.revision != if_match:
            raise VersionConflict("cart revision changed", current_version=cart.revision)
        conn = self._require_capability(cart.provider_id, "cart.update")
        # Full replacement semantics normalized here, protected by the revision check.
        conn.adapter.replace_cart(cart.provider_cart_ref, list(lines))

        def _tx(tx):
            self._guard(tx, principal.member_id, CARTS_QUOTES)
            current = tx.get("carts", cart_id)
            if current.revision != if_match:
                raise VersionConflict("cart revision changed", current_version=current.revision)
            updated = replace(current, lines=tuple(lines), revision=current.revision + 1, status="draft")
            tx.put("carts", updated.id, updated)
            return updated
        return self.store.run(_tx)

    @staticmethod
    def _validate_lines(lines: Sequence[CartLineRequest]) -> None:
        if not lines or len(lines) > MAX_CART_LINES:
            raise InvalidQuote("cart must have 1..50 lines")
        seen = set()
        for l in lines:
            if not 1 <= l.quantity <= 99:
                raise InvalidQuote("quantity out of range")
            if l.variant_id in seen:
                raise InvalidQuote("duplicate variant in cart")
            seen.add(l.variant_id)

    # ----------------------------------------------------------------- quotes
    def quote_cart(self, principal: Principal, cart_id: str) -> CheckoutQuote:
        principal, d = self._authorize(principal, "commerce:cart")
        cart = self._own(self.store, "carts", cart_id, principal)
        self._guard_agent_cart(principal, d, cart)
        conn = self._require_capability(cart.provider_id, "price.quote")
        from brandme_core.domains.providers.contracts import ProviderCart
        pq = conn.adapter.quote(ProviderCart(cart.provider_cart_ref, cart.merchant_id, cart.lines))
        wanted = {(l.variant_id, l.source_variant_ref, l.quantity) for l in cart.lines}
        got = {(l.variant_id, l.source_variant_ref, l.quantity) for l in pq.lines}
        if wanted != got:
            # Stock loss / quantity cap: never silently substitute or shrink.
            raise InvalidQuote("provider could not quote the exact cart (stock or quantity changed)",
                               code="cart_not_quotable")
        if pq.merchant_id != cart.merchant_id:
            raise InvalidQuote("merchant changed between cart and quote")
        currency = pq.lines[0].unit_price.currency
        lines = tuple(QuoteLine(l.variant_id, l.source_variant_ref, l.quantity, l.unit_price,
                                l.unit_price.times(l.quantity), l.title, l.category) for l in pq.lines)
        subtotal = sum_money((l.line_total for l in lines), currency)
        now = self.clock()
        quote = CheckoutQuote(
            id=new_id(), environment=self.environment, provider_id=cart.provider_id,
            merchant_id=pq.merchant_id, payee_ref=pq.payee_ref, cart_id=cart.id,
            cart_revision=cart.revision, lines=lines, subtotal=subtotal, tax=pq.tax,
            shipping=pq.shipping, discount=pq.discount,
            total=(subtotal + pq.tax + pq.shipping) - pq.discount,
            delivery_ref=pq.delivery_ref, terms=pq.terms, checkout_reference=pq.checkout_reference,
            issued_at=now, expires_at=pq.expires_at, source_evidence_ref=pq.evidence_ref,
        ).seal()

        def _tx(tx):
            self._guard(tx, principal.member_id, CARTS_QUOTES)
            current = tx.get("carts", cart.id)
            if current.revision != cart.revision:
                raise VersionConflict("cart changed while quoting", current_version=current.revision)
            tx.put("quotes", quote.id, (principal.member_id, quote))
            tx.put("carts", cart.id, replace(current, status="quoted"))
            self._event(tx, "commerce.quote.ready", "CheckoutQuote", quote.id, 1, principal,
                        {"quote_id": quote.id, "quote_hash": quote.quote_hash, "cart_id": cart.id})
            return quote
        return self.store.run(_tx)

    def get_quote(self, principal: Principal, quote_id: str) -> CheckoutQuote:
        principal, _ = self._authorize(principal, "commerce:research")
        return self._quote(self.store, principal, quote_id)

    # -------------------------------------------------------- purchase request
    def request_purchase(self, principal: Principal, quote_id: str) -> PurchaseOperation:
        """Agent or member asks for approval. Creates no approval, spends nothing."""
        principal, d = self._authorize(principal, "commerce:cart")
        quote = self._quote(self.store, principal, quote_id)
        quote.verify_seal()
        quote.ensure_fresh(self.clock())
        if d is not None:
            if d.mode is AssistanceMode.RESEARCH:
                raise Forbidden("research delegation cannot request purchases")
            if quote.provider_id not in d.allowed_providers:
                raise Forbidden("provider not allowed by delegation")
            if d.mode is AssistanceMode.BUY_WITHIN_RULES:
                self._check_grant(d, quote)
        now = self.clock()
        op = PurchaseOperation(
            id=new_id(), member_id=principal.member_id, delegation_id=principal.delegation_id,
            client_id=principal.client_id or "", quote_id=quote.id, quote_hash=quote.quote_hash,
            approval_id=None, provider_id=quote.provider_id, state="awaiting_approval",
            provider_idempotency_key="bm-" + secrets.token_hex(16), created_at=now, updated_at=now)

        def _tx(tx):
            self._guard(tx, principal.member_id, ORDERS)
            tx.put("operations", op.id, op)
            self._event(tx, "commerce.purchase.approval_requested", "PurchaseOperation", op.id, 1, principal,
                        {"operation_id": op.id, "quote_id": quote.id})
            return op
        return self.store.run(_tx)

    # ------------------------------------------------- trusted approval surface
    def open_approval_challenge(self, principal: Principal, operation_id: str) -> ApprovalChallenge:
        """Rendered only by Brand.Me's deterministic approval UI (AP2 trusted surface)."""
        principal = self._require_first_party(principal, "only the member's trusted surface can open an approval",
                                              "not_trusted_surface")
        op = self._own(self.store, "operations", operation_id, principal)
        if op.state != "awaiting_approval":
            raise ApprovalInvalid(f"operation is {op.state}")
        quote = self._quote(self.store, principal, op.quote_id)
        quote.verify_seal()
        now = self.clock()
        quote.ensure_fresh(now)
        nonce = secrets.token_urlsafe(24)
        ch = ApprovalChallenge(id=new_id(), member_id=principal.member_id, operation_id=op.id, quote_id=quote.id,
                               quote_hash=quote.quote_hash, nonce_hash=_nonce_hash(nonce),
                               delegation_ref=op.delegation_id, issued_at=now,
                               expires_at=min(quote.expires_at, now + APPROVAL_CHALLENGE_TTL))
        def _tx(tx):
            self._guard(tx, principal.member_id, CARTS_QUOTES)
            tx.put("challenges", ch.id, ch)
        self.store.run(_tx)
        return replace(ch, nonce=nonce)  # the plaintext nonce leaves once, to the trusted surface

    def approve(self, principal: Principal, *, operation_id: str, challenge_id: str, nonce: str,
                displayed_quote_hash: str) -> PurchaseApproval:
        principal = self._require_first_party(principal, "agents cannot approve purchases", "not_trusted_surface")
        op = self._own(self.store, "operations", operation_id, principal)
        # Foundation's ``simulated`` dev identity may approve only simulated providers in local environments.
        if not meets_assurance(principal, self.approval_requires_assurance,
                               simulation_ok=self._is_simulation(op.provider_id)):
            raise ApprovalInvalid("reauthentication required", code="reauthentication_required")
        now = self.clock()

        def _tx(tx):
            self._guard(tx, principal.member_id, ORDERS)
            op = self._own(tx, "operations", operation_id, principal)
            ch = self._own(tx, "challenges", challenge_id, principal)
            quote = self._quote(tx, principal, op.quote_id)
            if ch.used or now >= ch.expires_at:
                raise ApprovalInvalid("approval challenge expired or used")
            if not secrets.compare_digest(ch.nonce_hash, _nonce_hash(nonce)):
                raise ApprovalInvalid("approval nonce mismatch")
            if ch.quote_id != op.quote_id or ch.operation_id != op.id:
                raise ApprovalInvalid("challenge is for a different operation")
            if op.state != "awaiting_approval":  # a second challenge cannot approve twice
                raise ApprovalInvalid(f"operation is {op.state}")
            # Bind to what was rendered *and* to current recomputed material terms.
            current_hash = quote.compute_hash()
            if not (displayed_quote_hash == ch.quote_hash == op.quote_hash == quote.quote_hash == current_hash):
                raise ApprovalInvalid("quote terms changed; review the new quote", code="quote_changed")
            quote.ensure_fresh(now)
            check_transition(op.state, "approved")
            approval = PurchaseApproval(
                id=new_id(), member_id=principal.member_id, delegation_ref=self._executor_ref(tx, op),
                quote_id=quote.id, quote_hash=current_hash, merchant_id=quote.merchant_id,
                allowed_total=quote.total, nonce=ch.nonce_hash, issued_at=now, expires_at=quote.expires_at,
                assurance_level=principal.assurance_level, method="trusted_surface",
                materiality_rule=MATERIALITY_RULE)
            tx.put("challenges", ch.id, replace(ch, used=True))
            tx.put("approvals", approval.id, approval)
            op = self._transition(tx, op, "approved", approval_id=approval.id)
            self._event(tx, "commerce.purchase.authorized", "PurchaseOperation", op.id, op.version, principal,
                        {"operation_id": op.id, "approval_id": approval.id, "quote_hash": current_hash})
            return approval
        return self.store.run(_tx)

    @staticmethod
    def _executor_ref(tx: Any, op: PurchaseOperation) -> Optional[str]:
        # Only a buy-within-rules delegation may execute; a prepared purchase is
        # completed by the member's own session.
        d = tx.get("delegations", op.delegation_id) if op.delegation_id else None
        return d.id if d is not None and d.mode is AssistanceMode.BUY_WITHIN_RULES else None

    # ------------------------------------------------------ AP2-backed approval
    def register_surface_key(self, principal: Principal, public_jwk: Mapping[str, Any]) -> str:
        """Member registers the trusted-surface device key that signs their AP2 mandates."""
        principal = self._require_first_party(
            principal, "only a reauthenticated member session can register a signing key", "not_trusted_surface")
        # A device key signs real AP2 mandates: simulated identities never qualify.
        if not meets_assurance(principal, "aal2", simulation_ok=False):
            raise Forbidden("only a reauthenticated member session can register a signing key",
                            code="reauthentication_required")
        from jwcrypto.jwk import JWK
        key = JWK(**dict(public_jwk))
        if key.has_private or key.get("kty") != "EC" or key.get("crv") != "P-256":
            raise CommerceError("surface key must be a public EC P-256 JWK", code="invalid_surface_key")
        kid = key.thumbprint()
        public = key.export_public(as_dict=True)
        def _tx(tx):
            self._guard(tx, principal.member_id, ORDERS)
            tx.put("surface_keys", (principal.member_id, kid), public)
        self.store.run(_tx)
        return kid

    def approve_with_ap2(self, principal: Principal, *, operation_id: str, checkout_mandate: str,
                         payment_mandate: str, expected_aud: Optional[str] = None,
                         expected_nonce: Optional[str] = None) -> PurchaseApproval:
        """Map verified AP2 v0.2 closed mandates to an approval bound to the canonical quote hash."""
        from jwcrypto.jwk import JWK
        from . import ap2
        principal, _ = self._authorize(principal, "commerce:cart")
        op = self._own(self.store, "operations", operation_id, principal)
        if op.state != "awaiting_approval":
            raise ApprovalInvalid(f"operation is {op.state}")
        quote = self._quote(self.store, principal, op.quote_id)
        quote.verify_seal()
        now = self.clock()
        quote.ensure_fresh(now)
        conn = self.registry.get(quote.provider_id)
        if conn.protocols.get("ap2") != ap2.AP2_VERSION:
            raise CapabilityUnavailable("provider does not support AP2 v0.2", code="protocol_not_supported")
        merchant_key = conn.merchant_public_keys.get(quote.merchant_id)
        if merchant_key is None:
            raise CapabilityUnavailable("no verified merchant checkout key", code="merchant_key_missing")
        keys = [JWK(**jwk) for jwk in self.store.surface_keys(principal.member_id)]
        last: Optional[Exception] = None
        for user_key in keys:
            try:
                result = ap2.verify_closed_mandates(
                    checkout_mandate=checkout_mandate, payment_mandate=payment_mandate, quote=quote,
                    user_key=user_key, merchant_public_key=merchant_key, now=int(now.timestamp()),
                    expected_aud=expected_aud, expected_nonce=expected_nonce)
                break
            except ap2.Ap2Error as exc:
                last = exc
                if exc.code != "mandate_signature":
                    raise ApprovalInvalid(exc.detail, code=f"ap2_{exc.code}") from None
        else:
            raise ApprovalInvalid("mandate not signed by a registered member key",
                                  code="ap2_" + getattr(last, "code", "no_surface_key"))

        def _tx(tx):
            self._guard(tx, principal.member_id, ORDERS)
            if tx.get("ap2_used", result.checkout_mandate_digest) is not None:
                raise ApprovalInvalid("mandate already used", code="ap2_replay")
            current = tx.get("operations", operation_id)
            if current.state != "awaiting_approval" or quote.compute_hash() != current.quote_hash:
                raise ApprovalInvalid("quote terms changed", code="quote_changed")
            approval = PurchaseApproval(
                id=new_id(), member_id=principal.member_id, delegation_ref=self._executor_ref(tx, current),
                quote_id=quote.id, quote_hash=current.quote_hash, merchant_id=quote.merchant_id,
                allowed_total=quote.total, nonce=result.checkout_hash, issued_at=now, expires_at=quote.expires_at,
                assurance_level="ap2_user_signed", method="ap2_mandate", materiality_rule=MATERIALITY_RULE,
                protocol_payload_hash=result.protocol_payload_hash)
            tx.put("ap2_used", result.checkout_mandate_digest, approval.id)
            tx.put("approvals", approval.id, approval)
            current = self._transition(tx, current, "approved", approval_id=approval.id)
            self._event(tx, "commerce.purchase.authorized", "PurchaseOperation", current.id, current.version,
                        principal, {"operation_id": current.id, "approval_id": approval.id,
                                    "quote_hash": current.quote_hash, "protocol": "ap2/0.2",
                                    "protocol_payload_hash": result.protocol_payload_hash})
            return approval
        return self.store.run(_tx)

    # ---------------------------------------------------------------- execute
    def execute_purchase(self, principal: Principal, *, operation_id: str, approval_id: str,
                         idempotency_key: str) -> PurchaseOperation:
        if not idempotency_key:
            raise InvalidRequest("Idempotency-Key is required", code="idempotency_key_required")
        principal, delegation = self._authorize(principal, "commerce:purchase")
        request = {"operation_id": operation_id, "approval_id": approval_id}
        scope, prior, digest = self._idempotent(principal, "purchase.execute", idempotency_key, request)
        if prior:
            return self.store.get("operations", prior)
        now = self.clock()

        def _tx(tx):
            self._guard(tx, principal.member_id, ORDERS)
            if scope:
                winner = tx.get("idempotency", scope)
                if winner is not None:  # a concurrent duplicate committed first
                    if winner.request_digest != digest:
                        raise IdempotencyConflict("idempotency key reused with a different request")
                    return tx.get("operations", winner.result_ref), None
            op = self._own(tx, "operations", operation_id, principal)
            if op.state != "approved":
                raise ApprovalInvalid(f"operation is {op.state}, not approved")
            approval = tx.get("approvals", approval_id)
            if approval is None or approval.member_id != principal.member_id:
                raise ApprovalInvalid("unknown approval")
            if approval.id != op.approval_id or approval.state != "issued":
                raise ApprovalInvalid("approval is not valid for this operation")
            if approval.delegation_ref != principal.delegation_id:
                raise ApprovalInvalid("approval bound to a different delegation")
            if now >= approval.expires_at:
                raise ApprovalInvalid("approval expired", code="approval_expired")
            quote = self._quote(tx, principal, op.quote_id)
            quote.ensure_fresh(now)
            current_hash = quote.compute_hash()
            if not (approval.quote_hash == op.quote_hash == quote.quote_hash == current_hash):
                raise ApprovalInvalid("approved terms do not match the quote", code="quote_changed")
            # The approval binds the quote, and the quote binds a cart revision: a cart edited
            # after approval is a different purchase.
            cart = tx.get("carts", quote.cart_id)
            if cart is None or cart.revision != quote.cart_revision:
                raise ApprovalInvalid("the cart changed after approval; review a new quote", code="quote_changed")
            if approval.allowed_total != quote.total or approval.merchant_id != quote.merchant_id:
                raise ApprovalInvalid("approved amount or merchant does not match")
            for other in tx.operations_for_quote_hash(op.quote_hash):
                if other.id != op.id and other.state in IN_FLIGHT | {"accepted"}:
                    raise IdempotencyConflict("this quote is already being purchased", code="purchase_in_progress")
            self._require_capability(op.provider_id, "checkout.submit")
            if delegation is not None:
                if delegation.mode is not AssistanceMode.BUY_WITHIN_RULES:
                    raise Forbidden("delegation does not allow purchase execution")
                self._check_grant(delegation, quote)
                self._reserve_budget(tx, delegation, op.id, quote.total)
            tx.put("approvals", approval.id, replace(approval, state="consumed"))
            op = self._transition(tx, op, "submitting", attempts=op.attempts + 1)
            if scope:
                tx.put("idempotency", scope, IdempotencyRecord(scope, digest, op.id, now))
            return op, quote

        op, quote = self.store.run(_tx)
        if quote is None:
            return op
        return self._submit(op, quote, principal)

    def execute_approved_quote(self, principal: Principal, *, quote_id: str, approval_id: str,
                               delegation_id: Optional[str], idempotency_key: str) -> PurchaseOperation:
        """``POST /commerce/purchases`` (contract ``PurchaseRequest``): find the operation the approval was issued for.

        ``delegation_id`` must name the caller's own grant (``null`` for the member's
        own session); it is a consistency check, never a source of authority.
        """
        bound, _ = self._authorize(principal, "commerce:purchase")
        if delegation_id != bound.delegation_id:
            raise Forbidden("delegation does not match the authenticated principal", code="delegation_mismatch")
        approval = self.store.get("approvals", approval_id)
        if approval is None or approval.member_id != bound.member_id or approval.quote_id != quote_id:
            raise ApprovalInvalid("unknown approval for this quote")
        op = next((o for o in self.store.operations_for_quote_hash(approval.quote_hash)
                   if o.approval_id == approval.id and o.member_id == bound.member_id), None)
        if op is None:
            raise ApprovalInvalid("approval is not attached to a purchase")
        return self.execute_purchase(bound, operation_id=op.id, approval_id=approval.id,
                                     idempotency_key=idempotency_key)

    def _submit(self, op: PurchaseOperation, quote: CheckoutQuote, principal: Principal | str) -> PurchaseOperation:
        # Last gate before the side effect: a revocation of the *executing* grant that
        # landed after the reservation must stop unsent work. A member executing their
        # own approved purchase is not stopped by the drafting agent's grant expiring.
        approval = self.store.get("approvals", op.approval_id) if op.approval_id else None
        executing = approval.delegation_ref if approval is not None else op.delegation_id
        if executing:
            d = self.store.get("delegations", executing)
            if d is None or not d.is_active(self.clock()):
                def _cancel(tx):
                    current = tx.get("operations", op.id)
                    # submitting -> cancelled is not a normal edge: nothing was sent.
                    cancelled = replace(current, state="cancelled", reason_code="delegation_revoked",
                                        updated_at=self.clock(), version=current.version + 1)
                    tx.put("operations", op.id, cancelled)
                    self._release_budget(tx, op.id)
                    return cancelled
                return self.store.run(_cancel)
        conn = self.registry.get(op.provider_id)
        adapter: CheckoutProvider = conn.adapter
        try:
            ack = adapter.submit(SubmitRequest(
                idempotency_key=op.provider_idempotency_key, checkout_reference=quote.checkout_reference,
                quote_hash=quote.quote_hash, expected_total=quote.total, payment_token_ref=None,
                lines=tuple(CartLineRequest(l.variant_id, l.source_variant_ref, l.quantity) for l in quote.lines)))
        except ProviderError as exc:
            def _failed(tx):
                current = tx.get("operations", op.id)
                if exc.transmitted or exc.kind is ProviderErrorKind.OUTCOME_UNKNOWN:
                    return self._transition(tx, current, "outcome_unknown", reason=exc.kind.value)
                self._release_budget(tx, op.id)
                return self._transition(tx, current, "rejected", reason=exc.kind.value)
            return self.store.run(_failed)
        except Exception:
            # Unclassified failure after the request may have left: never assume it did not.
            return self.store.run(lambda tx: self._transition(
                tx, tx.get("operations", op.id), "outcome_unknown", reason="unclassified_submit_error"))
        return self._apply_ack(op.id, quote, ack.accepted, ack.provider_order_ref, ack.reason_code,
                               ack.evidence_ref, principal)

    def _apply_ack(self, op_id: str, quote: CheckoutQuote, accepted: bool, order_ref: Optional[str],
                   reason: Optional[str], evidence_ref: Optional[str], actor: Principal | str) -> PurchaseOperation:
        def _tx(tx):
            op = tx.get("operations", op_id)
            if op.state not in ("submitting", "outcome_unknown"):
                return op  # already resolved by a concurrent reconcile/webhook
            if not accepted:
                self._release_budget(tx, op.id)
                return self._transition(tx, op, "rejected", reason=reason or "provider_rejected")
            self._consume_budget(tx, op.id)
            now = self.clock()
            order = Order(
                id=new_id(), member_id=op.member_id, operation_id=op.id, provider_id=op.provider_id,
                merchant_id=quote.merchant_id, provider_order_ref=order_ref or "",
                quote_hash=quote.quote_hash, idempotency_key=op.provider_idempotency_key,
                order_status="accepted", payment_status="unknown", fulfillment_status="unfulfilled",
                lines=tuple(OrderLine(l.variant_id, l.source_variant_ref, l.quantity) for l in quote.lines),
                total=quote.total, refunded_total=Money.zero(quote.currency), last_observed_at=now,
                evidence_refs=(evidence_ref,) if evidence_ref else ())
            tx.put("orders", order.id, order)
            op = self._transition(tx, op, "accepted", order_id=order.id)
            self._order_event(tx, order, actor, effect="incoming")
            return op
        return self.store.run(_tx)

    # ------------------------------------------------------------- reconcile
    def reconcile(self, operation_id: str) -> PurchaseOperation:
        """Worker entrypoint: resolve ``outcome_unknown`` through the provider's own record."""
        op = self.store.get("operations", operation_id)
        if op is None:
            raise NotFound("operation not found")
        if op.state == "submitting" and self.clock() - op.updated_at >= STALE_SUBMITTING:
            # Crash between the durable intent and the provider response: treat as unknown.
            def _stale(tx):
                current = tx.get("operations", op.id)
                if current.state != "submitting":
                    return current
                return self._transition(tx, current, "outcome_unknown", reason="stale_submitting")
            op = self.store.run(_stale)
        if op.state != "outcome_unknown":
            return op
        conn = self.registry.get(op.provider_id)
        provider: OrderProvider = conn.adapter
        quote = self.store.get("quotes", op.quote_id)[1]
        try:
            obs = provider.lookup_by_idempotency_key(op.provider_idempotency_key)
        except ProviderError:
            return op  # still unknown; slower retry lane
        if obs is None:
            # Provider authoritatively has no order for this key.
            return self._apply_ack(op.id, quote, False, None, "not_found_at_provider", None, "system:reconciler")
        op = self._apply_ack(op.id, quote, obs.order_status == "accepted", obs.provider_order_ref,
                             None if obs.order_status == "accepted" else obs.order_status,
                             obs.evidence_ref, "system:reconciler")
        if op.order_id:
            self._apply_observation(op.order_id, obs, "system:reconciler")
        return self.store.get("operations", op.id)

    # --------------------------------------------------------------- webhooks
    def handle_webhook(self, provider_id: str, headers: Mapping[str, str], body: bytes) -> WebhookReceipt:
        conn = self._require_capability(provider_id, "orders.webhook")
        event = conn.adapter.verify_webhook(headers, body)  # raises on bad signature / replay window
        key = (provider_id, event.event_id)

        def _receive(tx):
            existing = tx.get("webhook_receipts", key)
            if existing is not None:
                return existing, False
            receipt = WebhookReceipt(provider_id, event.event_id, event.event_type, self.clock(), "pending_reconcile")
            tx.put("webhook_receipts", key, receipt)
            return receipt, True
        receipt, fresh = self.store.run(_receive)
        if not fresh:
            return receipt
        order = self.store.order_by_provider_ref(provider_id, event.provider_order_ref)
        if order is None:
            # Possibly an order still in outcome_unknown: reconcile that operation.
            for op in self.store.operations_in_state(provider_id, "outcome_unknown"):
                self.reconcile(op.id)
            order = self.store.order_by_provider_ref(provider_id, event.provider_order_ref)
            if order is None:
                return receipt
        # Event order is not trusted: re-read the source of truth and apply monotonically.
        try:
            obs = conn.adapter.lookup(event.provider_order_ref)
        except ProviderError:
            return receipt
        self._apply_observation(order.id, obs, f"provider:{provider_id}")
        applied = replace(receipt, state="applied")
        self.store.run(lambda tx: tx.put("webhook_receipts", key, applied))
        return applied

    def _variant_resolver(self, provider_id: str) -> Callable[[str], Optional[str]]:
        try:
            fn = getattr(self.registry.get(provider_id).adapter, "variant_id_for", None)
        except RegistryError:
            fn = None
        return fn if fn is not None else (lambda _ref: None)

    def _apply_observation(self, order_id: str, obs: OrderObservation, actor: str) -> Order:
        def _tx(tx):
            order = tx.get("orders", order_id)
            resolve = self._variant_resolver(order.provider_id)  # pure lookup, no provider I/O
            by_ref = {l.source_variant_ref: l for l in order.lines}
            new_lines: List[OrderLine] = []
            for ol in obs.lines:
                prev = by_ref.pop(ol.source_variant_ref, None)
                if prev is None:
                    # Exchange creates a new variant relationship; history is retained.
                    new_lines.append(OrderLine(resolve(ol.source_variant_ref), ol.source_variant_ref, ol.quantity_ordered,
                                               ol.quantity_shipped, ol.quantity_delivered,
                                               ol.quantity_returned, ol.exchanged_from_ref, ol.quantity_cancelled))
                    continue
                shipped_ = max(prev.quantity_shipped, min(ol.quantity_shipped, prev.quantity_ordered))
                new_lines.append(replace(
                    prev, quantity_shipped=shipped_,
                    quantity_delivered=max(prev.quantity_delivered, min(ol.quantity_delivered, prev.quantity_ordered)),
                    quantity_returned=max(prev.quantity_returned, min(ol.quantity_returned, prev.quantity_ordered)),
                    # Cancelled units are units that never ship.
                    quantity_cancelled=max(prev.quantity_cancelled,
                                           min(ol.quantity_cancelled, prev.quantity_ordered - shipped_))))
            new_lines.extend(by_ref.values())
            lines = tuple(new_lines)
            payment = order.payment_status
            if _PAYMENT_RANK.get(obs.payment_status, 0) > _PAYMENT_RANK.get(payment, 0):
                payment = obs.payment_status
            refunded = order.refunded_total
            if obs.refunded_total.amount_minor > refunded.amount_minor:
                credit = obs.refunded_total - refunded
                refunded = obs.refunded_total
                self._credit_refund(tx, order, credit)
            if payment != order.payment_status:
                # Money that was authorized but never taken goes back to the grant whatever its refund policy.
                if payment == "voided":
                    self._credit_unspent(tx, order, order.total - refunded)
                elif payment == "captured" and obs.captured_total is not None and obs.captured_total < order.total:
                    self._credit_unspent(tx, order, order.total - obs.captured_total)
            delivered = sum(l.quantity_delivered for l in lines)
            shipped = sum(l.quantity_shipped for l in lines)
            owed = sum(l.quantity_ordered - l.quantity_cancelled for l in lines)
            fulfillment = ("fulfilled" if owed and delivered >= owed else
                           "partially_fulfilled" if shipped or delivered else "unfulfilled")
            order_status = obs.order_status if obs.order_status in ("cancelled",) else order.order_status
            by_line = lambda ls: sorted(ls, key=lambda l: l.source_variant_ref)  # noqa: E731  (stores may reorder)
            changed = (by_line(lines) != by_line(order.lines) or payment != order.payment_status or refunded != order.refunded_total
                       or fulfillment != order.fulfillment_status or order_status != order.order_status)
            if not changed:
                return order
            prev_order = order
            order = replace(order, lines=lines, payment_status=payment, refunded_total=refunded,
                            fulfillment_status=fulfillment, order_status=order_status,
                            last_observed_at=obs.observed_at,
                            evidence_refs=order.evidence_refs + ((obs.evidence_ref,) if obs.evidence_ref else ()),
                            version=order.version + 1)
            tx.put("orders", order.id, order)
            self._mark_returns_received(tx, order.id, prev_order.lines, lines)
            op = tx.get("operations", order.operation_id)
            target = self._summary_state(order)
            if target != op.state:
                try:
                    check_transition(op.state, target)
                    self._transition(tx, op, target)
                except CommerceError:
                    pass  # summary state is advisory; order facts above are authoritative
            previous_refs = {l.source_variant_ref for l in prev_order.lines}
            exchanged = any(l.exchanged_from_ref and l.source_variant_ref not in previous_refs for l in lines)
            effect = ("exchanged" if exchanged
                      else "returned" if sum(l.quantity_returned for l in lines) > sum(l.quantity_returned for l in prev_order.lines)
                      else "cancelled" if sum(l.quantity_cancelled for l in lines) > sum(l.quantity_cancelled for l in prev_order.lines)
                      else "arrived" if delivered > sum(l.quantity_delivered for l in prev_order.lines)
                      else "updated")
            self._order_event(tx, order, actor, effect=effect)
            return order
        return self.store.run(_tx)

    @staticmethod
    def _summary_state(order: Order) -> str:
        if order.order_status == "cancelled":
            return "refunded" if order.payment_status == "refunded" else "cancelled"
        if order.payment_status == "voided":
            return "cancelled"
        if order.payment_status == "refunded":
            return "refunded"
        if order.payment_status == "partially_refunded":
            return "partially_refunded"
        if order.fulfillment_status == "fulfilled":
            return "fulfilled"
        if order.fulfillment_status == "partially_fulfilled":
            return "partially_fulfilled"
        return "accepted"

    def _order_event(self, tx: Any, order: Order, actor: Principal | str, *, effect: str) -> None:
        """Wardrobe lane reduces these into "On the way"/arrived/returned entries."""
        self._event(tx, "commerce.order.observed", "Order", order.id, order.version, actor, {
            "order_id": order.id, "operation_id": order.operation_id,
            "member_id": order.member_id, "provider_id": order.provider_id,
            "order_status": order.order_status, "payment_status": order.payment_status,
            "fulfillment_status": order.fulfillment_status, "wardrobe_effect": effect,
            "lines": [{"variant_id": l.variant_id, "source_variant_ref": l.source_variant_ref,
                       "ordered": l.quantity_ordered, "shipped": l.quantity_shipped,
                       "delivered": l.quantity_delivered, "returned": l.quantity_returned,
                       "cancelled": l.quantity_cancelled, "exchanged_from_ref": l.exchanged_from_ref}
                      for l in order.lines],
            "acquisition_evidence": list(order.evidence_refs),
        })

    # ---------------------------------------------------------------- returns
    def request_return(self, principal: Principal, order_id: str, source_variant_ref: str,
                       quantity: int, *, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Ask the provider to accept a return. A return request is not a refund.

        The intent and its idempotency record commit before provider I/O, so a
        retried request with the same key never reaches the provider twice.
        Units already being returned count against what can be returned.
        """
        principal, d = self._authorize(principal, "commerce:purchase")
        order = self._own(self.store, "orders", order_id, principal)
        if d is not None:
            placed_by = self.store.get("operations", order.operation_id)
            if (d.mode is not AssistanceMode.BUY_WITHIN_RULES or placed_by is None
                    or placed_by.delegation_id != d.id or order.provider_id not in d.allowed_providers):
                raise Forbidden("an agent can only return orders placed under its own grant", code="order_not_yours")
        request = {"order_id": order_id, "source_variant_ref": source_variant_ref, "quantity": quantity}
        scope, prior, digest = self._idempotent(principal, "order.return", idempotency_key, request)
        if prior:
            return self._return_wire(self.store.get("returns", prior), order)
        conn = self.registry.get(order.provider_id)
        handoff = not conn.can_execute("returns.request")
        now = self.clock()
        record = ReturnRequest(id=new_id(), order_id=order.id, member_id=order.member_id,
                               source_variant_ref=source_variant_ref, quantity=quantity,
                               status="handoff" if handoff else "return_requested", requested_at=now)

        def _intent(tx):
            self._guard(tx, principal.member_id, ORDERS)
            if scope:
                winner = tx.get("idempotency", scope)
                if winner is not None:
                    return tx.get("returns", winner.result_ref), False
            current = tx.get("orders", order.id)
            line = next((l for l in current.lines if l.source_variant_ref == source_variant_ref), None)
            pending = sum(r.quantity for r in tx.returns_for_order(order.id)
                          if r.source_variant_ref == source_variant_ref and r.status == "return_requested")
            if line is None or not 1 <= quantity <= line.quantity_ordered - line.quantity_returned - pending:
                raise InvalidQuote("invalid return line or quantity (including returns already requested)")
            if scope:
                tx.put("idempotency", scope, IdempotencyRecord(scope, digest, record.id, now))
            tx.put("returns", record.id, record)
            return record, True

        saved, fresh = self.store.run(_intent)
        if not fresh or handoff:
            return self._return_wire(saved, order, conn)
        adapter: ReturnsProvider = conn.adapter
        try:
            result = adapter.request_return(order.provider_order_ref, source_variant_ref, quantity)  # outside txn
        except ProviderError as exc:
            if not (exc.transmitted or exc.kind is ProviderErrorKind.OUTCOME_UNKNOWN):
                self.store.run(lambda tx: tx.put("returns", saved.id, replace(saved, status="rejected")))
            raise
        done = replace(saved, provider_reference=result.source_reference)

        def _tx(tx):
            tx.put("returns", done.id, done)
            op = tx.get("operations", order.operation_id)
            try:
                self._transition(tx, op, "return_requested")
            except CommerceError:
                pass
        self.store.run(_tx)
        return self._return_wire(done, order, conn)

    @staticmethod
    def _return_wire(rr: ReturnRequest, order: Order, conn: Any = None) -> Dict[str, Any]:
        if rr.status == "handoff":
            return {"status": "handoff", "return_id": rr.id,
                    "reason_code": conn.capability("returns.request").reason_code if conn else "handoff",
                    "detail": "Start the return with the retailer; Brand.Me will update when evidence arrives."}
        return {"status": rr.status, "return_id": rr.id, "provider_reference": rr.provider_reference}

    @staticmethod
    def _mark_returns_received(tx: Any, order_id: str, before: Sequence[OrderLine], after: Sequence[OrderLine]) -> None:
        returned_before = {l.source_variant_ref: l.quantity_returned for l in before}
        for l in after:
            delta = l.quantity_returned - returned_before.get(l.source_variant_ref, 0)
            if delta <= 0:
                continue
            for rr in sorted(tx.returns_for_order(order_id), key=lambda r: r.requested_at):
                if delta <= 0:
                    break
                if rr.source_variant_ref == l.source_variant_ref and rr.status == "return_requested" \
                        and rr.quantity <= delta:
                    tx.put("returns", rr.id, replace(rr, status="received"))
                    delta -= rr.quantity

    # ----------------------------------------------------------------- budget
    def available_budget(self, delegation: AgentDelegation, reader: Any = None) -> Money:
        limits = delegation.limits
        if limits is None:
            return Money.zero("USD")
        window_start = self.clock() - timedelta(seconds=limits.window_seconds)
        spent = 0
        for e in (reader or self.store).budget_entries(delegation.id):
            if e.created_at < window_start:
                continue
            if e.kind == "reservation" and e.state in ("reserved", "consumed"):
                spent += e.amount.amount_minor
            elif e.kind == "credit" and e.state == "credited":
                spent -= e.amount.amount_minor
        return Money(max(0, limits.max_cumulative.amount_minor - max(0, spent)), limits.currency)

    def _reserve_budget(self, tx: Any, delegation: AgentDelegation, op_id: str, amount: Money) -> None:
        # Inside the transaction: the availability read and the reservation write are atomic.
        if amount.amount_minor == 0:
            return  # nothing to reserve; the ledger only records positive amounts
        if amount > self.available_budget(delegation, tx):
            raise BudgetExceeded("purchase exceeds the remaining delegated budget")
        e = BudgetEntry(new_id(), delegation.id, op_id, amount, "reservation", "reserved", self.clock())
        tx.put("reservations", (e.delegation_id, e.id), e)

    @staticmethod
    def _set_reservation_state(tx: Any, op_id: str, to_state: str) -> None:
        for e in tx.budget_entries_for_operation(op_id):
            if e.kind == "reservation" and e.state == "reserved":
                tx.put("reservations", (e.delegation_id, e.id), replace(e, state=to_state))

    def _release_budget(self, tx: Any, op_id: str) -> None:
        self._set_reservation_state(tx, op_id, "released")

    def _consume_budget(self, tx: Any, op_id: str) -> None:
        self._set_reservation_state(tx, op_id, "consumed")

    def _credit_unspent(self, tx: Any, order: Order, amount: Money) -> None:
        """Authorized but never captured (void, expired hold, reduced capture): not a refund, never spent."""
        op = tx.get("operations", order.operation_id)
        if not op.delegation_id or amount.amount_minor <= 0:
            return
        d = tx.get("delegations", op.delegation_id)
        if d is None or d.limits is None:
            return
        e = BudgetEntry(new_id(), d.id, op.id, amount, "credit", "credited", self.clock())
        tx.put("reservations", (e.delegation_id, e.id), e)

    def _credit_refund(self, tx: Any, order: Order, amount: Money) -> None:
        op = tx.get("operations", order.operation_id)
        if not op.delegation_id:
            return
        d = tx.get("delegations", op.delegation_id)
        if d is None or d.limits is None or not d.limits.refund_credit_back:
            return
        e = BudgetEntry(new_id(), d.id, op.id, amount, "credit", "credited", self.clock())
        tx.put("reservations", (e.delegation_id, e.id), e)

    # ------------------------------------------------------------------ grant
    @staticmethod
    def _check_grant(d: AgentDelegation, quote: CheckoutQuote) -> None:
        if quote.provider_id not in d.allowed_providers:
            raise Forbidden("provider not allowed by delegation")
        limits = d.limits
        if limits is None:
            raise Forbidden("delegation has no purchase limits")
        if quote.currency != limits.currency:
            raise DelegationInvalid("currency differs from the grant; new approval required", code="currency_mismatch")
        if quote.merchant_id not in limits.allowed_merchants:
            raise Forbidden("merchant not allowed by delegation")
        if quote.total > limits.max_per_order:
            raise BudgetExceeded("order total exceeds the per-order limit")
        for line in quote.lines:
            if line.category in DEFAULT_EXCLUDED_CATEGORIES:
                raise Forbidden("category excluded from the fashion purchase scope")
            if limits.allowed_categories and line.category not in limits.allowed_categories:
                raise Forbidden("category not allowed by delegation")
            if limits.allowed_variant_refs and line.source_variant_ref not in limits.allowed_variant_refs:
                raise Forbidden("variant not allowed by delegation")
        if limits.delivery_ref and quote.delivery_ref != limits.delivery_ref:
            raise Forbidden("delivery choice not allowed by delegation")
        if limits.require_returnable and not quote.terms.returnable:
            raise Forbidden("delegation requires returnable items")

    # ------------------------------------------------------------- internals
    def _transition(self, tx: Any, op: PurchaseOperation, new_state: str, *, reason: Optional[str] = None,
                    **changes: Any) -> PurchaseOperation:
        check_transition(op.state, new_state)
        op = replace(op, state=new_state, updated_at=self.clock(), version=op.version + 1,
                     reason_code=reason if reason is not None else op.reason_code, **changes)
        tx.put("operations", op.id, op)
        return op

    @staticmethod
    def _void_approval(tx: Any, approval_id: Optional[str]) -> None:
        if approval_id:
            a = tx.get("approvals", approval_id)
            if a is not None and a.state == "issued":
                tx.put("approvals", a.id, replace(a, state="void"))

    def _is_simulation(self, provider_id: str) -> bool:
        try:
            return bool(self.registry.get(provider_id).simulation)
        except RegistryError:
            return False

    # ------------------------------------------------------------ operator queue
    OPERATOR_SCOPE = "commerce:operator"

    def operator_queue(self, principal: Principal) -> Dict[str, Any]:
        """Purchases that need attention, for ``/commerce/operations``. No member identifiers.

        An operator role is never implied by a member session. Reconciliation
        itself runs in the worker (``reconcile``); this is a read-only view.
        """
        if principal.environment != self.environment:
            raise Forbidden("principal environment mismatch")
        if self.OPERATOR_SCOPE not in principal.scopes:
            raise Forbidden(f"scope {self.OPERATOR_SCOPE} required", code="insufficient_scope")
        now = self.clock()

        def item(o: PurchaseOperation) -> Dict[str, Any]:
            return {"operation_id": o.id, "provider_id": o.provider_id, "state": o.state,
                    "reason_code": o.reason_code, "attempts": o.attempts,
                    "age_seconds": int((now - o.updated_at).total_seconds()),
                    "updated_at": o.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ")}

        unknown = [item(o) for o in self.store.operations_by_state("outcome_unknown")]
        stale = [item(o) for o in self.store.operations_by_state("submitting")
                 if now - o.updated_at >= STALE_SUBMITTING]
        hooks = [{"provider_id": r.provider_id, "event_type": r.event_type,
                  "age_seconds": int((now - r.received_at).total_seconds())}
                 for r in self.store.webhook_receipts_pending()]
        return {"environment": self.environment, "observed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "outcome_unknown": unknown, "stale_submitting": stale, "webhooks_pending": hooks}

    # ----------------------------------------------------------- privacy jobs
    # Driven by the My Data deletion orchestrator through ``privacy_handler``; it has already
    # reauthenticated the member. Financial evidence — orders, the approvals and grants behind
    # them, and anything still settling — is retained (ch.03 §8).
    PRIVACY_ACTOR = "system:privacy"

    def _cancel_unsent(self, tx: Any, op: PurchaseOperation, reason: str) -> PurchaseOperation:
        if op.state in ("draft", "quoting", "awaiting_approval", "approved"):
            op = self._transition(tx, op, "cancelled", reason=reason)
            self._release_budget(tx, op.id)
            self._void_approval(tx, op.approval_id)
        return op

    # Each category's erasure is self-contained: the privacy orchestrator runs categories in
    # request order and replays tombstones in any order. Counts: ``settling`` rows wait for a
    # provider outcome (the job stays open); ``kept`` rows are permanent evidence of an order.
    def _erase_agent_grants(self, tx: Any, member_id: str) -> Dict[str, int]:
        counts = {"revoked": 0, "deleted": 0, "kept": 0, "settling": 0}
        for d in tx.for_member("delegations", member_id):
            if d.revoked_at is None:
                d = replace(d, revoked_at=self.clock(), version=d.version + 1)
                tx.put("delegations", d.id, d)
                for op in tx.operations_for_delegation(d.id):
                    self._cancel_unsent(tx, op, "member_data_deleted")
                self._event(tx, "commerce.delegation.revoked", "AgentDelegation", d.id, d.version,
                            self.PRIVACY_ACTOR, {"delegation_id": d.id})
                counts["revoked"] += 1
            ops = tx.operations_for_delegation(d.id)
            if any(op.state in IN_FLIGHT for op in ops):
                counts["settling"] += 1
                continue
            if any(op.order_id is not None for op in ops):
                counts["kept"] += 1  # purchase authority behind an order stays, revoked
                continue
            for e in tx.budget_entries(d.id):
                tx.delete("reservations", (e.delegation_id, e.id))
            tx.delete("delegations", d.id)
            counts["deleted"] += 1
        return counts

    def _erase_carts_and_quotes(self, tx: Any, member_id: str) -> Dict[str, int]:
        counts = {"carts": 0, "quotes": 0, "challenges": 0, "kept": 0, "settling": 0}
        held: Dict[str, str] = {}  # quote_id -> "kept" | "settling"
        for op in tx.for_member("operations", member_id):
            op = self._cancel_unsent(tx, op, "member_data_deleted")
            if op.state in IN_FLIGHT:
                held[op.quote_id] = "settling"
            elif op.order_id is not None:
                held.setdefault(op.quote_id, "kept")
        for c in tx.for_member("carts", member_id):
            tx.delete("carts", c.id)
            counts["carts"] += 1
        for _, q in tx.for_member("quotes", member_id):
            if q.id in held:
                counts[held[q.id]] += 1
            else:
                tx.delete("quotes", q.id)
                counts["quotes"] += 1
        for ch in tx.for_member("challenges", member_id):
            tx.delete("challenges", ch.id)
            counts["challenges"] += 1
        return counts

    def _erase_order_side_data(self, tx: Any, member_id: str) -> Dict[str, int]:
        """Orders are kept; device keys, order-less purchases and spent idempotency keys go."""
        counts = {"surface_keys": 0, "operations": 0, "approvals": 0, "idempotency": 0,
                  "retained": 0, "settling": 0}
        for key in tx.surface_key_ids(member_id):
            tx.delete("surface_keys", key)
            counts["surface_keys"] += 1
        guarded = set()  # purchases still settling with a provider
        for op in tx.for_member("operations", member_id):
            op = self._cancel_unsent(tx, op, "member_data_deleted")
            if op.state in IN_FLIGHT:
                guarded.add(op.id)
                counts["settling"] += 1
                continue
            if op.order_id is not None:
                counts["retained"] += 1
                continue
            if op.approval_id:
                tx.delete("approvals", op.approval_id)
                counts["approvals"] += 1
            tx.delete("operations", op.id)
            counts["operations"] += 1
        for rec in tx.for_member("idempotency", member_id):
            # Never expire a key while a remote side effect can still settle (ch.03 §6).
            if rec.result_ref not in guarded:
                tx.delete("idempotency", rec.scope)
                counts["idempotency"] += 1
        return counts

    # Store-level entry points (the in-memory store and ops tooling); the privacy handler
    # runs the same functions inside the orchestrator's transaction.
    def erase_agent_grants(self, member_id: str) -> Dict[str, int]:
        return self.store.run(lambda tx: self._erase_agent_grants(tx, member_id))

    def erase_carts_and_quotes(self, member_id: str) -> Dict[str, int]:
        return self.store.run(lambda tx: self._erase_carts_and_quotes(tx, member_id))

    def erase_order_side_data(self, member_id: str) -> Dict[str, int]:
        return self.store.run(lambda tx: self._erase_order_side_data(tx, member_id))

    def get_operation(self, principal: Principal, operation_id: str) -> PurchaseOperation:
        principal, _ = self._authorize(principal, "commerce:research")
        return self._own(self.store, "operations", operation_id, principal)

    def get_order(self, principal: Principal, order_id: str) -> Order:
        principal, _ = self._authorize(principal, "commerce:research")
        return self._own(self.store, "orders", order_id, principal)
