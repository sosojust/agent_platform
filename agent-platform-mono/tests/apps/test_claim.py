"""理赔域测试。"""
import pytest
from unittest.mock import AsyncMock, patch


async def test_query_claim_status_approved():
    from apps.claim.tools.claim_tools import query_claim_status
    mock_data = {
        "claimId": "C2024001", "status": "APPROVED",
        "currentStep": "待赔付", "submitDate": "2024-06-01",
        "expectedCompleteDate": "2024-06-10", "rejectReason": None,
    }
    with patch("apps.claim.tools.claim_tools.gateway_client.get",
               new=AsyncMock(return_value=mock_data)):
        result = await query_claim_status("C2024001")
    assert result["status"] == "APPROVED"
    assert result["reject_reason"] is None


async def test_query_claim_status_rejected():
    from apps.claim.tools.claim_tools import query_claim_status
    mock_data = {
        "claimId": "C2024002", "status": "REJECTED",
        "currentStep": "审核完成", "submitDate": "2024-06-01",
        "expectedCompleteDate": None, "rejectReason": "材料不齐全，缺少诊断证明",
    }
    with patch("apps.claim.tools.claim_tools.gateway_client.get",
               new=AsyncMock(return_value=mock_data)):
        result = await query_claim_status("C2024002")
    assert result["status"] == "REJECTED"
    assert "诊断证明" in result["reject_reason"]


async def test_claim_memory_config():
    """验证理赔域的 memory config 参数符合预期"""
    from apps.claim.memory_config import CLAIM_MEMORY_CONFIG
    assert CLAIM_MEMORY_CONFIG.long_term_enabled is True
    assert CLAIM_MEMORY_CONFIG.short_term_max_turns > 20   # 理赔对话轮次多
    assert CLAIM_MEMORY_CONFIG.max_steps >= 15             # 理赔步骤多
