"""客服域 MCP Tools。"""
from mcp.server.fastmcp import FastMCP
from client.gateway import gateway_client
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)
mcp = FastMCP("customer")


@mcp.tool()
async def query_customer_info(customer_id: str) -> dict:
    """
    查询客户（企业）基本信息。
    当用户询问企业联系方式、行业类型、客户经理是谁时调用。
    """
    try:
        data = await gateway_client.get(
            f"/customer-service/api/v1/customers/{customer_id}"
        )
        return {
            "customer_id": data["customerId"], "company_name": data["companyName"],
            "industry": data["industry"], "contact_name": data["contactName"],
            "contact_phone": data["contactPhone"],
            "account_manager": data["accountManager"]["name"],
        }
    except Exception as e:
        logger.error("query_customer_failed", customer_id=customer_id, error=str(e))
        return {"error": f"查询客户 {customer_id} 失败"}


@mcp.tool()
async def search_faq(question: str, top_k: int = 3) -> dict:
    """
    FAQ 知识库检索。
    当用户询问通用的产品介绍、投保流程、理赔流程等常见问题时优先调用。
    """
    try:
        data = await gateway_client.get(
            "/customer-service/api/v1/faq/search",
            params={"q": question, "topK": top_k},
        )
        return {"results": [{"question": r["question"], "answer": r["answer"]}
                             for r in data["items"]]}
    except Exception as e:
        logger.error("search_faq_failed", error=str(e))
        return {"error": "FAQ 检索失败"}


@mcp.tool()
async def transfer_to_human(reason: str, session_id: str) -> dict:
    """
    转接人工客服。
    当用户明确要求转人工，或问题超出 Agent 能力范围时调用。
    """
    try:
        data = await gateway_client.post(
            "/customer-service/api/v1/transfer",
            body={"reason": reason, "sessionId": session_id},
        )
        return {"transferred": True, "queue_number": data.get("queueNumber"),
                "estimated_wait": data.get("estimatedWaitMinutes")}
    except Exception as e:
        logger.error("transfer_to_human_failed", error=str(e))
        return {"error": "转接人工失败，请稍后重试或拨打客服电话"}


customer_tools = mcp.get_tools()
