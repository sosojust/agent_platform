"""
调用 mcp-service 的 HTTP 客户端。

agent-service 通过此客户端：
  1. 启动时拉取所有 tool schema，绑定到 LangGraph 的 LLM
  2. LLM 决策调用 tool 时，转发给 mcp-service 执行，返回结果
"""
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config.settings import settings
from agent_platform_shared.logging.logger import get_logger
from agent_platform_shared.middleware.tenant import get_current_tenant_id, get_current_trace_id

logger = get_logger(__name__)


def _headers() -> dict:
    return {
        "X-Tenant-Id": get_current_tenant_id(),
        "X-Trace-Id": get_current_trace_id(),
        "Content-Type": "application/json",
    }


class MCPClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.mcp_url,
            timeout=30.0,
        )

    async def list_tools(self) -> list[dict]:
        """拉取所有已注册 tool 的 schema。启动时调用一次。"""
        try:
            resp = await self._client.get("/tools/list", headers=_headers())
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("mcp_list_tools_failed", error=str(e))
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True,
    )
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """执行指定 tool，返回结果。LangGraph ToolNode 调用路径。"""
        resp = await self._client.post(
            "/tools/call",
            json={"tool_name": tool_name, "arguments": arguments},
            headers=_headers(),
        )
        resp.raise_for_status()
        result = resp.json()["result"]
        logger.info("mcp_tool_called", tool=tool_name)
        return result

    async def close(self) -> None:
        await self._client.aclose()


mcp_client = MCPClient()
