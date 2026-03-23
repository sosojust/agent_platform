"""Agent Service API 测试。"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Tenant-Id": "test_tenant_001"},
    ) as c:
        yield c


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "agent-service"


async def test_list_agents_has_all_domains(client):
    resp = await client.get("/agent/list")
    assert resp.status_code == 200
    ids = [a["agent_id"] for a in resp.json()]
    assert "policy-assistant" in ids
    assert "claim-assistant" in ids
    assert "customer-assistant" in ids


async def test_run_unknown_agent(client):
    resp = await client.post("/agent/run", json={
        "agent_id": "non-existent",
        "input": "你好",
    })
    assert resp.status_code == 404


async def test_stream_response_is_sse(client):
    """验证 /agent/stream 返回 SSE content-type。"""
    with patch("main.registry.get") as mock_get:
        mock_agent = MagicMock()

        async def mock_events(*args, **kwargs):
            yield {"event": "on_chat_model_stream",
                   "data": {"chunk": MagicMock(content="你好")}}

        mock_agent.astream_events = mock_events
        mock_get.return_value = MagicMock(
            factory=lambda: mock_agent,
            rag_top_k_recall=20,
            rag_top_k_rerank=5,
        )

        with patch("main.get_checkpointer", new=AsyncMock(return_value=MagicMock())):
            resp = await client.post("/agent/stream", json={
                "agent_id": "policy-assistant",
                "input": "查保单",
            })

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
