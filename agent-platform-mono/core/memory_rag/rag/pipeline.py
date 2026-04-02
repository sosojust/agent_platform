from __future__ import annotations
from typing import List
from core.ai_core.llm.client import llm_gateway
from core.ai_core.embedding.provider import get_embedding_provider
from core.memory_rag.vector.store import vector_gateway
from core.memory_rag.rerank.service import rerank_gateway


class RagGateway:
    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        collection_type: str,
        top_k_recall: int,
        top_k_rerank: int,
        rewrite: bool,
    ) -> List[str]:
        final_query = await self._rewrite_query(query, collection_type, rewrite)
        collection = f"{tenant_id}_{collection_type}"
        qvec = get_embedding_provider().embed([final_query])[0]
        f = {"AND": [{"EQ": ["tenant_id", tenant_id]}]}
        hits = vector_gateway.search(collection, qvec, top_k_recall, filter_ast=f)
        docs = [h["metadata"].get("text", "") for h in hits]
        if not docs:
            return []
        ranked = rerank_gateway.rerank(final_query, docs, top_k_rerank)
        return ranked

    async def _rewrite_query(self, query: str, collection_type: str, rewrite: bool) -> str:
        if not rewrite:
            return str(query)
        scene_map = {
            "policy": "policy_rag_rewrite",
            "claim": "claim_rag_rewrite",
            "customer": "customer_intent",
        }
        scene = scene_map.get(str(collection_type), "policy_rag_rewrite")
        llm = llm_gateway.get_chat([], scene=scene)
        try:
            response = await llm.ainvoke(
                [
                    {
                        "role": "system",
                        "content": "你是检索改写助手。请将用户问题改写成更适合知识库召回的一句话，不要解释。",
                    },
                    {"role": "user", "content": str(query)},
                ]
            )
            rewritten = str(getattr(response, "content", "")).strip()
            return rewritten or str(query)
        except Exception:
            return str(query)


rag_gateway = RagGateway()
