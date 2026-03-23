"""MCP Service tool 单元测试。"""
import pytest
from unittest.mock import AsyncMock, patch
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
    data = resp.json()
    assert data["service"] == "mcp-service"
    assert data["tool_count"] > 0


async def test_list_tools(client):
    resp = await client.get("/tools/list")
    assert resp.status_code == 200
    tools = resp.json()
    names = [t["name"] for t in tools]
    assert "query_policy_basic" in names
    assert "query_claim_status" in names
    assert "search_faq" in names


async def test_call_unknown_tool(client):
    resp = await client.post("/tools/call", json={
        "tool_name": "non_existent_tool",
        "arguments": {},
    })
    assert resp.status_code == 404


async def test_call_policy_tool_success(client):
    mock_data = {
        "policyId": "P2024001", "status": "ACTIVE",
        "effectiveDate": "2024-01-01", "expiryDate": "2025-01-01",
        "insuredAmount": 500000, "policyholder": {"name": "测试公司"},
    }
    with patch(
        "tools.policy_tools.gateway_client.get",
        new=AsyncMock(return_value=mock_data),
    ):
        resp = await client.post("/tools/call", json={
            "tool_name": "query_policy_basic",
            "arguments": {"policy_id": "P2024001"},
        })
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["status"] == "ACTIVE"
    assert result["policyholder"] == "测试公司"


async def test_call_policy_tool_error_fallback(client):
    """Gateway 调用失败时，tool 应返回友好错误而非 500。"""
    with patch(
        "tools.policy_tools.gateway_client.get",
        new=AsyncMock(side_effect=Exception("connection refused")),
    ):
        resp = await client.post("/tools/call", json={
            "tool_name": "query_policy_basic",
            "arguments": {"policy_id": "P9999999"},
        })
    assert resp.status_code == 200   # tool 内部处理了异常，返回 error 字段而非 500
    assert "error" in resp.json()["result"]


async def test_call_claim_tool(client):
    mock_data = {
        "claimId": "C2024001", "status": "REVIEWING",
        "currentStep": "医疗核查", "submitDate": "2024-06-01",
        "expectedCompleteDate": "2024-06-15", "rejectReason": None,
    }
    with patch(
        "tools.claim_tools.gateway_client.get",
        new=AsyncMock(return_value=mock_data),
    ):
        resp = await client.post("/tools/call", json={
            "tool_name": "query_claim_status",
            "arguments": {"claim_id": "C2024001"},
        })
    assert resp.status_code == 200
    assert resp.json()["result"]["status"] == "REVIEWING"
