from types import SimpleNamespace
from typing import Any
import pytest

from core.memory_rag.rag.pipeline import RagGateway


async def test_rewrite_query_uses_scene_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = RagGateway()
    captured: dict[str, str] = {}

    class _FakeChat:
        async def ainvoke(self, messages: list[dict[str, str]]) -> Any:
            return SimpleNamespace(content="改写结果")

    def _fake_get_chat(
        tools: list[Any], task_type: str = "complex", scene: str | None = None
    ) -> _FakeChat:
        captured["scene"] = str(scene or "")
        return _FakeChat()

    monkeypatch.setattr("core.memory_rag.rag.pipeline.llm_gateway.get_chat", _fake_get_chat)
    rewritten = await gateway._rewrite_query("原问题", "claim", True)
    assert rewritten == "改写结果"
    assert captured["scene"] == "claim_rag_rewrite"


async def test_retrieve_pipeline_with_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = RagGateway()
    captured: dict[str, object] = {}

    async def _fake_rewrite(query: str, collection_type: str, rewrite: bool) -> str:
        captured["rewrite_input"] = query
        captured["rewrite_type"] = collection_type
        captured["rewrite_flag"] = rewrite
        return "重写查询"

    def _fake_embed(texts: list[str]) -> list[list[float]]:
        captured["embedded_texts"] = list(texts)
        return [[0.1, 0.2]]

    def _fake_search(
        collection: str, qvec: list[float], top_k: int, filter_ast: dict[str, Any] | None = None
    ) -> list[dict[str, dict[str, str]]]:
        captured["collection"] = collection
        captured["qvec"] = qvec
        captured["top_k"] = top_k
        captured["filter_ast"] = filter_ast
        return [{"metadata": {"text": "doc-a"}}, {"metadata": {"text": "doc-b"}}]

    def _fake_rerank(query: str, docs: list[str], top_k: int) -> list[str]:
        captured["rerank_query"] = query
        captured["rerank_docs"] = list(docs)
        captured["rerank_top_k"] = top_k
        return ["doc-b", "doc-a"]

    monkeypatch.setattr(gateway, "_rewrite_query", _fake_rewrite)
    monkeypatch.setattr("core.memory_rag.rag.pipeline.embedding_gateway.embed", _fake_embed)
    monkeypatch.setattr("core.memory_rag.rag.pipeline.vector_gateway.search", _fake_search)
    monkeypatch.setattr("core.memory_rag.rag.pipeline.rerank_gateway.rerank", _fake_rerank)

    out = await gateway.retrieve(
        query="原查询",
        tenant_id="t1",
        collection_type="policy",
        top_k_recall=4,
        top_k_rerank=2,
        rewrite=True,
    )
    assert out == ["doc-b", "doc-a"]
    assert captured["collection"] == "t1_policy"
    assert captured["embedded_texts"] == ["重写查询"]
    assert captured["rerank_query"] == "重写查询"
    assert captured["filter_ast"] == {"AND": [{"EQ": ["tenant_id", "t1"]}]}


async def test_rewrite_query_fallback_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = RagGateway()

    class _FailChat:
        async def ainvoke(self, messages: list[dict[str, str]]) -> Any:
            raise RuntimeError("failed")

    def _fake_get_chat(
        tools: list[Any], task_type: str = "complex", scene: str | None = None
    ) -> _FailChat:
        return _FailChat()

    monkeypatch.setattr("core.memory_rag.rag.pipeline.llm_gateway.get_chat", _fake_get_chat)
    rewritten = await gateway._rewrite_query("保留原问题", "policy", True)
    assert rewritten == "保留原问题"
