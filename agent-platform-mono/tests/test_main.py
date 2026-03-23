"""主 API 集成测试。"""
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Tenant-Id": "tenant_test_001"},
    ) as c:
        yield c


async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


async def test_list_agents_includes_all_domains(client: AsyncClient):
    resp = await client.get("/agent/list")
    assert resp.status_code == 200
    ids = [a["agent_id"] for a in resp.json()]
    assert "policy-assistant" in ids
    assert "claim-assistant" in ids
    assert "customer-assistant" in ids


async def test_run_unknown_agent(client: AsyncClient):
    resp = await client.post("/agent/run", json={
        "agent_id": "unknown-agent",
        "input": "你好",
    })
    assert resp.status_code == 404


async def test_run_agent_returns_session_id(client: AsyncClient, mocker):
    mocker.patch(
        "main.registry.get",
        return_value=type("M", (), {
            "factory": lambda self: type("A", (), {
                "ainvoke": AsyncMock(return_value={
                    "messages": [type("Msg", (), {"content": "已为您查询"})()],
                    "step_count": 2,
                })
            })()
        })(),
    )
    from unittest.mock import AsyncMock
    resp = await client.post("/agent/run", json={
        "agent_id": "policy-assistant",
        "input": "查询保单 P2024001",
    })
    assert resp.status_code == 200
    assert "session_id" in resp.json()
