"""
调用 ai-core-service 的 HTTP 客户端。

complete()：普通调用，等待完整响应，用于 RAG 查询改写等。
stream()：HTTP streaming 调用，逐 token yield，用于 Agent 主推理。
         消费 ai-core-service 的 NDJSON 格式响应（每行一个 JSON）。
"""
import json
from typing import AsyncIterator
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


class AICoreClient:

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.ai_core_url,
            timeout=60.0,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True,
    )
    async def complete(
        self,
        messages: list[dict],
        task_type: str = "simple",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """同步调用，返回完整文本。"""
        resp = await self._client.post(
            "/llm/complete",
            json={"messages": messages, "task_type": task_type,
                  "temperature": temperature, "max_tokens": max_tokens},
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()["output"]

    async def stream(
        self,
        messages: list[dict],
        task_type: str = "complex",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """
        流式调用，逐 token yield。
        消费 ai-core-service /llm/stream 的 NDJSON 响应。
        """
        async with httpx.AsyncClient(
            base_url=settings.ai_core_url,
            timeout=120.0,   # streaming 需要更长超时
        ) as client:
            async with client.stream(
                "POST",
                "/llm/stream",
                json={"messages": messages, "task_type": task_type,
                      "temperature": temperature, "max_tokens": max_tokens},
                headers=_headers(),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "token" in data:
                            yield data["token"]
                        elif data.get("done"):
                            break
                        elif "error" in data:
                            logger.error("ai_core_stream_error", error=data["error"])
                            raise RuntimeError(data["error"])
                    except json.JSONDecodeError:
                        logger.warning("ai_core_stream_invalid_line", line=line)

    async def get_prompt(self, name: str, tenant_id: str = "") -> str:
        """获取渲染后的 Prompt 模板。"""
        try:
            resp = await self._client.get(
                f"/prompt/{name}",
                params={"tenant_id": tenant_id},
                headers=_headers(),
            )
            resp.raise_for_status()
            return resp.json()["content"]
        except Exception as e:
            logger.warning("get_prompt_failed", name=name, error=str(e))
            return ""

    async def close(self) -> None:
        await self._client.aclose()


ai_core_client = AICoreClient()
