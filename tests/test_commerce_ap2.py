"""AP2 v0.2 closed Checkout/Payment mandate conformance (BM-COM-014).

Local tests validate against the vendored official schemas. The oracle tests
cross-verify with the official AP2 SDK (pinned commit) in a separate
interpreter given by ``AP2_SDK_PYTHON``; they are skipped, not passed, when it
is absent.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from jwcrypto.jwk import JWK

from brandme_core.domains.commerce import ap2
from brandme_core.domains.commerce.errors import ApprovalInvalid
from tests.fixtures.commerce.ap2_issuer import (
    closed_checkout_mandate, closed_payment_mandate, issue, merchant_checkout_jwt, present_with_kb,
)
from tests.fixtures.commerce.harness import world

ORACLE = Path(__file__).resolve().parent / "fixtures/commerce/ap2_sdk_oracle.py"


@pytest.fixture
def setup():
    w = world()
    d, ag = w.delegate()
    _, quote, op = w.prepared(ag)
    user = JWK.generate(kty="EC", crv="P-256")
    w.svc.register_surface_key(w.member, user.export_public(as_dict=True))
    now = int(w.clock.now.timestamp())
    return w, ag, quote, op, user, now


def mandates(w, quote, user, now, **pm_kw):
    cjwt = merchant_checkout_jwt(w.provider, quote)
    exp = int(quote.expires_at.timestamp())
    return (closed_checkout_mandate(user, cjwt, iat=now, exp=exp),
            closed_payment_mandate(user, cjwt, quote, iat=now, exp=exp, **pm_kw))


def test_vendored_schemas_are_the_pinned_official_ones():
    notice = (Path(ap2.__file__).with_name("ap2_schemas") / "NOTICE.md").read_text()
    assert ap2.AP2_SCHEMA_COMMIT in notice
    assert json.loads((Path(ap2.__file__).with_name("ap2_schemas") / "ap2/checkout_mandate.json").read_text()
                      )["properties"]["vct"]["const"] == ap2.VCT_CHECKOUT


def test_checkout_hash_matches_sdk_definition():
    # Official SDK: b64url(sha256(checkout_jwt.encode('ascii'))) without padding.
    import base64, hashlib
    jwt_str = "aaa.bbb.ccc"
    assert ap2.checkout_hash(jwt_str) == base64.urlsafe_b64encode(
        hashlib.sha256(jwt_str.encode()).digest()).rstrip(b"=").decode()


def test_valid_mandates_produce_bound_approval_and_purchase(setup):
    w, ag, quote, op, user, now = setup
    cm, pm = mandates(w, quote, user, now)
    approval = w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
    assert approval.method == "ap2_mandate" and approval.quote_hash == quote.quote_hash
    assert approval.protocol_payload_hash.startswith("sha256:")
    done = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="ap2-exec")
    assert done.state == "accepted"


def test_replayed_mandate_rejected(setup):
    w, ag, quote, op, user, now = setup
    cm, pm = mandates(w, quote, user, now)
    w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
    op2 = w.svc.request_purchase(ag, quote.id)
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.approve_with_ap2(ag, operation_id=op2.id, checkout_mandate=cm, payment_mandate=pm)
    assert e.value.code == "ap2_replay"


def test_mandate_signed_by_unregistered_key_rejected(setup):
    w, ag, quote, op, _, now = setup
    stranger = JWK.generate(kty="EC", crv="P-256")
    cm, pm = mandates(w, quote, stranger, now)
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
    assert e.value.code == "ap2_mandate_signature"


def test_tampered_disclosure_or_signature_rejected(setup):
    w, ag, quote, op, user, now = setup
    cm, pm = mandates(w, quote, user, now)
    bad_sig = cm[: cm.index("~")][:-4] + "AAAA" + cm[cm.index("~"):]
    for bad in (bad_sig, cm.replace("~", "~x", 1)):
        with pytest.raises(ApprovalInvalid):
            w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=bad, payment_mandate=pm)


@pytest.mark.parametrize("override,code", [
    (dict(totals=[{"type": "subtotal", "amount": 8900}, {"type": "tax", "amount": 712},
                  {"type": "total", "amount": 1}]), "ap2_terms_mismatch"),
    (dict(currency="EUR"), "ap2_terms_mismatch"),
    (dict(id="other-checkout"), "ap2_terms_mismatch"),
])
def test_merchant_checkout_not_matching_quote_rejected(setup, override, code):
    w, ag, quote, op, user, now = setup
    cjwt = merchant_checkout_jwt(w.provider, quote, **override)
    exp = int(quote.expires_at.timestamp())
    cm = closed_checkout_mandate(user, cjwt, iat=now, exp=exp)
    pm = closed_payment_mandate(user, cjwt, quote, iat=now, exp=exp)
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
    assert e.value.code == code


def test_merchant_jwt_must_be_es256_and_merchant_signed(setup):
    w, ag, quote, op, user, now = setup
    doc = w.provider.ucp_checkout(quote)
    exp = int(quote.expires_at.timestamp())
    for cjwt in (jwt.encode(doc, ed25519.Ed25519PrivateKey.generate(), algorithm="EdDSA"),
                 jwt.encode(doc, ec.generate_private_key(ec.SECP256R1()), algorithm="ES256")):
        cm = closed_checkout_mandate(user, cjwt, iat=now, exp=exp)
        pm = closed_payment_mandate(user, cjwt, quote, iat=now, exp=exp)
        with pytest.raises(ApprovalInvalid) as e:
            w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
        assert e.value.code in ("ap2_checkout_jwt_alg", "ap2_checkout_jwt_signature")


@pytest.mark.parametrize("kw,code", [
    (dict(amount=1), "ap2_payment_amount"),
    (dict(payee_id="someone-else"), "ap2_payee"),
])
def test_payment_mandate_terms(setup, kw, code):
    w, ag, quote, op, user, now = setup
    cm, pm = mandates(w, quote, user, now, **kw)
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
    assert e.value.code == code


def test_payment_bound_to_other_checkout_rejected(setup):
    w, ag, quote, op, user, now = setup
    cjwt = merchant_checkout_jwt(w.provider, quote)
    other = merchant_checkout_jwt(w.provider, quote, status="incomplete")
    exp = int(quote.expires_at.timestamp())
    cm = closed_checkout_mandate(user, cjwt, iat=now, exp=exp)
    pm = closed_payment_mandate(user, other, quote, iat=now, exp=exp)
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
    assert e.value.code == "ap2_transaction_id"


def test_expired_or_overlong_mandate(setup):
    w, ag, quote, op, user, now = setup
    cjwt = merchant_checkout_jwt(w.provider, quote)
    exp = int(quote.expires_at.timestamp())
    pm = closed_payment_mandate(user, cjwt, quote, iat=now, exp=exp)
    for cm, code in ((closed_checkout_mandate(user, cjwt, iat=now - 100, exp=now - 1), "ap2_mandate_expired"),
                     (closed_checkout_mandate(user, cjwt, iat=now, exp=exp + 3600), "ap2_exp_beyond_quote")):
        with pytest.raises(ApprovalInvalid) as e:
            w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
        assert e.value.code == code


def test_wrong_vct_and_schema_violation(setup):
    w, ag, quote, op, user, now = setup
    cjwt = merchant_checkout_jwt(w.provider, quote)
    exp = int(quote.expires_at.timestamp())
    pm = closed_payment_mandate(user, cjwt, quote, iat=now, exp=exp)
    old_style = issue(user, {"vct": "mandate.cart", "checkout_jwt": cjwt, "checkout_hash": ap2.checkout_hash(cjwt),
                             "iat": now, "exp": exp})
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=old_style, payment_mandate=pm)
    assert e.value.code == "ap2_schema_violation"


def test_key_binding_requires_matching_aud_and_nonce(setup):
    w, ag, quote, op, user, now = setup
    cjwt = merchant_checkout_jwt(w.provider, quote)
    exp = int(quote.expires_at.timestamp())
    cm_issued = closed_checkout_mandate(user, cjwt, iat=now, exp=exp, holder_jwk=user)
    pm_issued = closed_payment_mandate(user, cjwt, quote, iat=now, exp=exp, holder_jwk=user)
    cm = present_with_kb(cm_issued, user, aud="brandme-commerce", nonce="n-123")
    pm = present_with_kb(pm_issued, user, aud="brandme-commerce", nonce="n-123")
    with pytest.raises(ApprovalInvalid) as e:  # verifier must supply aud/nonce
        w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
    assert e.value.code == "ap2_kb_requires_aud_nonce"
    with pytest.raises(ApprovalInvalid):
        w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm,
                               expected_aud="brandme-commerce", expected_nonce="other")
    a = w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm,
                               expected_aud="brandme-commerce", expected_nonce="n-123")
    assert a.method == "ap2_mandate"


def test_open_mandates_and_chains_unsupported(setup):
    w, ag, quote, op, user, now = setup
    cm, pm = mandates(w, quote, user, now)
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm + "~" + cm, payment_mandate=pm)
    assert e.value.code == "ap2_unsupported_chain"


def test_provider_without_ap2_refuses(setup):
    w, ag, quote, op, user, now = setup
    w.registry.get("demo_atelier").protocols = {}
    cm, pm = mandates(w, quote, user, now)
    with pytest.raises(Exception) as e:
        w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
    assert getattr(e.value, "code", "") == "protocol_not_supported"


# ------------------------------------------------------------ official SDK oracle
SDK_PY = os.environ.get("AP2_SDK_PYTHON")
oracle = pytest.mark.skipif(not SDK_PY, reason="AP2_SDK_PYTHON not set: official SDK oracle not available")


def _oracle(req):
    out = subprocess.run([SDK_PY, str(ORACLE)], input=json.dumps(req), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


@oracle
def test_official_sdk_verifies_mandates_we_accept(setup):
    w, ag, quote, op, user, now = setup
    cm, pm = mandates(w, quote, user, now)
    pub = user.export_public(as_dict=True)
    for kind, tok in (("checkout", cm), ("payment", pm)):
        r = _oracle({"mode": "verify", "kind": kind, "token": tok, "public_jwk": pub, "current_time": now})
        assert r["ok"], r
    assert r["payload"]["vct"] == ap2.VCT_PAYMENT and r["payload"]["payment_amount"]["amount"] == quote.total.amount_minor


@oracle
def test_we_verify_mandates_issued_by_official_sdk(setup):
    w, ag, quote, op, user, now = setup
    cjwt = merchant_checkout_jwt(w.provider, quote)
    exp = int(quote.expires_at.timestamp())
    priv = json.loads(user.export_private())
    cm = _oracle({"mode": "create", "kind": "checkout", "private_jwk": priv, "payload": {
        "vct": ap2.VCT_CHECKOUT, "checkout_jwt": cjwt, "checkout_hash": ap2.checkout_hash(cjwt), "iat": now, "exp": exp}})["token"]
    pm = _oracle({"mode": "create", "kind": "payment", "private_jwk": priv, "payload": {
        "vct": ap2.VCT_PAYMENT, "transaction_id": ap2.checkout_hash(cjwt),
        "payee": {"id": quote.merchant_id, "name": "Demo Atelier (fictional)"},
        "payment_amount": {"amount": quote.total.amount_minor, "currency": quote.currency},
        "payment_instrument": {"id": "demo-instrument-ref", "type": "demo_network_token"},
        "iat": now, "exp": exp}})["token"]
    a = w.svc.approve_with_ap2(ag, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)
    assert a.method == "ap2_mandate"


@oracle
def test_official_sdk_rejects_what_we_reject(setup):
    w, ag, quote, op, user, now = setup
    cm, _ = mandates(w, quote, user, now)
    stranger = JWK.generate(kty="EC", crv="P-256").export_public(as_dict=True)
    assert not _oracle({"mode": "verify", "kind": "checkout", "token": cm, "public_jwk": stranger,
                        "current_time": now})["ok"]
    expired = _oracle({"mode": "verify", "kind": "checkout", "token": cm,
                       "public_jwk": user.export_public(as_dict=True), "current_time": now + 3600})
    assert not expired["ok"] and "expired" in expired["error"]
