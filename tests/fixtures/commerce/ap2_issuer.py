"""Test-only AP2 mandate issuer standing in for the member's trusted-surface device key.

Mirrors the official SDK's root SD-JWT shape (``delegate_payload`` array with
selectively disclosable ``checkout_jwt``). Production Brand.Me servers never
issue mandates; they only verify them (``brandme_core.domains.commerce.ap2``).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import jwt
from jwcrypto.jwk import JWK
from sd_jwt.common import SDObj
from sd_jwt.holder import SDJWTHolder
from sd_jwt.issuer import SDJWTIssuer

from brandme_core.domains.commerce.ap2 import VCT_CHECKOUT, VCT_PAYMENT, checkout_hash
from brandme_core.domains.commerce.quote import CheckoutQuote


def merchant_checkout_jwt(provider, quote: CheckoutQuote, **override: Any) -> str:
    return provider.signed_checkout_jwt(quote, **override)


def issue(user_jwk: JWK, payload: Dict[str, Any], *, holder_jwk: Optional[JWK] = None,
          disclosable: tuple = ()) -> str:
    claims = {SDObj(k) if k in disclosable else k: v for k, v in payload.items()}
    issuer = SDJWTIssuer({"delegate_payload": [claims]}, user_jwk,
                         holder_key=holder_jwk, serialization_format="compact")
    return issuer.sd_jwt_issuance


def present_with_kb(issuance: str, holder_jwk: JWK, *, aud: str, nonce: str) -> str:
    holder = SDJWTHolder(issuance, serialization_format="compact")
    # Disclose the mandate's selectively disclosable fields (e.g. checkout_jwt).
    holder.create_presentation({"delegate_payload": [{"checkout_jwt": True}]}, nonce, aud, holder_jwk)
    return holder.sd_jwt_presentation


def closed_checkout_mandate(user_jwk: JWK, cjwt: str, *, iat: int, exp: int, **kw) -> str:
    return issue(user_jwk, {"vct": VCT_CHECKOUT, "checkout_jwt": cjwt, "checkout_hash": checkout_hash(cjwt),
                            "iat": iat, "exp": exp}, disclosable=("checkout_jwt",), **kw)


def closed_payment_mandate(user_jwk: JWK, cjwt: str, quote: CheckoutQuote, *, iat: int, exp: int,
                           amount: Optional[int] = None, payee_id: Optional[str] = None, **kw) -> str:
    return issue(user_jwk, {
        "vct": VCT_PAYMENT, "transaction_id": checkout_hash(cjwt),
        "payee": {"id": payee_id or quote.merchant_id, "name": "Demo Atelier (fictional)"},
        "payment_amount": {"amount": quote.total.amount_minor if amount is None else amount,
                           "currency": quote.currency},
        "payment_instrument": {"id": "demo-instrument-ref", "type": "demo_network_token"},
        "iat": iat, "exp": exp}, **kw)
