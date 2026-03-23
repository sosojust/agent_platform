"""保单域 MCP Tools。"""
from mcp.server.fastmcp import FastMCP
from client.gateway import gateway_client
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)
mcp = FastMCP("policy")


@mcp.tool()
async def query_policy_basic(policy_id: str) -> dict:
    """
    查询保单基本信息。
    当用户询问保单状态、生效日期、到期日期、承保金额、投保人或被保险人时调用。
    需要明确的 policy_id（保单号）。
    """
    try:
        data = await gateway_client.get(f"/policy-service/api/v1/policies/{policy_id}/basic")
        return {
            "policy_id": data["policyId"], "status": data["status"],
            "effective_date": data["effectiveDate"], "expiry_date": data["expiryDate"],
            "insured_amount": data["insuredAmount"],
            "policyholder": data["policyholder"]["name"],
        }
    except Exception as e:
        logger.error("query_policy_basic_failed", policy_id=policy_id, error=str(e))
        return {"error": f"查询保单 {policy_id} 失败，请确认保单号是否正确"}


@mcp.tool()
async def list_policies_by_company(
    company_id: str, status: str = "ACTIVE", page: int = 1, page_size: int = 10
) -> dict:
    """
    查询企业名下的保单列表。
    当用户询问某企业有哪些保单、保单总数时调用。
    status 可选：ACTIVE（有效）、EXPIRED（到期）、ALL（全部）。
    """
    try:
        data = await gateway_client.get(
            f"/policy-service/api/v1/companies/{company_id}/policies",
            params={"status": status, "page": page, "pageSize": page_size},
        )
        return {
            "total": data["total"],
            "policies": [{"policy_id": p["policyId"], "product_name": p["productName"],
                          "status": p["status"], "expiry_date": p["expiryDate"]}
                         for p in data["items"]],
        }
    except Exception as e:
        logger.error("list_policies_failed", company_id=company_id, error=str(e))
        return {"error": "查询保单列表失败"}


policy_tools = mcp.get_tools()
