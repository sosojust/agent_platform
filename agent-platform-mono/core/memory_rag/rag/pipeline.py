from __future__ import annotations
from typing import List
from core.memory_rag.embedding.gateway import embedding_gateway
from core.memory_rag.vector.store import vector_gateway
from core.memory_rag.rerank.service import rerank_gateway


class RagGateway:
    def retrieve(
        self,
        query: str,
        tenant_id: str,
        collection_type: str,
        top_k_recall: int,
        top_k_rerank: int,
        rewrite: bool,
    ) -> List[str]:
        collection = f"{tenant_id}_{collection_type}"
        qvec = embedding_gateway.embed([query])[0]
        f = {"AND": [{"EQ": ["tenant_id", tenant_id]}]}
        hits = vector_gateway.search(collection, qvec, top_k_recall, filter_ast=f)
        docs = [h["metadata"].get("text", "") for h in hits]
        if not docs:
            return []
        ranked = rerank_gateway.rerank(query, docs, top_k_rerank)
        return ranked


rag_gateway = RagGateway()
