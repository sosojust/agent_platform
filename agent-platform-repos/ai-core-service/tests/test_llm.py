"""AI Core Service 单元测试。"""
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
    assert resp.json()["service"] == "ai-core-service"


async def test_llm_complete(client):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "这是测试响应"
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 5
    mock_resp.usage.total_tokens = 15

    with patch("llm.client.acompletion", new=AsyncMock(return_value=mock_resp)):
        resp = await client.post("/llm/complete", json={
            "messages": [{"role": "user", "content": "你好"}],
            "task_type": "simple",
        })
    assert resp.status_code == 200
    assert resp.json()["output"] == "这是测试响应"


async def test_llm_stream_returns_ndjson(client):
    async def mock_stream(*args, **kwargs):
        for token in ["你", "好", "！"]:
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content=token))])

    with patch("llm.client.acompletion", new=AsyncMock(return_value=mock_stream())):
        resp = await client.post("/llm/stream", json={
            "messages": [{"role": "user", "content": "你好"}],
            "task_type": "complex",
        })
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
