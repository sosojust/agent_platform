"""客服域 MCP Tools。"""
from typing import Any
from mcp.server.fastmcp import FastMCP
from core.tool_service.client.gateway import internal_gateway
from shared.logging.logger import get_logger

logger = get_logger(__name__)
mcp = FastMCP("customer-domain")


@mcp.tool()
async def query_customer_info(customer_id: str) -> dict[str, Any]:
    """
    查询客户（企业）基本信息。
    当用户询问企业联系方式、行业类型、客户经理是谁时调用。
    不含财务数据。
    """
    try:
        data = await internal_gateway.get(
            f"/customer-service/api/v1/customers/{customer_id}"
        )
        return {
            "customer_id": data["customerId"],
            "company_name": data["companyName"],
            "industry": data["industry"],
            "contact_name": data["contactName"],
            "contact_phone": data["contactPhone"],
            "account_manager": data["accountManager"]["name"],
        }
    except Exception as e:
        logger.error("query_customer_failed", customer_id=customer_id, error=str(e))
        return {"error": f"查询客户 {customer_id} 失败"}


@mcp.tool()
async def search_faq(question: str, top_k: int = 3) -> dict[str, Any]:
    """
    在 FAQ 知识库中检索常见问题答案。
    当用户询问通用的产品介绍、投保流程、理赔流程等常见问题时优先调用。
    比 RAG 检索更快，适合标准化问题。
    """
    try:
        data = await internal_gateway.get(
            "/customer-service/api/v1/faq/search",
            params={"q": question, "topK": top_k},
        )
        return {
            "results": [
                {"question": r["question"], "answer": r["answer"], "score": r["score"]}
                for r in data["items"]
            ]
        }
    except Exception as e:
        logger.error("search_faq_failed", error=str(e))
        return {"error": "FAQ 检索失败"}


@mcp.tool()
async def transfer_to_human(reason: str, conversation_id: str) -> dict[str, Any]:
    """
    转接人工客服。
    当用户明确要求转人工，或问题超出 Agent 能力范围时调用。
    reason 填写转接原因，便于人工客服快速了解背景。
    """
    try:
        data = await internal_gateway.post(
            "/customer-service/api/v1/transfer",
            body={"reason": reason, "sessionId": conversation_id},
        )
        return {
            "transferred": True,
            "queue_number": data.get("queueNumber"),
            "estimated_wait": data.get("estimatedWaitMinutes"),
        }
    except Exception as e:
        logger.error("transfer_to_human_failed", error=str(e))
        return {"error": "转接人工失败，请稍后重试或拨打客服电话"}


customer_tools: list[Any] = []
