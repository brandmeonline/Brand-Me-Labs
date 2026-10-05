"""Commerce application service (ch.05 §5–§6, ch.03 §5–§6).

Invariants enforced here:

* Identity comes only from ``Principal``; no method accepts a member/user id.
* An agent can research and prepare carts; it cannot approve, and it can only
  execute a purchase that a first-party trusted surface approved for the exact
  canonical quote hash.
* Budget reservation, approval consumption, idempotency record and the durable
  submission intent commit in one transaction *before* provider network I/O.
* A transmitted-but-unanswered submission becomes ``outcome_unknown`` and is
  reconciled through the same provider idempotency key; it is never blindly
  re-sent and the same quote cannot be purchased again meanwhile.
* Order, payment and fulfillment facts stay separate; webhooks are verified,
  deduplicated, and applied by re-reading the source of truth.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import rfc8785

from brandme_core.domains.providers.contracts import (
    CartLineRequest, CheckoutProvider, OrderObservation, OrderProvider, ProviderError,
    ProviderErrorKind, ReturnsProvider, SubmitRequest,
)
from brandme_core.domains.providers.registry import ProviderRegistry, RegistryError

from .delegation import (
    DEFAULT_EXCLUDED_CATEGORIES, AgentDelegation, AssistanceMode, DelegationLimits, build_delegation,
)
from .errors import (
    ApprovalInvalid, BudgetExceeded, CapabilityUnavailable, CommerceError, DelegationInvalid,
    Forbidden, IdempotencyConflict, InvalidQuote, NotFound, VersionConflict,
)
from .money import Money, sum_money
from .principal import Principal
from .quote import MATERIALITY_RULE, CheckoutQuote, QuoteLine
from .records import (
    IN_FLIGHT, ApprovalChallenge, BudgetEntry, Cart, IdempotencyRecord, Order, OrderLine,
    PurchaseApproval, PurchaseOperation, WebhookReceipt, check_transition,
)
from .store import InMemoryCommerceStore, OutboxEvent, new_id

Clock = Callable[[], datetime]

APPROVAL_CHALLENGE_TTL = timedelta(minutes=5)
MAX_CART_LINES = 50
_AAL = {"aal1": 1, "aal2": 2, "aal3": 3}
_PAYMENT_RANK = {"unknown": 0, "authorized": 1, "captured": 2, "partially_refunded": 3, "refunded": 4}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _digest(doc: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(doc)).hexdigest()


class CommerceService:
    def __init__(self, *, store: InMemoryCommerceStore, registry: ProviderRegistry,
                 environment: str, clock: Clock = _utcnow,
                 approval_requires_assurance: str = "aal2"):
        self.store = store
        self.registry = registry
        self.environment = environment
        self.clock = clock
        self.approval_requires_assurance = approval_requires_assurance

    # ------------------------------------------------------------------ utils
    def _event(self, event_type: str, aggregate_type: str, aggregate_id: str, version: int,
               actor: Principal | str, payload: Dict[str, Any], correlation_id: Optional[str] = None,
               privacy_class: str = "member_private") -> None:
        actor_ref = actor if isinstance(actor, str) else (
            f"member:{actor.member_id}" if not actor.is_agent else f"client:{actor.client_id}")
        self.store.emit(OutboxEvent(
            event_id=new_id(), event_type=event_type, schema_version="1",
            aggregate_type=aggregate_type, aggregate_id=aggregate_id, aggregate_version=version,
            occurred_at=self.clock(), environment=self.environment, actor_ref=actor_ref,
            correlation_id=correlation_id or new_id(), causation_id=None,
            privacy_class=privacy_class, payload=payload))

    def _require_env(self, principal: Principal) -> None:
        if principal.environment != self.environment:
            raise Forbidden("principal environment mismatch")

    def _require_scope(self, principal: Principal, scope: str) -> None:
        if not principal.has_scope(scope):
            raise Forbidden(f"missing scope {scope}", code="insufficient_scope")

    def _active_delegation(self, principal: Principal) -> Optional[AgentDelegation]:
        """Agents must act through an active delegation; first-party sessions need none."""
        if principal.delegation_id is None:
            if principal.is_agent:
                raise DelegationInvalid("agent principal without delegation")
            return None
        d = self.store.get("delegations", principal.delegation_id)
        if d is None:
            raise DelegationInvalid("unknown delegation")
        d.require_active_for(principal, self.clock())
        return d

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

    def _own(self, table: str, key: str, principal: Principal) -> Any:
        row = self.store.get(table, key)
        # 404 for someone else's object: do not reveal existence.
        if row is None or getattr(row, "member_id", None) != principal.member_id:
            raise NotFound(f"{table[:-1]} not found")
        return row

    def _idempotent(self, principal: Principal, operation: str, key: Optional[str],
                    request: Mapping[str, Any]) -> Tuple[Optional[Tuple], Optional[str], str]:
        digest = _digest(dict(request))
        if not key:
            return None, None, digest
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
        self._require_env(principal)
        d = build_delegation(granting=principal, delegation_id=new_id(), client_id=client_id,
                             mode=mode, allowed_providers=frozenset(allowed_providers),
                             limits=limits, now=self.clock(), expires_at=expires_at)
        with self.store.transaction():
            self.store.put("delegations", d.id, d)
            self._event("delegation.created", "AgentDelegation", d.id, 1, principal,
                        {"delegation_id": d.id, "mode": d.mode.value, "client_id": client_id})
        return d

    def revoke_delegation(self, principal: Principal, delegation_id: str) -> AgentDelegation:
        if principal.is_agent:
            raise Forbidden("agents cannot revoke delegations")
        with self.store.transaction():
            d = self._own("delegations", delegation_id, principal)
            if d.revoked_at is not None:
                return d
            now = self.clock()
            d = replace(d, revoked_at=now, version=d.version + 1)
            self.store.put("delegations", d.id, d)
            # Cancel unsent work immediately; submitted work keeps reconciling.
            for op in self.store.rows("operations"):
                if op.delegation_id == d.id and op.state in ("draft", "quoting", "awaiting_approval", "approved"):
                    self._transition(op, "cancelled", reason="delegation_revoked")
                    self._release_budget(op.id)
                    self._void_approval(op.approval_id)
            self._event("delegation.revoked", "AgentDelegation", d.id, d.version, principal,
                        {"delegation_id": d.id})
        return d

    # ------------------------------------------------------------------ carts
    def create_cart(self, principal: Principal, *, provider_id: str, merchant_id: str,
                    lines: Sequence[CartLineRequest], idempotency_key: Optional[str] = None) -> Cart:
        self._require_env(principal)
        self._require_scope(principal, "commerce:cart")
        d = self._active_delegation(principal)
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
                    lines=tuple(lines), revision=1, created_by_client=principal.client_id)
        with self.store.transaction():
            if scope:
                if self.store.get("idempotency", scope):  # lost a race: return the winner
                    return self.store.get("carts", self.store.get("idempotency", scope).result_ref)
                self.store.put("idempotency", scope, IdempotencyRecord(scope, digest, cart.id, self.clock()))
            self.store.put("carts", cart.id, cart)
        return cart

    def update_cart(self, principal: Principal, cart_id: str, *, if_match: int,
                    lines: Sequence[CartLineRequest]) -> Cart:
        self._require_scope(principal, "commerce:cart")
        self._active_delegation(principal)
        self._validate_lines(lines)
        cart = self._own("carts", cart_id, principal)
        if cart.revision != if_match:
            raise VersionConflict("cart revision changed")
        conn = self._require_capability(cart.provider_id, "cart.update")
        # Full replacement semantics normalized here, protected by the revision check.
        conn.adapter.replace_cart(cart.provider_cart_ref, list(lines))
        with self.store.transaction():
            current = self.store.get("carts", cart_id)
            if current.revision != if_match:
                raise VersionConflict("cart revision changed")
            cart = replace(current, lines=tuple(lines), revision=current.revision + 1, status="draft")
            self.store.put("carts", cart.id, cart)
        return cart

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
        self._require_scope(principal, "commerce:cart")
        self._active_delegation(principal)
        cart = self._own("carts", cart_id, principal)
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
        with self.store.transaction():
            current = self.store.get("carts", cart.id)
            if current.revision != cart.revision:
                raise VersionConflict("cart changed while quoting")
            self.store.put("quotes", quote.id, (principal.member_id, quote))
            self.store.put("carts", cart.id, replace(current, status="quoted"))
            self._event("commerce.quote.ready", "CheckoutQuote", quote.id, 1, principal,
                        {"quote_id": quote.id, "quote_hash": quote.quote_hash, "cart_id": cart.id})
        return quote

    def get_quote(self, principal: Principal, quote_id: str) -> CheckoutQuote:
        row = self.store.get("quotes", quote_id)
        if row is None or row[0] != principal.member_id:
            raise NotFound("quote not found")
        return row[1]

    # -------------------------------------------------------- purchase request
    def request_purchase(self, principal: Principal, quote_id: str) -> PurchaseOperation:
        """Agent or member asks for approval. Creates no approval, spends nothing."""
        self._require_scope(principal, "commerce:cart")
        d = self._active_delegation(principal)
        quote = self.get_quote(principal, quote_id)
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
            client_id=principal.client_id, quote_id=quote.id, quote_hash=quote.quote_hash,
            approval_id=None, provider_id=quote.provider_id, state="awaiting_approval",
            provider_idempotency_key="bm-" + secrets.token_hex(16), created_at=now, updated_at=now)
        with self.store.transaction():
            self.store.put("operations", op.id, op)
            self._event("commerce.purchase.approval_requested", "PurchaseOperation", op.id, 1, principal,
                        {"operation_id": op.id, "quote_id": quote.id})
        return op

    # ------------------------------------------------- trusted approval surface
    def open_approval_challenge(self, principal: Principal, operation_id: str) -> ApprovalChallenge:
        """Rendered only by Brand.Me's deterministic approval UI (AP2 trusted surface)."""
        if principal.is_agent:
            raise Forbidden("only the member's trusted surface can open an approval", code="not_trusted_surface")
        op = self._own("operations", operation_id, principal)
        if op.state != "awaiting_approval":
            raise ApprovalInvalid(f"operation is {op.state}")
        quote = self.get_quote(principal, op.quote_id)
        quote.verify_seal()
        now = self.clock()
        quote.ensure_fresh(now)
        ch = ApprovalChallenge(id=new_id(), member_id=principal.member_id, quote_id=quote.id,
                               quote_hash=quote.quote_hash, nonce=secrets.token_urlsafe(24),
                               delegation_ref=op.delegation_id, issued_at=now,
                               expires_at=min(quote.expires_at, now + APPROVAL_CHALLENGE_TTL))
        with self.store.transaction():
            self.store.put("challenges", ch.id, ch)
        return ch

    def approve(self, principal: Principal, *, operation_id: str, challenge_id: str, nonce: str,
                displayed_quote_hash: str) -> PurchaseApproval:
        if principal.is_agent:
            raise Forbidden("agents cannot approve purchases", code="not_trusted_surface")
        if _AAL.get(principal.assurance_level, 0) < _AAL[self.approval_requires_assurance]:
            raise ApprovalInvalid("reauthentication required", code="reauthentication_required")
        now = self.clock()
        with self.store.transaction():
            op = self._own("operations", operation_id, principal)
            ch = self._own("challenges", challenge_id, principal)
            quote = self.get_quote(principal, op.quote_id)
            if ch.used or now >= ch.expires_at:
                raise ApprovalInvalid("approval challenge expired or used")
            if not secrets.compare_digest(ch.nonce, nonce):
                raise ApprovalInvalid("approval nonce mismatch")
            if ch.quote_id != op.quote_id:
                raise ApprovalInvalid("challenge is for a different quote")
            # Bind to what was rendered *and* to current recomputed material terms.
            current_hash = quote.compute_hash()
            if not (displayed_quote_hash == ch.quote_hash == op.quote_hash == quote.quote_hash == current_hash):
                raise ApprovalInvalid("quote terms changed; review the new quote", code="quote_changed")
            quote.ensure_fresh(now)
            check_transition(op.state, "approved")
            # Only a buy-within-rules delegation may execute; a prepared purchase is
            # completed by the member's own session.
            d = self.store.get("delegations", op.delegation_id) if op.delegation_id else None
            executor_ref = d.id if d is not None and d.mode is AssistanceMode.BUY_WITHIN_RULES else None
            approval = PurchaseApproval(
                id=new_id(), member_id=principal.member_id, delegation_ref=executor_ref,
                quote_id=quote.id, quote_hash=current_hash, merchant_id=quote.merchant_id,
                allowed_total=quote.total, nonce=ch.nonce, issued_at=now, expires_at=quote.expires_at,
                assurance_level=principal.assurance_level, method="trusted_surface",
                materiality_rule=MATERIALITY_RULE)
            self.store.put("challenges", ch.id, replace(ch, used=True))
            self.store.put("approvals", approval.id, approval)
            self._transition(op, "approved", approval_id=approval.id)
            self._event("commerce.purchase.authorized", "PurchaseOperation", op.id, op.version + 1, principal,
                        {"operation_id": op.id, "approval_id": approval.id, "quote_hash": current_hash})
        return approval

    # ------------------------------------------------------ AP2-backed approval
    def register_surface_key(self, principal: Principal, public_jwk: Mapping[str, Any]) -> str:
        """Member registers the trusted-surface device key that signs their AP2 mandates."""
        if principal.is_agent or _AAL.get(principal.assurance_level, 0) < _AAL["aal2"]:
            raise Forbidden("only a reauthenticated member session can register a signing key")
        from jwcrypto.jwk import JWK
        key = JWK(**dict(public_jwk))
        if key.has_private or key.get("kty") != "EC" or key.get("crv") != "P-256":
            raise CommerceError("surface key must be a public EC P-256 JWK", code="invalid_surface_key")
        kid = key.thumbprint()
        with self.store.transaction():
            self.store.put("surface_keys", (principal.member_id, kid), key.export_public(as_dict=True))
        return kid

    def approve_with_ap2(self, principal: Principal, *, operation_id: str, checkout_mandate: str,
                         payment_mandate: str, expected_aud: Optional[str] = None,
                         expected_nonce: Optional[str] = None) -> PurchaseApproval:
        """Map verified AP2 v0.2 closed mandates to an approval bound to the canonical quote hash."""
        from jwcrypto.jwk import JWK
        from . import ap2
        op = self._own("operations", operation_id, principal)
        if op.state != "awaiting_approval":
            raise ApprovalInvalid(f"operation is {op.state}")
        quote = self.get_quote(principal, op.quote_id)
        quote.verify_seal()
        now = self.clock()
        quote.ensure_fresh(now)
        conn = self.registry.get(quote.provider_id)
        if conn.protocols.get("ap2") != ap2.AP2_VERSION:
            raise CapabilityUnavailable("provider does not support AP2 v0.2", code="protocol_not_supported")
        merchant_key = conn.merchant_public_keys.get(quote.merchant_id)
        if merchant_key is None:
            raise CapabilityUnavailable("no verified merchant checkout key", code="merchant_key_missing")
        keys = [JWK(**self.store.get("surface_keys", k)) for k in self.store.keys("surface_keys")
                if k[0] == principal.member_id]
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
        with self.store.transaction():
            if self.store.get("ap2_used", result.checkout_mandate_digest) is not None:
                raise ApprovalInvalid("mandate already used", code="ap2_replay")
            op = self.store.get("operations", operation_id)
            if op.state != "awaiting_approval" or quote.compute_hash() != op.quote_hash:
                raise ApprovalInvalid("quote terms changed", code="quote_changed")
            d = self.store.get("delegations", op.delegation_id) if op.delegation_id else None
            executor_ref = d.id if d is not None and d.mode is AssistanceMode.BUY_WITHIN_RULES else None
            approval = PurchaseApproval(
                id=new_id(), member_id=principal.member_id, delegation_ref=executor_ref, quote_id=quote.id,
                quote_hash=op.quote_hash, merchant_id=quote.merchant_id, allowed_total=quote.total,
                nonce=result.checkout_hash, issued_at=now, expires_at=quote.expires_at,
                assurance_level="ap2_user_signed", method="ap2_mandate", materiality_rule=MATERIALITY_RULE,
                protocol_payload_hash=result.protocol_payload_hash)
            self.store.put("ap2_used", result.checkout_mandate_digest, approval.id)
            self.store.put("approvals", approval.id, approval)
            self._transition(op, "approved", approval_id=approval.id)
            self._event("commerce.purchase.authorized", "PurchaseOperation", op.id, op.version + 1, principal,
                        {"operation_id": op.id, "approval_id": approval.id, "quote_hash": op.quote_hash,
                         "protocol": "ap2/0.2", "protocol_payload_hash": result.protocol_payload_hash})
        return approval

    # ---------------------------------------------------------------- execute
    def execute_purchase(self, principal: Principal, *, operation_id: str, approval_id: str,
                         idempotency_key: str) -> PurchaseOperation:
        if not idempotency_key:
            raise CommerceError("Idempotency-Key is required", code="idempotency_key_required")
        self._require_scope(principal, "commerce:purchase")
        request = {"operation_id": operation_id, "approval_id": approval_id}
        scope, prior, digest = self._idempotent(principal, "purchase.execute", idempotency_key, request)
        if prior:
            return self.store.get("operations", prior)

        delegation = self._active_delegation(principal)
        now = self.clock()
        with self.store.transaction():
            op = self._own("operations", operation_id, principal)
            if op.state != "approved":
                raise ApprovalInvalid(f"operation is {op.state}, not approved")
            approval = self.store.get("approvals", approval_id)
            if approval is None or approval.member_id != principal.member_id:
                raise ApprovalInvalid("unknown approval")
            if approval.id != op.approval_id or approval.state != "issued":
                raise ApprovalInvalid("approval is not valid for this operation")
            if approval.delegation_ref != principal.delegation_id:
                raise ApprovalInvalid("approval bound to a different delegation")
            if now >= approval.expires_at:
                raise ApprovalInvalid("approval expired", code="approval_expired")
            quote = self.get_quote(principal, op.quote_id)
            quote.ensure_fresh(now)
            current_hash = quote.compute_hash()
            if not (approval.quote_hash == op.quote_hash == quote.quote_hash == current_hash):
                raise ApprovalInvalid("approved terms do not match the quote", code="quote_changed")
            if approval.allowed_total != quote.total or approval.merchant_id != quote.merchant_id:
                raise ApprovalInvalid("approved amount or merchant does not match")
            for other in self.store.rows("operations"):
                if other.id != op.id and other.quote_hash == op.quote_hash and other.state in IN_FLIGHT | {"accepted"}:
                    raise IdempotencyConflict("this quote is already being purchased", code="purchase_in_progress")
            self._require_capability(op.provider_id, "checkout.submit")
            if delegation is not None:
                if delegation.mode is not AssistanceMode.BUY_WITHIN_RULES:
                    raise Forbidden("delegation does not allow purchase execution")
                self._check_grant(delegation, quote)
                self._reserve_budget(delegation, op.id, quote.total)
            self.store.put("approvals", approval.id, replace(approval, state="consumed"))
            op = self._transition(op, "submitting", attempts=op.attempts + 1)
            if scope:
                self.store.put("idempotency", scope, IdempotencyRecord(scope, digest, op.id, now))
        return self._submit(op, quote, principal)

    def _submit(self, op: PurchaseOperation, quote: CheckoutQuote, principal: Principal | str) -> PurchaseOperation:
        # Last gate before the side effect: a revocation that landed after the
        # reservation must stop unsent work.
        if op.delegation_id:
            d = self.store.get("delegations", op.delegation_id)
            if d is None or not d.is_active(self.clock()):
                with self.store.transaction():
                    current = self.store.get("operations", op.id)
                    # submitting -> cancelled is not a normal edge: nothing was sent.
                    self.store.put("operations", op.id, replace(
                        current, state="cancelled", reason_code="delegation_revoked",
                        updated_at=self.clock(), version=current.version + 1))
                    self._release_budget(op.id)
                return self.store.get("operations", op.id)
        conn = self.registry.get(op.provider_id)
        adapter: CheckoutProvider = conn.adapter
        try:
            ack = adapter.submit(SubmitRequest(
                idempotency_key=op.provider_idempotency_key, checkout_reference=quote.checkout_reference,
                quote_hash=quote.quote_hash, expected_total=quote.total, payment_token_ref=None))
        except ProviderError as exc:
            with self.store.transaction():
                current = self.store.get("operations", op.id)
                if exc.transmitted or exc.kind is ProviderErrorKind.OUTCOME_UNKNOWN:
                    return self._transition(current, "outcome_unknown", reason=exc.kind.value)
                self._release_budget(op.id)
                return self._transition(current, "rejected", reason=exc.kind.value)
        return self._apply_ack(op.id, quote, ack.accepted, ack.provider_order_ref, ack.reason_code,
                               ack.evidence_ref, principal)

    def _apply_ack(self, op_id: str, quote: CheckoutQuote, accepted: bool, order_ref: Optional[str],
                   reason: Optional[str], evidence_ref: Optional[str], actor: Principal | str) -> PurchaseOperation:
        with self.store.transaction():
            op = self.store.get("operations", op_id)
            if op.state not in ("submitting", "outcome_unknown"):
                return op  # already resolved by a concurrent reconcile/webhook
            if not accepted:
                self._release_budget(op.id)
                return self._transition(op, "rejected", reason=reason or "provider_rejected")
            self._consume_budget(op.id)
            now = self.clock()
            order = Order(
                id=new_id(), member_id=op.member_id, operation_id=op.id, provider_id=op.provider_id,
                merchant_id=quote.merchant_id, provider_order_ref=order_ref or "",
                quote_hash=quote.quote_hash, idempotency_key=op.provider_idempotency_key,
                order_status="accepted", payment_status="unknown", fulfillment_status="unfulfilled",
                lines=tuple(OrderLine(l.variant_id, l.source_variant_ref, l.quantity) for l in quote.lines),
                total=quote.total, refunded_total=Money.zero(quote.currency), last_observed_at=now,
                evidence_refs=(evidence_ref,) if evidence_ref else ())
            self.store.put("orders", order.id, order)
            op = self._transition(op, "accepted", order_id=order.id)
            self._order_event(order, actor, effect="incoming")
            return op

    # ------------------------------------------------------------- reconcile
    def reconcile(self, operation_id: str) -> PurchaseOperation:
        """Worker entrypoint: resolve ``outcome_unknown`` through the provider's own record."""
        op = self.store.get("operations", operation_id)
        if op is None:
            raise NotFound("operation not found")
        if op.state != "outcome_unknown":
            return op
        conn = self.registry.get(op.provider_id)
        provider: OrderProvider = conn.adapter
        row = self.store.get("quotes", op.quote_id)
        quote = row[1]
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
        with self.store.transaction():
            existing = self.store.get("webhook_receipts", key)
            if existing is not None:
                return existing
            receipt = WebhookReceipt(provider_id, event.event_id, event.event_type, self.clock(), "pending_reconcile")
            self.store.put("webhook_receipts", key, receipt)
        order = next((o for o in self.store.rows("orders")
                      if o.provider_id == provider_id and o.provider_order_ref == event.provider_order_ref), None)
        if order is None:
            # Possibly an order still in outcome_unknown: reconcile that operation.
            for op in self.store.rows("operations"):
                if op.provider_id == provider_id and op.state == "outcome_unknown":
                    self.reconcile(op.id)
            order = next((o for o in self.store.rows("orders")
                          if o.provider_id == provider_id and o.provider_order_ref == event.provider_order_ref), None)
            if order is None:
                return receipt
        # Event order is not trusted: re-read the source of truth and apply monotonically.
        try:
            obs = conn.adapter.lookup(event.provider_order_ref)
        except ProviderError:
            return receipt
        self._apply_observation(order.id, obs, f"provider:{provider_id}")
        with self.store.transaction():
            receipt = replace(receipt, state="applied")
            self.store.put("webhook_receipts", key, receipt)
        return receipt

    def _apply_observation(self, order_id: str, obs: OrderObservation, actor: str) -> Order:
        with self.store.transaction():
            order = self.store.get("orders", order_id)
            by_ref = {l.source_variant_ref: l for l in order.lines}
            new_lines: List[OrderLine] = []
            for ol in obs.lines:
                prev = by_ref.pop(ol.source_variant_ref, None)
                if prev is None:
                    # Exchange creates a new variant relationship; history is retained.
                    new_lines.append(OrderLine(None, ol.source_variant_ref, ol.quantity_ordered,
                                               ol.quantity_shipped, ol.quantity_delivered,
                                               ol.quantity_returned, ol.exchanged_from_ref))
                    continue
                new_lines.append(replace(
                    prev,
                    quantity_shipped=max(prev.quantity_shipped, min(ol.quantity_shipped, prev.quantity_ordered)),
                    quantity_delivered=max(prev.quantity_delivered, min(ol.quantity_delivered, prev.quantity_ordered)),
                    quantity_returned=max(prev.quantity_returned, min(ol.quantity_returned, prev.quantity_ordered))))
            new_lines.extend(by_ref.values())
            lines = tuple(new_lines)
            payment = order.payment_status
            if obs.payment_status == "failed":
                payment = "failed"
            elif _PAYMENT_RANK.get(obs.payment_status, 0) > _PAYMENT_RANK.get(payment, 0):
                payment = obs.payment_status
            refunded = order.refunded_total
            if obs.refunded_total.amount_minor > refunded.amount_minor:
                credit = obs.refunded_total - refunded
                refunded = obs.refunded_total
                self._credit_refund(order, credit)
            delivered = sum(l.quantity_delivered for l in lines)
            shipped = sum(l.quantity_shipped for l in lines)
            ordered = sum(l.quantity_ordered for l in lines)
            fulfillment = ("fulfilled" if ordered and delivered >= ordered else
                           "partially_fulfilled" if shipped or delivered else "unfulfilled")
            order_status = obs.order_status if obs.order_status in ("cancelled",) else order.order_status
            changed = (lines != order.lines or payment != order.payment_status or refunded != order.refunded_total
                       or fulfillment != order.fulfillment_status or order_status != order.order_status)
            if not changed:
                return order
            prev_order = order
            order = replace(order, lines=lines, payment_status=payment, refunded_total=refunded,
                            fulfillment_status=fulfillment, order_status=order_status,
                            last_observed_at=obs.observed_at,
                            evidence_refs=order.evidence_refs + ((obs.evidence_ref,) if obs.evidence_ref else ()),
                            version=order.version + 1)
            self.store.put("orders", order.id, order)
            op = self.store.get("operations", order.operation_id)
            target = self._summary_state(order)
            if target != op.state:
                try:
                    check_transition(op.state, target)
                    self._transition(op, target)
                except CommerceError:
                    pass  # summary state is advisory; order facts above are authoritative
            effect = ("returned" if sum(l.quantity_returned for l in lines) > sum(l.quantity_returned for l in prev_order.lines)
                      else "arrived" if delivered > sum(l.quantity_delivered for l in prev_order.lines)
                      else "updated")
            self._order_event(order, actor, effect=effect)
            return order

    @staticmethod
    def _summary_state(order: Order) -> str:
        if order.order_status == "cancelled":
            return "refunded" if order.payment_status == "refunded" else "cancelled"
        if order.payment_status == "refunded":
            return "refunded"
        if order.payment_status == "partially_refunded":
            return "partially_refunded"
        if order.fulfillment_status == "fulfilled":
            return "fulfilled"
        if order.fulfillment_status == "partially_fulfilled":
            return "partially_fulfilled"
        return "accepted"

    def _order_event(self, order: Order, actor: Principal | str, *, effect: str) -> None:
        """Wardrobe lane reduces these into "On the way"/arrived/returned entries."""
        self._event("commerce.order.observed", "Order", order.id, order.version, actor, {
            "order_id": order.id, "operation_id": order.operation_id,
            "member_id": order.member_id, "provider_id": order.provider_id,
            "order_status": order.order_status, "payment_status": order.payment_status,
            "fulfillment_status": order.fulfillment_status, "wardrobe_effect": effect,
            "lines": [{"variant_id": l.variant_id, "source_variant_ref": l.source_variant_ref,
                       "ordered": l.quantity_ordered, "shipped": l.quantity_shipped,
                       "delivered": l.quantity_delivered, "returned": l.quantity_returned,
                       "exchanged_from_ref": l.exchanged_from_ref} for l in order.lines],
            "acquisition_evidence": list(order.evidence_refs),
        })

    # ---------------------------------------------------------------- returns
    def request_return(self, principal: Principal, order_id: str, source_variant_ref: str,
                       quantity: int) -> Dict[str, Any]:
        order = self._own("orders", order_id, principal)
        line = next((l for l in order.lines if l.source_variant_ref == source_variant_ref), None)
        if line is None or not 1 <= quantity <= line.quantity_ordered - line.quantity_returned:
            raise InvalidQuote("invalid return line or quantity")
        conn = self.registry.get(order.provider_id)
        if not conn.can_execute("returns.request"):
            return {"status": "handoff", "reason_code": conn.capability("returns.request").reason_code,
                    "detail": "Start the return with the retailer; Brand.Me will update when evidence arrives."}
        adapter: ReturnsProvider = conn.adapter
        result = adapter.request_return(order.provider_order_ref, source_variant_ref, quantity)
        with self.store.transaction():
            op = self.store.get("operations", order.operation_id)
            try:
                self._transition(op, "return_requested")
            except CommerceError:
                pass
        # A return request is not a refund: refund state changes only on observation.
        return {"status": "return_requested", "provider_reference": result.source_reference}

    # ----------------------------------------------------------------- budget
    def available_budget(self, delegation: AgentDelegation) -> Money:
        limits = delegation.limits
        if limits is None:
            return Money.zero("USD")
        window_start = self.clock() - timedelta(seconds=limits.window_seconds)
        spent = 0
        for e in self.store.rows("reservations"):
            if e.delegation_id != delegation.id or e.created_at < window_start:
                continue
            if e.kind == "reservation" and e.state in ("reserved", "consumed"):
                spent += e.amount.amount_minor
            elif e.kind == "credit" and e.state == "credited":
                spent -= e.amount.amount_minor
        return Money(max(0, limits.max_cumulative.amount_minor - max(0, spent)), limits.currency)

    def _reserve_budget(self, delegation: AgentDelegation, op_id: str, amount: Money) -> None:
        # Called inside the store transaction: the check and the write are atomic.
        if amount > self.available_budget(delegation):
            raise BudgetExceeded("purchase exceeds the remaining delegated budget")
        e = BudgetEntry(new_id(), delegation.id, op_id, amount, "reservation", "reserved", self.clock())
        self.store.put("reservations", e.id, e)

    def _release_budget(self, op_id: str) -> None:
        for e in self.store.rows("reservations"):
            if e.operation_id == op_id and e.kind == "reservation" and e.state == "reserved":
                self.store.put("reservations", e.id, replace(e, state="released"))

    def _consume_budget(self, op_id: str) -> None:
        for e in self.store.rows("reservations"):
            if e.operation_id == op_id and e.kind == "reservation" and e.state == "reserved":
                self.store.put("reservations", e.id, replace(e, state="consumed"))

    def _credit_refund(self, order: Order, amount: Money) -> None:
        op = self.store.get("operations", order.operation_id)
        if not op.delegation_id:
            return
        d = self.store.get("delegations", op.delegation_id)
        if d is None or d.limits is None or not d.limits.refund_credit_back:
            return
        e = BudgetEntry(new_id(), d.id, op.id, amount, "credit", "credited", self.clock())
        self.store.put("reservations", e.id, e)

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
    def _transition(self, op: PurchaseOperation, new_state: str, *, reason: Optional[str] = None,
                    **changes: Any) -> PurchaseOperation:
        check_transition(op.state, new_state)
        op = replace(op, state=new_state, updated_at=self.clock(), version=op.version + 1,
                     reason_code=reason if reason is not None else op.reason_code, **changes)
        self.store.put("operations", op.id, op)
        return op

    def _void_approval(self, approval_id: Optional[str]) -> None:
        if approval_id:
            a = self.store.get("approvals", approval_id)
            if a is not None and a.state == "issued":
                self.store.put("approvals", a.id, replace(a, state="void"))

    def get_operation(self, principal: Principal, operation_id: str) -> PurchaseOperation:
        return self._own("operations", operation_id, principal)

    def get_order(self, principal: Principal, order_id: str) -> Order:
        return self._own("orders", order_id, principal)
