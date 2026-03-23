"""RAG Pipeline：查询改写 → 向量召回 → rerank。"""
import httpx
from config.settings import settings
from vector.store import vector_store
from rerank.service import rerank_service
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)


class RAGPipeline:
    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        collection_type: str = "business",
        top_k_recall: int = 20,
        top_k_rerank: int = 5,
        rewrite: bool = True,
    ) -> list[str]:
        search_query = await self._rewrite(query) if rewrite else query

        candidates = vector_store.search(
            tenant_id=tenant_id,
            col_type=collection_type,
            query=search_query,
            top_k=top_k_recall,
        )
        if not candidates:
            return []

        ranked = rerank_service.rerank(
            query=query,
            documents=[c["text"] for c in candidates],
            top_k=top_k_rerank,
        )
        results = [doc for _, score, doc in ranked if score > 0.3]
        logger.info("rag_retrieve", candidates=len(candidates), after_rerank=len(results))
        return results

    async def _rewrite(self, query: str) -> str:
        """调用 ai-core-service 的 /llm/complete 改写查询。"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.ai_core_url}/llm/complete",
                    json={
                        "messages": [{"role": "user", "content":
                            f"将以下问题改写为更适合向量检索的查询语句：\n{query}\n改写后："}],
                        "task_type": "simple",
                        "temperature": 0.0,
                        "max_tokens": 128,
                    },
                )
                return resp.json().get("output", query)
        except Exception:
            return query  # 改写失败时降级用原始查询


rag_pipeline = RAGPipeline()
