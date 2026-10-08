"""AP2 v0.2 Checkout/Payment mandate codec — verifier and mapper (ch.05 §4 "Correct the old AP2 plan").

Brand.Me's role: the member's trusted surface holds the signing key and
produces closed Checkout and Payment mandates as SD-JWTs. Brand.Me's server
**verifies** them and maps them to an internal ``PurchaseApproval`` bound to
the canonical quote hash. The server never signs a mandate on the member's
behalf, and an internal ``ShoppingIntent`` is never presented as an AP2
credential.

Pinned against official sources (verified 2026-10-05):
* spec: https://ap2-protocol.org/ap2/specification/ (v0.2)
* schemas: google-agentic-commerce/AP2 @ ``AP2_SCHEMA_COMMIT`` (vendored, Apache-2.0)
* SD-JWT verification: ``sd-jwt==0.10.4`` (same library and pin as the official SDK)

Implemented: closed mandates (``mandate.checkout.1`` / ``mandate.payment.1``),
merchant Checkout JWT verification (ES256 only — the spec requires a
non-deterministic signature), ``checkout_hash`` / ``transaction_id`` binding,
optional KB-JWT ``aud``/``nonce``, expiry, single use, and exact mapping to
the quote's material terms.
Not implemented (explicitly unsupported): open mandates and delegation chains
(``~~``), agent-to-agent delegation (outside AP2 v0.2 scope), receipts issuance.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import jsonschema
import jwt
from jwcrypto.jwk import JWK
from referencing import Registry, Resource
from sd_jwt.verifier import SDJWTVerifier

from .quote import CheckoutQuote

AP2_VERSION = "0.2"
AP2_SCHEMA_COMMIT = "e1ea56db72a6385bce3e5c1112b3a56ce60acb43"
VCT_CHECKOUT = "mandate.checkout.1"
VCT_PAYMENT = "mandate.payment.1"
_SCHEMA_DIR = Path(__file__).with_name("ap2_schemas")
_HASHES = {None: hashlib.sha256, "sha-256": hashlib.sha256, "sha-384": hashlib.sha384, "sha-512": hashlib.sha512}


class Ap2Error(ValueError):
    """Mandate rejected. ``code`` is stable for problem responses and tests."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def checkout_hash(checkout_jwt: str, sd_alg: Optional[str] = None) -> str:
    """base64url(hash(ascii(checkout_jwt))); sha-256 unless the SD-JWT's ``_sd_alg`` says otherwise."""
    try:
        h = _HASHES[sd_alg]
    except KeyError:
        raise Ap2Error("unsupported_sd_alg", f"unsupported _sd_alg {sd_alg!r}") from None
    return b64url(h(checkout_jwt.encode("ascii")).digest())


@lru_cache(maxsize=1)
def _registry() -> Registry:
    resources = []
    for path in sorted(_SCHEMA_DIR.rglob("*.json")):
        doc = json.loads(path.read_text())
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def _schema(rel: str) -> Dict[str, Any]:
    return json.loads((_SCHEMA_DIR / rel).read_text())


def validate(rel_schema: str, instance: Any) -> None:
    validator = jsonschema.Draft202012Validator(_schema(rel_schema), registry=_registry(),
                                                format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        raise Ap2Error("schema_violation", f"{rel_schema}: {errors[0].message[:200]}")


# ---------------------------------------------------------------- merchant JWT
def verify_merchant_checkout_jwt(checkout_jwt: str, merchant_public_key: Any) -> Dict[str, Any]:
    try:
        header = jwt.get_unverified_header(checkout_jwt)
    except jwt.PyJWTError:
        raise Ap2Error("malformed_checkout_jwt", "checkout_jwt is not a compact JWS") from None
    if header.get("alg") != "ES256":
        # AP2 v0.2: deterministic signatures (e.g. Ed25519) are not allowed for the Checkout JWT.
        raise Ap2Error("checkout_jwt_alg", f"checkout_jwt alg {header.get('alg')!r} not allowed")
    try:
        payload = jwt.decode(checkout_jwt, merchant_public_key, algorithms=["ES256"],
                             options={"verify_aud": False, "require": []})
    except jwt.PyJWTError as exc:
        raise Ap2Error("checkout_jwt_signature", f"merchant signature invalid: {type(exc).__name__}") from None
    validate("ucp/types/checkout.json", payload)
    return payload


def checkout_violations(checkout: Mapping[str, Any], quote: CheckoutQuote) -> List[str]:
    """Compare the merchant-signed checkout with Brand.Me's canonical quote (material terms only)."""
    v: List[str] = []
    if checkout.get("currency") != quote.currency:
        v.append("currency")
    if checkout.get("id") != quote.checkout_reference:
        v.append("checkout_reference")
    if (checkout.get("merchant") or {}).get("id") != quote.merchant_id:
        v.append("merchant")
    if checkout.get("status") not in ("ready_for_complete", "incomplete"):
        v.append("status")
    want = {l.source_variant_ref: (l.quantity, l.unit_price.amount_minor) for l in quote.lines}
    got: Dict[str, Tuple[int, int]] = {}
    for li in checkout.get("line_items", []):
        item = li.get("item", {})
        got[item.get("id")] = (li.get("quantity"), item.get("price"))
    if got != want:
        v.append("line_items")
    totals: Dict[str, List[int]] = {}
    for t in checkout.get("totals", []):
        totals.setdefault(t.get("type"), []).append(t.get("amount"))
    if totals.get("subtotal") != [quote.subtotal.amount_minor] or totals.get("total") != [quote.total.amount_minor]:
        v.append("totals")
    if sum(totals.get("tax", [])) != quote.tax.amount_minor:
        v.append("tax")
    if sum(totals.get("fulfillment", [])) != quote.shipping.amount_minor:
        v.append("shipping")
    discount = -sum(totals.get("discount", []) + totals.get("items_discount", []))
    if abs(discount) != quote.discount.amount_minor:
        v.append("discount")
    return v


# ------------------------------------------------------------ SD-JWT mandates
def _effective_payload(token: str, user_key: JWK, expected_aud: Optional[str],
                       expected_nonce: Optional[str]) -> Tuple[Dict[str, Any], Optional[str], str]:
    if "~~" in token:
        raise Ap2Error("unsupported_chain", "mandate delegation chains / open mandates are not supported")
    if "~" not in token:
        raise Ap2Error("not_sd_jwt", "mandate must be an SD-JWT compact serialization")
    has_kb = bool(token.split("~")[-1].strip())
    if has_kb and not (expected_aud and expected_nonce):
        raise Ap2Error("kb_requires_aud_nonce", "key-binding JWT present; verifier must check aud and nonce")
    try:
        verified = SDJWTVerifier(token, lambda _iss, _hdr: user_key, expected_aud=expected_aud if has_kb else None,
                                 expected_nonce=expected_nonce if has_kb else None,
                                 serialization_format="compact").get_verified_payload()
    except Exception as exc:  # library raises several types
        raise Ap2Error("mandate_signature", f"SD-JWT verification failed: {type(exc).__name__}") from None
    dp = verified.get("delegate_payload")
    if isinstance(dp, list):
        items = [i for i in dp if isinstance(i, dict)]
        if len(items) != 1:
            raise Ap2Error("delegate_payload", "expected exactly one disclosed mandate payload")
        payload = items[0]
    else:
        payload = verified
    issuer_part = token.split("~")[0]
    try:
        sd_alg = jwt.decode(issuer_part, options={"verify_signature": False}).get("_sd_alg")
    except jwt.PyJWTError:
        sd_alg = None
    sd_portion = token if not has_kb else token[: token.rindex("~") + 1]
    return payload, sd_alg, b64url(hashlib.sha256(sd_portion.encode("ascii")).digest())


def _check_times(payload: Mapping[str, Any], now: int, not_after: int) -> None:
    exp, iat = payload.get("exp"), payload.get("iat")
    # Brand.Me policy (stricter than the optional schema fields): both required.
    if not isinstance(exp, int) or not isinstance(iat, int):
        raise Ap2Error("missing_time_claims", "iat and exp are required by Brand.Me policy")
    if iat > now + 60:
        raise Ap2Error("iat_in_future", "mandate issued in the future")
    if exp <= now:
        raise Ap2Error("mandate_expired", "mandate has expired")
    if exp > not_after:
        raise Ap2Error("exp_beyond_quote", "mandate outlives the quote it authorizes")


@dataclass(frozen=True)
class Ap2Verification:
    version: str
    checkout_hash: str
    checkout_mandate_digest: str
    payment_mandate_digest: str
    payment_amount_minor: int
    currency: str
    payee_id: str
    payment_instrument_ref: str

    @property
    def protocol_payload_hash(self) -> str:
        return "sha256:" + hashlib.sha256(
            f"{self.checkout_mandate_digest}.{self.payment_mandate_digest}".encode()).hexdigest()


def verify_closed_mandates(*, checkout_mandate: str, payment_mandate: str, quote: CheckoutQuote,
                           user_key: JWK, merchant_public_key: Any, now: int,
                           expected_aud: Optional[str] = None, expected_nonce: Optional[str] = None,
                           allowed_instrument_types: Tuple[str, ...] = ()) -> Ap2Verification:
    cm, cm_alg, cm_digest = _effective_payload(checkout_mandate, user_key, expected_aud, expected_nonce)
    validate("ap2/checkout_mandate.json", cm)
    if cm.get("vct") != VCT_CHECKOUT:
        raise Ap2Error("vct", "not a closed checkout mandate")
    cjwt = cm["checkout_jwt"]
    chash = checkout_hash(cjwt, cm_alg)
    if cm["checkout_hash"] != chash:
        raise Ap2Error("checkout_hash", "checkout_hash does not match checkout_jwt")
    not_after = int(quote.expires_at.timestamp())
    _check_times(cm, now, not_after)
    checkout = verify_merchant_checkout_jwt(cjwt, merchant_public_key)
    violations = checkout_violations(checkout, quote)
    if violations:
        raise Ap2Error("terms_mismatch", "mandate terms differ from the quote: " + ",".join(violations))

    pm, pm_alg, pm_digest = _effective_payload(payment_mandate, user_key, expected_aud, expected_nonce)
    validate("ap2/payment_mandate.json", pm)
    if pm.get("vct") != VCT_PAYMENT:
        raise Ap2Error("vct", "not a closed payment mandate")
    if pm["transaction_id"] != checkout_hash(cjwt, pm_alg):
        raise Ap2Error("transaction_id", "payment mandate is bound to a different checkout")
    _check_times(pm, now, not_after)
    amount = pm["payment_amount"]
    if amount["currency"] != quote.currency or amount["amount"] != quote.total.amount_minor:
        raise Ap2Error("payment_amount", "payment amount/currency differs from the approved total")
    if pm["payee"]["id"] != quote.merchant_id:
        raise Ap2Error("payee", "payee differs from the quote merchant")
    if pm.get("execution_date"):
        raise Ap2Error("deferred_execution", "deferred/recurring execution is outside the purchase scope")
    if allowed_instrument_types and pm["payment_instrument"]["type"] not in allowed_instrument_types:
        raise Ap2Error("payment_instrument", "instrument type not allowed")
    return Ap2Verification(AP2_VERSION, chash, cm_digest, pm_digest, amount["amount"], amount["currency"],
                           pm["payee"]["id"], pm["payment_instrument"]["id"])
