"""主 API 集成测试。"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.gateway.app import app


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
    from domain_agents.policy.register import register as register_policy
    from domain_agents.claim.register import register as register_claim
    from domain_agents.customer.register import register as register_customer
    register_policy()
    register_claim()
    register_customer()
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


async def test_run_agent_returns_conversation_id(client: AsyncClient, monkeypatch):
    from unittest.mock import AsyncMock

    # Create mock objects to replace registry.get and its return value
    mock_agent_instance = type("A", (), {
        "ainvoke": AsyncMock(return_value={
            "messages": [type("Msg", (), {"content": "已为您查询"})()],
            "step_count": 2,
        })
    })()
    
    mock_agent_model = type("M", (), {
        "factory": lambda self: mock_agent_instance
    })()
    
    monkeypatch.setattr("app.gateway.routers.agents.agent_gateway.get", lambda x: mock_agent_model)
    resp = await client.post("/agent/run", json={
        "agent_id": "policy-assistant",
        "input": "查询保单 P2024001",
    })
    assert resp.status_code == 200
    assert "conversation_id" in resp.json()
