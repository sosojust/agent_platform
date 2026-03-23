"""Milvus 向量库操作，按 {tenant_id}_{collection_type} 隔离。"""
from pymilvus import MilvusClient, DataType
from config.settings import settings
from embedding.service import embedding_service
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)
VECTOR_DIM = 1024


class VectorStore:
    def __init__(self) -> None:
        self._client = MilvusClient(
            uri=f"http://{settings.milvus_host}:{settings.milvus_port}"
        )

    def _col(self, tenant_id: str, col_type: str) -> str:
        return f"{tenant_id.replace('-', '_')}_{col_type}"

    def ensure_collection(self, tenant_id: str, col_type: str) -> None:
        name = self._col(tenant_id, col_type)
        if self._client.has_collection(name):
            return
        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("id", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("text", DataType.VARCHAR, max_length=4096)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=VECTOR_DIM)
        idx = self._client.prepare_index_params()
        idx.add_index("vector", index_type="HNSW", metric_type="COSINE",
                      params={"M": 16, "efConstruction": 200})
        self._client.create_collection(collection_name=name, schema=schema, index_params=idx)
        logger.info("collection_created", name=name)

    def upsert(self, tenant_id: str, col_type: str, documents: list[dict]) -> None:
        self.ensure_collection(tenant_id, col_type)
        name = self._col(tenant_id, col_type)
        vectors = embedding_service.embed([d["text"] for d in documents])
        data = [{"id": d["id"], "text": d["text"], "vector": v,
                 **{k: v2 for k, v2 in d.items() if k not in ("id", "text")}}
                for d, v in zip(documents, vectors)]
        self._client.upsert(collection_name=name, data=data)

    def search(self, tenant_id: str, col_type: str, query: str,
               top_k: int = 20, filter_expr: str = "") -> list[dict]:
        self.ensure_collection(tenant_id, col_type)
        name = self._col(tenant_id, col_type)
        results = self._client.search(
            collection_name=name, data=[embedding_service.embed_one(query)],
            limit=top_k, filter=filter_expr, output_fields=["id", "text"],
        )
        return [{"id": h["id"], "text": h["entity"]["text"], "score": h["distance"]}
                for h in (results[0] if results else [])]


vector_store = VectorStore()
