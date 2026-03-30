from __future__ import annotations
from typing import Any, Dict, List, Sequence
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from shared.config.settings import settings
from core.memory_rag.vector.acl import VectorStoreAdapter
from core.memory_rag.embedding.gateway import embedding_gateway
from core.memory_rag.rag.filters import build_qdrant_filter


class QdrantProvider(VectorStoreAdapter):
    def __init__(self, url: str):
        self._client = QdrantClient(url=url)

    def create_collection(self, name: str, schema: Dict[str, Any]) -> None:
        dim = int(schema.get("vector_size") or len(embedding_gateway.embed(["warmup"])[0]))
        self._client.recreate_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    def upsert(self, collection: str, items: Sequence[Dict[str, Any]]) -> None:
        points: List[PointStruct] = []
        texts: List[str] = []
        idxs: List[int] = []
        for i, it in enumerate(items):
            vid = str(it.get("id"))
            text = str(it.get("text", ""))
            vec = it.get("vector")
            payload = dict(it.get("metadata") or {})
            payload["text"] = text
            if vec is None:
                texts.append(text)
                idxs.append(i)
            points.append(PointStruct(id=vid, vector=vec or [], payload=payload))
        if texts:
            vecs = embedding_gateway.embed(texts)
            for j, k in enumerate(idxs):
                points[k].vector = vecs[j]
        self._client.upsert(collection_name=collection, points=points)

    def add_texts(
        self,
        collection: str,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str] | None = None,
    ) -> List[str]:
        vectors = embedding_gateway.embed(texts)
        points = []
        out_ids: List[str] = []
        for i, text in enumerate(texts):
            pid = ids[i] if ids else None
            pid = pid or f"{collection}-{i}"
            payload = dict(metadatas[i] or {})
            payload["text"] = text
            points.append(PointStruct(id=pid, vector=vectors[i], payload=payload))
            out_ids.append(pid)
        self._client.upsert(collection_name=collection, points=points)
        return out_ids

    def search(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int,
        filter_ast: Dict[str, Any] | None = None,
        with_vectors: bool = False,
    ) -> List[Dict[str, Any]]:
        qfilter = build_qdrant_filter(filter_ast)
        res = self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qfilter,
            with_payload=True,
            with_vectors=with_vectors,
        )
        out: List[Dict[str, Any]] = []
        for r in res:
            item: Dict[str, Any] = {"id": str(r.id), "score": float(r.score), "metadata": dict(r.payload or {})}
            if with_vectors and getattr(r, "vector", None) is not None:
                item["vector"] = list(r.vector)
            out.append(item)
        return out

    def delete(self, collection: str, ids: List[str]) -> int:
        self._client.delete(collection_name=collection, points_selector=ids)
        return len(ids)

    def by_ids(self, collection: str, ids: List[str]) -> List[Dict[str, Any]]:
        res = self._client.retrieve(collection_name=collection, ids=ids, with_payload=True, with_vectors=False)
        out: List[Dict[str, Any]] = []
        for r in res:
            out.append({"id": str(r.id), "metadata": dict(r.payload or {})})
        return out

    def list_collections(self) -> List[str]:
        res = self._client.get_collections()
        return [c.name for c in res.collections or []]


if settings.vector_db.backend.lower() == "qdrant":
    vector_gateway = QdrantProvider(settings.vector_db.qdrant_url)
else:
    vector_gateway = QdrantProvider(settings.vector_db.qdrant_url)
