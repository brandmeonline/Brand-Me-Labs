"""MCP authorization for Brand.Me (MCP 2026-07-28 authorization; RFC 9728, RFC 8707, RFC 6750).

Two audience-bound credentials exist, matching the interface decision in
``docs/build/status/opus-commerce-agents.md``:

1. **External access token** — issued by the authorization server for the
   canonical MCP resource URI. Validated at the gateway transport.
   ``McpAccessTokenValidator`` is the reference implementation of those rules
   (and the conformance oracle for the TypeScript transport).
2. **Executor assertion** — a short-lived JWT the gateway signs after
   validation, audience ``brandme:mcp-executor``, carrying the resolved
   principal. The external token is never forwarded (no token passthrough).

The same verifier, with audience ``brandme:commerce-domain`` and
``allow_session=True``, authenticates the gateway's ``/api/v1`` hop to the
commerce domain, where a first-party session principal is legitimate. The two
audiences are never interchangeable.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

import jwt

from brandme_core.domains.commerce.principal import Principal, validate_principal

MCP_PROTOCOL_VERSION = "2026-07-28"
EXECUTOR_AUDIENCE = "brandme:mcp-executor"
DOMAIN_AUDIENCE = "brandme:commerce-domain"
ALLOWED_ALGORITHMS = ("ES256", "RS256")  # never HS256/none for externally issued tokens
MAX_ASSERTION_TTL = 60
CLOCK_SKEW = 30

# Scopes from ch.03 §3 that MCP clients may request.
MCP_SCOPES = (
    "profile:read", "wardrobe:read", "outfits:read", "commerce:research", "commerce:cart",
    "commerce:purchase", "social:write", "rights:transfer", "rights:reprint",
)


class AuthError(Exception):
    def __init__(self, status: int, error: str, description: str, *, scope: Optional[str] = None,
                 resource_metadata: Optional[str] = None):
        super().__init__(description)
        self.status = status
        self.error = error
        self.description = description
        self.scope = scope
        self.resource_metadata = resource_metadata

    def www_authenticate(self) -> str:
        parts = [f'error="{self.error}"']
        if self.scope:
            parts.append(f'scope="{self.scope}"')
        if self.resource_metadata:
            parts.append(f'resource_metadata="{self.resource_metadata}"')
        parts.append(f'error_description="{self.description}"')
        return "Bearer " + ", ".join(parts)


def canonical_resource(uri: str) -> str:
    """RFC 8707 canonical form: lowercase scheme/host, no fragment, no trailing slash."""
    from urllib.parse import urlsplit, urlunsplit
    p = urlsplit(uri)
    if not p.scheme or not p.netloc or p.fragment:
        raise ValueError("canonical resource URI needs scheme and host and no fragment")
    path = p.path[:-1] if p.path.endswith("/") and p.path != "/" else p.path
    path = "" if path == "/" else path
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, p.query, ""))


def protected_resource_metadata(resource: str, authorization_servers: Sequence[str],
                                scopes_supported: Sequence[str] = ("commerce:research",)) -> Dict[str, Any]:
    """RFC 9728 document served at ``/.well-known/oauth-protected-resource``."""
    return {
        "resource": canonical_resource(resource),
        "authorization_servers": list(authorization_servers),
        "scopes_supported": list(scopes_supported),  # minimal set; step-up for more
        "bearer_methods_supported": ["header"],
        "resource_signing_alg_values_supported": list(ALLOWED_ALGORITHMS),
    }


@dataclass(frozen=True)
class ValidatedToken:
    issuer: str
    subject: str
    client_id: str
    scopes: frozenset
    expires_at: int
    claims: Mapping[str, Any]


class McpAccessTokenValidator:
    """Validates externally issued access tokens for one canonical MCP resource."""

    def __init__(self, *, issuer: str, resource: str, keys: Mapping[str, Any],
                 resource_metadata_url: str, leeway: int = CLOCK_SKEW):
        self.issuer = issuer
        self.resource = canonical_resource(resource)
        self.keys = dict(keys)  # kid -> public key (from the AS JWKS; rotation = new kid)
        self.resource_metadata_url = resource_metadata_url
        self.leeway = leeway

    def _unauthorized(self, msg: str) -> AuthError:
        return AuthError(401, "invalid_token", msg, resource_metadata=self.resource_metadata_url)

    def validate(self, authorization_header: Optional[str]) -> ValidatedToken:
        if not authorization_header or not authorization_header.startswith("Bearer "):
            raise AuthError(401, "invalid_request", "Bearer token required",
                            resource_metadata=self.resource_metadata_url)
        token = authorization_header[7:].strip()
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise self._unauthorized("malformed token") from None
        alg, kid = header.get("alg"), header.get("kid")
        if alg not in ALLOWED_ALGORITHMS:
            raise self._unauthorized("token algorithm not allowed")
        key = self.keys.get(kid)
        if key is None:
            raise self._unauthorized("unknown signing key")
        try:
            claims = jwt.decode(token, key=key, algorithms=[alg], issuer=self.issuer,
                                audience=self.resource, leeway=self.leeway,
                                options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except jwt.InvalidAudienceError:
            raise self._unauthorized("token was not issued for this resource") from None
        except jwt.PyJWTError as exc:
            raise self._unauthorized(f"invalid token: {type(exc).__name__}") from None
        client_id = claims.get("client_id") or claims.get("azp")
        if not client_id:
            raise self._unauthorized("token lacks client identification")
        scopes = frozenset(str(claims.get("scope", "")).split())
        return ValidatedToken(claims["iss"], claims["sub"], client_id, scopes, int(claims["exp"]), claims)

    def require_scopes(self, token: ValidatedToken, required: Iterable[str]) -> None:
        need = sorted(set(required) - token.scopes)
        if need:
            raise AuthError(403, "insufficient_scope", "additional scope required",
                            scope=" ".join(sorted(set(required))), resource_metadata=self.resource_metadata_url)


# ---------------------------------------------------------------- executor hop
class ExecutorAssertionVerifier:
    """Verifies the gateway's principal assertion before any tool runs."""

    def __init__(self, *, gateway_issuer: str, keys: Mapping[str, Any], environment: str,
                 clock=time.time, audience: str = EXECUTOR_AUDIENCE, allow_session: bool = False):
        if allow_session and audience == EXECUTOR_AUDIENCE:
            raise ValueError("the MCP executor hop never accepts session principals")
        self.gateway_issuer = gateway_issuer
        self.keys = dict(keys)
        self.environment = environment
        self.clock = clock
        self.audience = audience
        self.allow_session = allow_session
        self._seen: Dict[str, int] = {}
        self._lock = threading.Lock()

    def verify(self, assertion: str) -> Principal:
        return self._principal(self._claims(assertion))

    def verify_service(self, assertion: str) -> None:
        """A principal-less gateway call (provider webhooks): the provider signature is checked downstream."""
        claims = self._claims(assertion)
        if claims["principal"] is not None:
            raise AuthError(401, "invalid_token", "service assertion must not carry a principal")
        if not self.allow_session:
            raise AuthError(401, "invalid_token", "service assertions are not accepted on the MCP hop")

    def _claims(self, assertion: str) -> Dict[str, Any]:
        try:
            header = jwt.get_unverified_header(assertion)
        except jwt.PyJWTError:
            raise AuthError(401, "invalid_token", "malformed executor assertion") from None
        if header.get("alg") != "ES256" or header.get("kid") not in self.keys:
            raise AuthError(401, "invalid_token", "executor assertion key/algorithm not allowed")
        now = int(self.clock())
        try:
            claims = jwt.decode(assertion, key=self.keys[header["kid"]], algorithms=["ES256"],
                                issuer=self.gateway_issuer, audience=self.audience, leeway=CLOCK_SKEW,
                                # "principal" may be null on service assertions, so it is checked below.
                                options={"require": ["exp", "iat", "iss", "aud", "jti"],
                                         "verify_iat": False},
                                )
        except jwt.InvalidAudienceError:
            raise AuthError(401, "invalid_token", f"assertion not issued for {self.audience}") from None
        except jwt.PyJWTError as exc:
            raise AuthError(401, "invalid_token", f"invalid executor assertion: {type(exc).__name__}") from None
        if int(claims["exp"]) - int(claims["iat"]) > MAX_ASSERTION_TTL:
            raise AuthError(401, "invalid_token", "executor assertion lifetime too long")
        if int(claims["iat"]) > now + CLOCK_SKEW or int(claims["exp"]) < now - CLOCK_SKEW:
            raise AuthError(401, "invalid_token", "executor assertion not currently valid")
        with self._lock:
            self._seen = {j: e for j, e in self._seen.items() if e >= now - CLOCK_SKEW}
            if claims["jti"] in self._seen:
                raise AuthError(401, "invalid_token", "executor assertion replayed")
            self._seen[claims["jti"]] = int(claims["exp"])
        if "principal" not in claims:
            raise AuthError(401, "invalid_token", "assertion has no principal claim")
        return claims

    def _principal(self, claims: Dict[str, Any]) -> Principal:
        p = claims["principal"]
        if not isinstance(p, dict):
            raise AuthError(401, "invalid_token", "principal claim malformed")
        if p.get("environment") != self.environment:
            raise AuthError(401, "invalid_token", "assertion environment mismatch")
        session_id = p.get("session_id")
        if session_id is not None and not self.allow_session:
            # MCP callers are never the trusted surface; a session here is a gateway bug.
            raise AuthError(401, "invalid_token", "session-bound principal on the MCP hop")
        assurance = p.get("assurance_level", "aal1")
        if assurance not in ("aal1", "aal2", "aal3") and not (self.allow_session and assurance == "simulated"):
            raise AuthError(401, "invalid_token", "assurance level not accepted on this hop")
        try:
            principal = Principal(
                member_id=p["member_id"], subject=p["subject"], session_id=session_id, client_id=p.get("client_id"),
                scopes=frozenset(p.get("scopes", [])), assurance_level=assurance,
                environment=p["environment"], delegation_id=p.get("delegation_id"))
            validate_principal(principal)
        except (KeyError, ValueError, TypeError):
            raise AuthError(401, "invalid_token", "principal claim incomplete") from None
        provenance = p.get("issuer") or p.get("identity_provider")
        if not provenance or (session_id is None and not principal.client_id):
            raise AuthError(401, "invalid_token", "principal claim incomplete")
        return principal


def sign_executor_assertion(*, private_key: Any, kid: str, gateway_issuer: str, principal: Dict[str, Any],
                            jti: str, now: Optional[int] = None, ttl: int = 30,
                            audience: str = EXECUTOR_AUDIENCE) -> str:
    """Reference signer used by tests and by a Python gateway shim; the TS transport mirrors it."""
    now = int(now if now is not None else time.time())
    return jwt.encode({"iss": gateway_issuer, "aud": audience, "iat": now, "exp": now + ttl,
                       "jti": jti, "principal": principal}, private_key, algorithm="ES256",
                      headers={"kid": kid})
