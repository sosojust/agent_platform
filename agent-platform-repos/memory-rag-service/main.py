"""
Memory RAG Service — FastAPI 入口（port 8003）。

readiness 检查项：
  - models：embedding + rerank 模型加载完成
  - redis：Redis 连通性
  - milvus：Milvus 连通性
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException

from config.settings import settings
from agent_platform_shared.config.nacos import init_nacos_config
from agent_platform_shared.logging.logger import configure_logging, get_logger
from agent_platform_shared.fastapi_utils import create_app, ReadinessRegistry
from agent_platform_shared.models.schemas import (
    RAGRetrieveRequest, RAGRetrieveResponse,
    MemoryGetRequest, MemoryGetResponse, MemoryAppendRequest,
)
from rag.pipeline import rag_pipeline
from memory.manager import memory_manager
from embedding.service import embedding_service
from rerank.service import rerank_service

configure_logging(settings.log_level)
logger = get_logger(__name__)

# ── Readiness ─────────────────────────────────────────────────
readiness = ReadinessRegistry()


async def _check_redis() -> bool:
    try:
        r = await memory_manager._r()
        await r.ping()
        return True
    except Exception:
        return False


async def _check_milvus() -> bool:
    try:
        from vector.store import vector_store
        vector_store._client.list_collections()
        return True
    except Exception:
        return False


# ── Lifespan ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app) -> AsyncIterator[None]:
    init_nacos_config(settings)
    logger.info("loading_models")
    embedding_service.embed(["warmup"])
    rerank_service.rerank("warmup", ["test"], top_k=1)
    readiness.mark_ready("models")
    readiness.register_check("redis", _check_redis)
    readiness.register_check("milvus", _check_milvus)
    yield


# ── App ───────────────────────────────────────────────────────
app = create_app(
    title="Memory RAG Service",
    service_name="memory-rag-service",
    version="0.1.0",
    readiness_registry=readiness,
    lifespan=lifespan,
)

# ── 业务路由 ──────────────────────────────────────────────────
router = APIRouter()


@router.post("/rag/retrieve", response_model=RAGRetrieveResponse)
async def rag_retrieve(request: RAGRetrieveRequest) -> RAGRetrieveResponse:
    try:
        docs = await rag_pipeline.retrieve(
            query=request.query, tenant_id=request.tenant_id,
            collection_type=request.collection_type,
            top_k_recall=request.top_k_recall,
            top_k_rerank=request.top_k_rerank, rewrite=request.rewrite,
        )
        return RAGRetrieveResponse(documents=docs)
    except Exception as e:
        logger.error("rag_retrieve_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/get-context", response_model=MemoryGetResponse)
async def memory_get_context(request: MemoryGetRequest) -> MemoryGetResponse:
    try:
        context = await memory_manager.build_memory_context(
            session_id=request.session_id, query=request.query,
            tenant_id=request.tenant_id,
        )
        return MemoryGetResponse(context=context)
    except Exception as e:
        logger.error("memory_get_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/append", status_code=204)
async def memory_append(request: MemoryAppendRequest) -> None:
    try:
        await memory_manager.append_short_term(
            session_id=request.session_id, role=request.role,
            content=request.content, tenant_id=request.tenant_id,
        )
    except Exception as e:
        logger.error("memory_append_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embedding/embed")
async def embed(texts: list[str]) -> dict:
    try:
        return {"vectors": embedding_service.embed(texts),
                "dimension": embedding_service.dimension}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.include_router(router)
