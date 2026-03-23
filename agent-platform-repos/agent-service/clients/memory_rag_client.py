"""调用 memory-rag-service 的 HTTP 客户端。"""
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


class MemoryRagClient:

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.memory_rag_url,
            timeout=30.0,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8),
           retry=retry_if_exception_type(httpx.TransportError), reraise=True)
    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        collection_type: str = "business",
        top_k_recall: int = 20,
        top_k_rerank: int = 5,
        rewrite: bool = True,
    ) -> list[str]:
        """RAG 检索，返回相关文档片段列表。"""
        resp = await self._client.post(
            "/rag/retrieve",
            json={"query": query, "tenant_id": tenant_id,
                  "collection_type": collection_type,
                  "top_k_recall": top_k_recall,
                  "top_k_rerank": top_k_rerank,
                  "rewrite": rewrite},
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()["documents"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8),
           retry=retry_if_exception_type(httpx.TransportError), reraise=True)
    async def get_memory_context(
        self, session_id: str, query: str, tenant_id: str
    ) -> str:
        """获取 session 记忆上下文。"""
        resp = await self._client.post(
            "/memory/get-context",
            json={"session_id": session_id, "query": query, "tenant_id": tenant_id},
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()["context"]

    async def append_memory(
        self, session_id: str, role: str, content: str, tenant_id: str
    ) -> None:
        """追加对话到短期记忆（fire-and-forget，失败不阻断主流程）。"""
        try:
            resp = await self._client.post(
                "/memory/append",
                json={"session_id": session_id, "role": role,
                      "content": content, "tenant_id": tenant_id},
                headers=_headers(),
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("memory_append_failed", error=str(e))

    async def close(self) -> None:
        await self._client.aclose()


memory_rag_client = MemoryRagClient()
