"""主 API 集成测试。"""
from collections.abc import AsyncIterator
import pytest
from httpx import AsyncClient, ASGITransport
from app.gateway.app import app
from shared.observability.metrics_gateway import metrics_gateway


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Tenant-Id": "tenant_test_001"},
    ) as c:
        yield c


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


async def test_list_agents_includes_all_domains(client: AsyncClient) -> None:
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


async def test_run_unknown_agent(client: AsyncClient) -> None:
    resp = await client.post("/agent/run", json={
        "agent_id": "unknown-agent",
        "input": "你好",
    })
    assert resp.status_code == 404


async def test_run_agent_returns_conversation_id(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    
    monkeypatch.setattr(
        "app.gateway.routers.agents.agent_gateway.get", lambda x: mock_agent_model
    )
    resp = await client.post("/agent/run", json={
        "agent_id": "policy-assistant",
        "input": "查询保单 P2024001",
    })
    assert resp.status_code == 200
    assert "conversation_id" in resp.json()


async def test_observability_subagent_dashboard(client: AsyncClient) -> None:
    metrics_gateway.reset()
    metrics_gateway.record_batch(
        {
            "tenant_id": "tenant_test_001",
            "parent_agent_id": "lead-agent",
            "task_count": 2,
            "success_count": 2,
            "error_count": 0,
            "batch_duration_ms": 123,
        }
    )
    metrics_gateway.record_aggregation(
        {
            "tenant_id": "tenant_test_001",
            "parent_agent_id": "lead-agent",
            "strategy": "vote",
            "aggregation_duration_ms": 12,
        }
    )

    resp = await client.get("/observability/subagents")

    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["batch_count"] >= 1
    assert data["summary"]["task_count"] >= 2
    assert data["recent_batches"][0]["parent_agent_id"] == "lead-agent"
    assert data["storage_backend"] in {"memory", "redis"}

    scoped_resp = await client.get(
        "/observability/subagents",
        params={"tenant_id": "tenant_test_001", "parent_agent_id": "lead-agent"},
    )
    assert scoped_resp.status_code == 200
    scoped_data = scoped_resp.json()
    assert scoped_data["summary"]["batch_count"] >= 1
