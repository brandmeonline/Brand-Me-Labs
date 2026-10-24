"""Legacy GraphRAG (``brandme-agents/agentic/graph_rag.py``, unwired) refuses outright.

The agentic image pins ``langchain-anthropic==0.1.1`` with ``anthropic==0.18.1``. That ChatAnthropic
has no ``api_key``/``base_url`` fields (they land in ``model_kwargs``, in plain text), and its validator
builds ``anthropic.Client(api_key=... or os.environ["ANTHROPIC_API_KEY"])`` with no base URL or HTTP
client, so the SDK takes ``ANTHROPIC_BASE_URL``, ``ANTHROPIC_AUTH_TOKEN`` and the ambient proxy from the
environment whatever arguments it is given. No construction keeps app code off ambient ``ANTHROPIC_*``
settings, so GraphRAG builds no client and reads no key at all.

The pinned LangChain packages are not installed in the test environment; they are stubbed here so the
module itself is exercised. The stubs record any client construction.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
AGENTIC = REPO / "brandme-agents" / "agentic"
PKG = "_brandme_legacy_agentic"
DEV_KEY = "sk-ant-api03-" + "d" * 40  # fake


def _load(monkeypatch):
    built = []

    class Recorder:
        def __init__(self, *args, **kwargs):
            built.append(type(self).__name__)

    stubs = {
        "langchain": types.ModuleType("langchain"),
        "langchain.prompts": types.ModuleType("langchain.prompts"),
        "langchain.schema": types.ModuleType("langchain.schema"),
        "langchain_anthropic": types.ModuleType("langchain_anthropic"),
        "openai": types.ModuleType("openai"),
        "numpy": types.ModuleType("numpy"),
        PKG: types.ModuleType(PKG),
        PKG + ".graph_db": types.ModuleType(PKG + ".graph_db"),
    }
    stubs["langchain.prompts"].ChatPromptTemplate = Recorder
    stubs["langchain.schema"].HumanMessage = stubs["langchain.schema"].SystemMessage = Recorder
    stubs["langchain_anthropic"].ChatAnthropic = type("ChatAnthropic", (Recorder,), {})
    stubs["openai"].Client = type("OpenAIClient", (Recorder,), {})
    stubs[PKG].__path__ = [str(AGENTIC)]
    stubs[PKG + ".graph_db"].BrandMeKnowledgeGraph = object
    stubs[PKG + ".graph_db"].get_knowledge_graph = lambda: type("KnowledgeGraph", (Recorder,), {})()
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(PKG + ".graph_rag", AGENTIC / "graph_rag.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module, built


def test_legacy_graph_rag_refuses_even_with_a_dev_key(monkeypatch):
    monkeypatch.setenv("BRANDME_DEV_ANTHROPIC_API_KEY", DEV_KEY)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-" + "ant-api03-ambient-session-key-0000000000")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://ambient.invalid")
    rag, built = _load(monkeypatch)
    with pytest.raises(rag.GraphRAGDisabled) as e:
        rag.get_graph_rag()
    with pytest.raises(rag.GraphRAGDisabled):
        rag.GraphRAG(graph_db=object())
    assert built == []  # no Anthropic, OpenAI or graph client was ever built
    message = str(e.value)
    assert "disabled" in message and DEV_KEY not in message and "session-key" not in message
    assert "ambient.invalid" not in message
