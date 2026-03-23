"""
Memory RAG Service — FastAPI 入口（port 8003）。

对外接口：
  POST /rag/retrieve          向量召回 + rerank，返回相关文档片段
  POST /memory/get-context    获取会话记忆上下文（短期 + 长期）
  POST /memory/append         追加对话到短期记忆
  POST /embedding/embed       批量生成 embedding（供外部使用）
  GET  /health
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException

from config.settings import settings
from agent_platform_shared.config.nacos import init_nacos_config
from agent_platform_shared.logging.logger import configure_logging, get_logger
from agent_platform_shared.middleware.tenant import TenantContextMiddleware
from agent_platform_shared.models.schemas import (
    RAGRetrieveRequest, RAGRetrieveResponse,
    MemoryGetRequest, MemoryGetResponse, MemoryAppendRequest,
)
from rag.pipeline import rag_pipeline
from memory.manager import memory_manager
from embedding.service import embedding_service

configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("memory_rag_service_starting", port=settings.port)
    init_nacos_config(settings)
    yield
    logger.info("memory_rag_service_stopped")


app = FastAPI(title="Memory RAG Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(TenantContextMiddleware)


@app.post("/rag/retrieve", response_model=RAGRetrieveResponse)
async def rag_retrieve(request: RAGRetrieveRequest) -> RAGRetrieveResponse:
    """RAG 检索：查询改写 → 向量召回 → rerank → 返回 top-k 文档。"""
    try:
        docs = await rag_pipeline.retrieve(
            query=request.query,
            tenant_id=request.tenant_id,
            collection_type=request.collection_type,
            top_k_recall=request.top_k_recall,
            top_k_rerank=request.top_k_rerank,
            rewrite=request.rewrite,
        )
        return RAGRetrieveResponse(documents=docs)
    except Exception as e:
        logger.error("rag_retrieve_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory/get-context", response_model=MemoryGetResponse)
async def memory_get_context(request: MemoryGetRequest) -> MemoryGetResponse:
    """获取注入 Prompt 的记忆上下文（短期对话历史 + 长期用户记忆）。"""
    try:
        context = await memory_manager.build_memory_context(
            session_id=request.session_id,
            query=request.query,
            tenant_id=request.tenant_id,
        )
        return MemoryGetResponse(context=context)
    except Exception as e:
        logger.error("memory_get_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory/append", status_code=204)
async def memory_append(request: MemoryAppendRequest) -> None:
    """追加一轮对话到短期记忆，超限时自动压缩写入长期记忆。"""
    try:
        await memory_manager.append_short_term(
            session_id=request.session_id,
            role=request.role,
            content=request.content,
            tenant_id=request.tenant_id,
        )
    except Exception as e:
        logger.error("memory_append_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/embedding/embed")
async def embed(texts: list[str]) -> dict:
    """批量生成 embedding 向量。"""
    try:
        vectors = embedding_service.embed(texts)
        return {"vectors": vectors, "dimension": embedding_service.dimension}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "memory-rag-service", "env": settings.app_env}
