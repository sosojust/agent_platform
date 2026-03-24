"""保单域测试。"""
import pytest
from unittest.mock import AsyncMock, patch


async def test_query_policy_basic_success():
    from apps.policy.tools.policy_tools import query_policy_basic
    mock_data = {
        "policyId": "P2024001", "status": "ACTIVE",
        "effectiveDate": "2024-01-01", "expiryDate": "2025-01-01",
        "insuredAmount": 500000, "policyholder": {"name": "测试科技有限公司"},
    }
    with patch("apps.policy.tools.policy_tools.gateway_client.get",
               new=AsyncMock(return_value=mock_data)):
        result = await query_policy_basic("P2024001")
    assert result["status"] == "ACTIVE"
    assert result["policyholder"] == "测试科技有限公司"
    assert "error" not in result


async def test_query_policy_basic_not_found():
    from apps.policy.tools.policy_tools import query_policy_basic
    with patch("apps.policy.tools.policy_tools.gateway_client.get",
               new=AsyncMock(side_effect=Exception("404"))):
        result = await query_policy_basic("P9999999")
    assert "error" in result


async def test_policy_register():
    """验证保单域注册后 agent_id 存在于注册表"""
    from core.agent_engine.agents.registry import registry
    from apps.policy.register import register
    register()
    assert registry.exists("policy-assistant")
    meta = registry.get("policy-assistant")
    assert meta is not None
    assert "policy" in meta.tags
    assert meta.memory_config.long_term_enabled is False  # 保单域不需要长期记忆
