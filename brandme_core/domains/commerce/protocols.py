"""Protocol integration status: ACP, UCP, A2A (ch.05 §3–§4).

Only AP2 v0.2 closed-mandate verification is implemented (``ap2.py``). The
others are **explicitly unconfigured**: no approved merchant, processor or
partner agent exists for this deployment, so no version is pinned and no
endpoint, Agent Card or capability is advertised. Each adapter fails closed
with ``NOT_CONFIGURED``. Pin the official version and implement against its
conformance suite only when a real approved integration exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from brandme_core.domains.providers.contracts import ProviderError, ProviderErrorKind


@dataclass(frozen=True)
class ProtocolStatus:
    name: str
    state: str  # implemented | unconfigured
    pinned_version: Optional[str]
    reason: str
    source: str


PROTOCOLS: Dict[str, ProtocolStatus] = {
    "ap2": ProtocolStatus("ap2", "implemented", "0.2",
                          "closed Checkout/Payment mandate verification only; open mandates unsupported",
                          "https://ap2-protocol.org/ap2/specification/"),
    "acp": ProtocolStatus("acp", "unconfigured", None, "no approved ACP merchant or payment processor account",
                          "https://www.agenticcommerce.dev/docs/reference/checkout"),
    "ucp": ProtocolStatus("ucp", "unconfigured", None, "no approved merchant UCP profile reference",
                          "https://shopify.dev/docs/agents/profiles"),
    "a2a": ProtocolStatus("a2a", "unconfigured", None, "no approved partner agent/task need",
                          "https://a2a-protocol.org/latest/specification/"),
}


def agent_card() -> None:
    """No A2A Agent Card is published: publishing one would advertise skills that do not exist."""
    return None


class _Unconfigured:
    protocol = ""

    def __getattr__(self, name: str):
        def _refuse(*_a, **_k):
            raise ProviderError(ProviderErrorKind.NOT_CONFIGURED,
                                f"{self.protocol} is not configured: {PROTOCOLS[self.protocol].reason}")
        return _refuse


class AcpCheckoutAdapter(_Unconfigured):
    protocol = "acp"


class ShopifyUcpAdapter(_Unconfigured):
    """Will verify an operator-approved profile/discovery document before negotiating operations."""
    protocol = "ucp"


class A2AClient(_Unconfigured):
    protocol = "a2a"
