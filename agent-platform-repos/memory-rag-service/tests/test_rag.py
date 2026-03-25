"""Memory RAG Service 测试。"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Tenant-Id": "test_tenant"},
    ) as c:
        yield c


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "memory-rag-service"


async def test_rag_retrieve(client):
    with patch("rag.pipeline.rag_pipeline.retrieve",
               new=AsyncMock(return_value=["团险保单条款第一条...", "理赔申请流程说明..."])):
        resp = await client.post("/rag/retrieve", json={
            "query": "如何申请理赔",
            "tenant_id": "test_tenant",
        })
    assert resp.status_code == 200
    assert len(resp.json()["documents"]) == 2


async def test_memory_append_and_get(client):
    with patch("memory.manager.memory_manager.append_short_term",
               new=AsyncMock(return_value=None)):
        resp = await client.post("/memory/append", json={
            "conversation_id": "conv_001",
            "role": "user",
            "content": "我想查询保单状态",
            "tenant_id": "test_tenant",
        })
    assert resp.status_code == 204

    with patch("memory.manager.memory_manager.build_memory_context",
               new=AsyncMock(return_value="【本次对话】\nuser: 我想查询保单状态")):
        resp = await client.post("/memory/get-context", json={
            "conversation_id": "conv_001",
            "query": "保单状态",
            "tenant_id": "test_tenant",
        })
    assert resp.status_code == 200
    assert "保单状态" in resp.json()["context"]
