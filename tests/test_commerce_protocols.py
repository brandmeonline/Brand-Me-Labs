"""ACP/UCP/A2A are explicitly unconfigured contract gates (BM-COM-015/016)."""

import pytest

from brandme_core.domains.commerce import protocols
from brandme_core.domains.providers.contracts import ProviderError, ProviderErrorKind
from brandme_core.mcp import McpToolExecutor


def test_only_ap2_is_pinned():
    pinned = {k: v.pinned_version for k, v in protocols.PROTOCOLS.items() if v.state == "implemented"}
    assert pinned == {"ap2": "0.2"}
    for name in ("acp", "ucp", "a2a"):
        assert protocols.PROTOCOLS[name].state == "unconfigured" and protocols.PROTOCOLS[name].pinned_version is None


@pytest.mark.parametrize("cls,op", [(protocols.AcpCheckoutAdapter, "create_checkout"),
                                    (protocols.ShopifyUcpAdapter, "discover"),
                                    (protocols.A2AClient, "send_task")])
def test_unconfigured_adapters_fail_closed(cls, op):
    with pytest.raises(ProviderError) as e:
        getattr(cls(), op)()
    assert e.value.kind is ProviderErrorKind.NOT_CONFIGURED


def test_no_agent_card_and_no_protocol_tools_advertised():
    assert protocols.agent_card() is None
    names = [t["name"] for t in McpToolExecutor.list_tools()["tools"]]
    assert not any(n.startswith(("acp.", "ap2.", "ucp.", "a2a.")) for n in names)
