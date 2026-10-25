"""
Gateway → consumer-domain principal assertion (check-in ruling Q12, PD-07/PD-18).

The gateway is the identity boundary (ch.03 §3). After its own session or
OIDC checks it signs a short-lived ES256 JWT, audience ``AUDIENCE``, that
carries the resolved principal. The domain service verifies:
- the key id and algorithm, and the issuer and audience;
- a lifetime of at most ``MAX_TTL`` seconds, currently valid;
- a single-use ``jti``, against a bounded replay cache;
- that the principal's environment equals this process's mode.

The member's own token or cookie never crosses this hop. Only the gateway holds
the private key; the domain service has the public keys (rotation by ``kid``).
This mirrors the commerce lane's executor assertion (brandme_core/mcp/authz.py).
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional

import jwt

from .kernel import Principal, member_principal

AUDIENCE = "brandme:consumer-domains"
MAX_TTL = 60
CLOCK_SKEW = 30
REPLAY_CACHE_MAX = 100_000


class AssertionRejected(Exception):
    """Why an assertion was refused (never echoed to callers)."""


class DomainAssertionVerifier:
    def __init__(self, *, issuer: str, keys: Mapping[str, Any], environment: str, clock: Callable[[], float] = time.time):
        if not issuer or not keys:
            raise ValueError("an issuer and at least one public key are required")
        self.issuer = issuer
        self.keys = dict(keys)
        self.environment = environment
        self.clock = clock
        self._seen: Dict[str, int] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_jwks(cls, *, issuer: str, jwks: str, environment: str, clock: Callable[[], float] = time.time) -> "DomainAssertionVerifier":
        """``jwks`` is a JSON Web Key Set of P-256 public keys, each with a ``kid``."""
        keys = {}
        for jwk in json.loads(jwks).get("keys", []):
            if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256" or "d" in jwk or not jwk.get("kid"):
                raise ValueError("only public P-256 keys with a kid are accepted")
            keys[jwk["kid"]] = jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(jwk))
        return cls(issuer=issuer, keys=keys, environment=environment, clock=clock)

    def verify(self, assertion: str) -> Principal:
        try:
            header = jwt.get_unverified_header(assertion)
        except jwt.PyJWTError:
            raise AssertionRejected("malformed") from None
        if header.get("alg") != "ES256" or header.get("kid") not in self.keys:
            raise AssertionRejected("key or algorithm not allowed")
        now = int(self.clock())
        try:
            claims = jwt.decode(assertion, key=self.keys[header["kid"]], algorithms=["ES256"], issuer=self.issuer, audience=AUDIENCE,
                                leeway=CLOCK_SKEW, options={"require": ["exp", "iat", "iss", "aud", "jti", "principal"], "verify_iat": False})
        except jwt.PyJWTError as exc:
            raise AssertionRejected(type(exc).__name__) from None
        iat, exp = int(claims["iat"]), int(claims["exp"])
        if exp - iat > MAX_TTL:
            raise AssertionRejected("lifetime too long")
        if iat > now + CLOCK_SKEW or exp < now - CLOCK_SKEW:
            raise AssertionRejected("not currently valid")
        jti = claims["jti"]
        if not isinstance(jti, str) or not 16 <= len(jti) <= 64:
            raise AssertionRejected("jti malformed")
        with self._lock:
            if len(self._seen) >= REPLAY_CACHE_MAX or jti in self._seen:
                self._seen = {j: e for j, e in self._seen.items() if e >= now - CLOCK_SKEW}
            if jti in self._seen:
                raise AssertionRejected("replayed")
            if len(self._seen) >= REPLAY_CACHE_MAX:
                raise AssertionRejected("replay cache full")
            self._seen[jti] = exp
        p = claims["principal"]
        if not isinstance(p, dict) or p.get("environment") != self.environment:
            raise AssertionRejected("principal malformed or for another environment")
        scopes = p.get("scopes")
        if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
            raise AssertionRejected("scopes malformed")
        try:
            return member_principal(p["member_id"], scopes, environment=p["environment"], subject=p["subject"],
                                    session_id=p.get("session_id"), client_id=p.get("client_id"),
                                    assurance_level=p["assurance_level"], delegation_id=p.get("delegation_id"))
        except (KeyError, TypeError, ValueError):
            raise AssertionRejected("principal incomplete") from None


def bearer_resolver(verifier: DomainAssertionVerifier) -> Callable[[Any], Optional[Principal]]:
    """``resolve_principal`` for this lane's routers: ``Authorization: Bearer <assertion>``."""

    def resolve(request: Any) -> Optional[Principal]:
        raw = request.headers.get("authorization", "")
        scheme, _, token = raw.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        try:
            return verifier.verify(token.strip())
        except AssertionRejected:
            return None

    return resolve


def sign_assertion(*, private_key: Any, kid: str, issuer: str, principal: Dict[str, Any], jti: str,
                   now: Optional[int] = None, ttl: int = 30) -> str:
    """Reference signer for tests; the gateway's TypeScript client mirrors it."""
    now = int(now if now is not None else time.time())
    return jwt.encode({"iss": issuer, "aud": AUDIENCE, "iat": now, "exp": now + ttl, "jti": jti, "principal": principal},
                      private_key, algorithm="ES256", headers={"kid": kid})
