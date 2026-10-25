"""The consumer-domain service: the gateway's principal assertion and the mounted app.

Verifier rules match brandme-gateway/src/services/domains.ts. The full flow
through the real gateway is brandme-gateway/src/routes/v1/consumer-domains.test.ts.
"""

from __future__ import annotations

import json
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from brandme_core.domains.media.providers import registry_from_environment
from brandme_core.domains.media.store import MemoryMediaStore
from brandme_core.domains.persona import app as domain_app
from brandme_core.domains.persona.assertion import AUDIENCE, MAX_TTL, DomainAssertionVerifier, bearer_resolver, sign_assertion
from test_persona_harness import insert_member, spanner_db  # noqa: F401

NOW = 1_800_000_000
ISSUER = "brandme-gateway"


@pytest.fixture(scope="module")
def keys():
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))
    return key, json.dumps({"keys": [{**jwk, "kid": "k-1"}]})


def principal(member_id: str, **over):
    return {"member_id": member_id, "subject": "dev|t", "session_id": "s", "client_id": None, "scopes": ["profile:read", "wardrobe:read"],
            "assurance_level": "simulated", "environment": "development", "delegation_id": None, **over}


def token(key, p, **kw):
    return sign_assertion(private_key=key, kid=kw.pop("kid", "k-1"), issuer=kw.pop("issuer", ISSUER), principal=p,
                          jti=kw.pop("jti", str(uuid.uuid4())), now=kw.pop("now", NOW), **kw)


def verifier(jwks, now=NOW):
    return DomainAssertionVerifier.from_jwks(issuer=ISSUER, jwks=jwks, environment="development", clock=lambda: now)


def test_valid_assertion_yields_the_principal(keys):
    key, jwks = keys
    p = verifier(jwks).verify(token(key, principal("11111111-1111-4111-8111-111111111111")))
    assert (p.member_id, p.scopes, p.environment, p.assurance_level) == (
        "11111111-1111-4111-8111-111111111111", frozenset({"profile:read", "wardrobe:read"}), "development", "simulated")


def test_assertions_that_must_be_refused(keys):
    key, jwks = keys
    v = verifier(jwks)
    m = "11111111-1111-4111-8111-111111111111"
    other = ec.generate_private_key(ec.SECP256R1())
    bad = {
        "replayed": None,
        "wrong issuer": token(key, principal(m), issuer="someone-else"),
        "unknown kid": token(key, principal(m), kid="k-2"),
        "foreign key": token(other, principal(m)),
        "too long": token(key, principal(m), ttl=MAX_TTL + 1),
        "expired": token(key, principal(m), now=NOW - 120),
        "other environment": token(key, principal(m, environment="production")),
        "scopes not a list": token(key, principal(m, scopes="wardrobe:write")),
        "wrong audience": jwt.encode({"iss": ISSUER, "aud": "brandme:mcp-executor", "iat": NOW, "exp": NOW + 30, "jti": str(uuid.uuid4()),
                                      "principal": principal(m)}, key, algorithm="ES256", headers={"kid": "k-1"}),
        "symmetric": jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "iat": NOW, "exp": NOW + 30, "jti": str(uuid.uuid4()),
                                 "principal": principal(m)}, "k" * 32, algorithm="HS256", headers={"kid": "k-1"}),
    }
    once = token(key, principal(m))
    v.verify(once)
    bad["replayed"] = once
    resolve = bearer_resolver(v)
    for name, t in bad.items():
        assert resolve(type("R", (), {"headers": {"authorization": f"Bearer {t}"}})()) is None, name


def test_only_public_p256_keys_are_accepted(keys):
    key, jwks = keys
    private = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key))
    with pytest.raises(ValueError):
        DomainAssertionVerifier.from_jwks(issuer=ISSUER, jwks=json.dumps({"keys": [{**private, "kid": "k-1"}]}), environment="development")
    with pytest.raises(ValueError):
        DomainAssertionVerifier.from_jwks(issuer=ISSUER, jwks=json.dumps({"keys": []}), environment="development")


def test_mounted_app_serves_lane_routes_only_with_a_valid_assertion(spanner_db, keys):  # noqa: F811
    key, jwks = keys
    member = insert_member(spanner_db)
    client = TestClient(domain_app.create_app(spanner_db, resolve_principal=bearer_resolver(verifier(jwks, now=int(__import__("time").time())))))
    assert client.get("/me/persona").status_code == 401
    ok = client.get("/me/persona", headers={"authorization": f"Bearer {token(key, principal(member), now=int(__import__('time').time()))}"})
    assert ok.status_code == 200 and ok.headers["cache-control"] == "private, no-store"
    assert client.get("/media/jobs/" + str(uuid.uuid4())).status_code == 404  # no bucket: media not mounted
    with_media = TestClient(domain_app.create_app(spanner_db, resolve_principal=bearer_resolver(verifier(jwks)), media_store=MemoryMediaStore()))
    assert with_media.get("/health").json() == {"status": "ok", "media": "mounted"}


def test_service_configuration_refusals():
    base = {"BRANDME_MODE": "development", "ENVIRONMENT": "development", "SPANNER_EMULATOR_HOST": "localhost:9010", "SPANNER_PROJECT_ID": "p",
            "SPANNER_INSTANCE_ID": "i", "SPANNER_DATABASE_ID": "d", "CONSUMER_DOMAIN_ASSERTION_ISSUER": ISSUER,
            "CONSUMER_DOMAIN_ASSERTION_JWKS": "{}"}
    assert domain_app._config(base)["port"] == domain_app.DEFAULT_PORT
    for change in ({"BRANDME_MODE": "sandbox"}, {"ENVIRONMENT": "production", "BRANDME_MODE": "production"},
                   {"CONSUMER_DOMAIN_ASSERTION_JWKS": ""}, {"SPANNER_DATABASE_ID": " "}):
        with pytest.raises(ValueError):
            domain_app._config({**base, **change})


def test_simulated_provider_is_dev_only():
    assert registry_from_environment({"ENVIRONMENT": "development"}).active() is None
    sim = registry_from_environment({"ENVIRONMENT": "development", "BRANDME_TRYON_PROVIDER": "simulated"}).active()
    assert sim is not None and sim.simulated is True
    for env in ({"ENVIRONMENT": "production", "BRANDME_TRYON_PROVIDER": "simulated"}, {"ENVIRONMENT": "development", "BRANDME_TRYON_PROVIDER": "vertex"}):
        with pytest.raises(ValueError):
            registry_from_environment(env)
