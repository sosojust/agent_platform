"""理赔域 MCP Tools。"""
from mcp.server.fastmcp import FastMCP
from core.tool_service.client.gateway import gateway_client
from shared.logging.logger import get_logger

logger = get_logger(__name__)
mcp = FastMCP("claim-domain")


@mcp.tool()
async def query_claim_status(claim_id: str) -> dict:
    """
    查询理赔进度和当前状态。
    当用户询问理赔申请的审核进度、当前环节、是否赔付或被拒绝时调用。
    """
    try:
        data = await gateway_client.get(f"/claim-service/api/v1/claims/{claim_id}/status")
        return {
            "claim_id": data["claimId"],
            "status": data["status"],
            "current_step": data["currentStep"],
            "submit_date": data["submitDate"],
            "expected_complete_date": data.get("expectedCompleteDate"),
            "reject_reason": data.get("rejectReason"),
        }
    except Exception as e:
        logger.error("query_claim_status_failed", claim_id=claim_id, error=str(e))
        return {"error": f"查询理赔 {claim_id} 状态失败"}


@mcp.tool()
async def list_claims_by_policy(policy_id: str) -> dict:
    """
    查询某张保单下的所有理赔记录。
    当用户询问某保单历史上发生过哪些理赔、理赔总金额时调用。
    """
    try:
        data = await gateway_client.get(
            "/claim-service/api/v1/claims", params={"policyId": policy_id}
        )
        return {
            "total": data["total"],
            "claims": [
                {"claim_id": c["claimId"], "status": c["status"],
                 "claim_amount": c["claimAmount"], "submit_date": c["submitDate"]}
                for c in data["items"]
            ],
        }
    except Exception as e:
        logger.error("list_claims_failed", policy_id=policy_id, error=str(e))
        return {"error": "查询理赔记录失败"}


claim_tools = []
