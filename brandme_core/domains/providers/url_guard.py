"""URL safety for imports and checkout redirects (ch.05 §3, §7; BM-PROV-010, BM-COM-013).

* ``check_public_url`` rejects non-HTTPS schemes, credentials in URLs, and any
  host resolving to loopback, private, link-local (incl. cloud metadata),
  multicast, reserved or unspecified addresses — IPv4, IPv6 and IPv4-mapped.
* ``SafeFetcher`` revalidates every redirect hop *before* following it and
  enforces size, time and content-type limits.
* ``validate_redirect`` only allows provider-issued destinations on hosts
  registered for that provider connection.

Residual risk: DNS rebinding between our resolution and the HTTP client's own
resolution. Production egress goes through the provider egress allowlist proxy
(ch.03 §9), which is the enforcing control; this module is defense in depth.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

Resolver = Callable[[str], Sequence[str]]

_METADATA_HOSTS = frozenset({"metadata.google.internal", "metadata", "169.254.169.254"})


class UnsafeUrl(ValueError):
    pass


def system_resolver(host: str) -> List[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified or not ip.is_global)


def check_public_url(url: str, resolver: Resolver = system_resolver) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeUrl("only https URLs are allowed")
    if parts.username or parts.password:
        raise UnsafeUrl("credentials in URL are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeUrl("missing host")
    if host in _METADATA_HOSTS or host == "localhost" or host.endswith(".localhost") \
            or host.endswith(".internal") or host.endswith(".local"):
        raise UnsafeUrl("internal host")
    if parts.port not in (None, 443):
        raise UnsafeUrl("non-standard port")
    try:
        literal = ipaddress.ip_address(host)
        addrs = [str(literal)]
    except ValueError:
        addrs = list(resolver(host))
    if not addrs:
        raise UnsafeUrl("host did not resolve")
    for a in addrs:
        if not _ip_is_public(ipaddress.ip_address(a)):
            raise UnsafeUrl("host resolves to a non-public address")
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))


@dataclass(frozen=True)
class FetchResult:
    final_url: str
    content_type: str
    body: bytes
    hops: Tuple[str, ...]


@dataclass(frozen=True)
class RawResponse:
    status: int
    headers: dict
    body: bytes


Transport = Callable[[str, float, int], RawResponse]  # (url, timeout_s, max_bytes) -> response


class SafeFetcher:
    def __init__(self, transport: Transport, *, resolver: Resolver = system_resolver,
                 allowed_content_types: Iterable[str] = ("image/jpeg", "image/png", "image/webp"),
                 max_bytes: int = 10 * 1024 * 1024, timeout_s: float = 10.0, max_redirects: int = 3):
        self.transport = transport
        self.resolver = resolver
        self.allowed = tuple(allowed_content_types)
        self.max_bytes = max_bytes
        self.timeout_s = timeout_s
        self.max_redirects = max_redirects

    def fetch(self, url: str) -> FetchResult:
        hops: List[str] = []
        current = check_public_url(url, self.resolver)
        for _ in range(self.max_redirects + 1):
            hops.append(current)
            resp = self.transport(current, self.timeout_s, self.max_bytes)
            if resp.status in (301, 302, 303, 307, 308):
                location = resp.headers.get("location") or resp.headers.get("Location")
                if not location:
                    raise UnsafeUrl("redirect without location")
                # Revalidate the next hop before any request is made to it.
                current = check_public_url(urljoin(current, location), self.resolver)
                continue
            if resp.status != 200:
                raise UnsafeUrl(f"unexpected status {resp.status}")
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if ctype not in self.allowed:
                raise UnsafeUrl(f"content type {ctype or 'missing'} not allowed")
            if len(resp.body) > self.max_bytes:
                raise UnsafeUrl("response too large")
            return FetchResult(current, ctype, resp.body, tuple(hops))
        raise UnsafeUrl("too many redirects")


def validate_redirect(url: str, allowed_hosts: Iterable[str]) -> str:
    """Hosted ``continue_url`` / handoff destinations must be registered merchant hosts."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password:
        raise UnsafeUrl("redirect must be https without credentials")
    host = (parts.hostname or "").lower().rstrip(".")
    allowed = {h.lower() for h in allowed_hosts}
    if host not in allowed:
        raise UnsafeUrl("redirect destination is not registered for this provider")
    if parts.port not in (None, 443):
        raise UnsafeUrl("non-standard port")
    return urlunsplit(("https", host, parts.path or "/", parts.query, ""))
