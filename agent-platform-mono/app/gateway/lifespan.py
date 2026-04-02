from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from qdrant_client import QdrantClient

from app.gateway.readiness import ReadinessRegistry
from core.tool_service.registry import tool_gateway
from shared.config.nacos import init_nacos_config
from shared.config.settings import settings
from shared.logging.logger import get_logger
from shared.internal_http.client import get_internal_api_client

logger = get_logger(__name__)
readiness = ReadinessRegistry()


async def _check_redis() -> bool:
    try:
        from core.memory_rag.memory.manager import memory_gateway

        redis_client = await memory_gateway._r()
        await redis_client.ping()
        return True
    except Exception:
        return False


async def _check_milvus() -> bool:
    try:
        from core.memory_rag.vector.store import vector_gateway

        vector_gateway.list_collections()
        return True
    except Exception:
        return False


async def _check_qdrant() -> bool:
    try:
        client = QdrantClient(url=settings.vector_db.qdrant_url, timeout=3)
        client.get_collections()
        return True
    except Exception:
        return False


async def _check_prompts() -> bool:
    try:
        from core.ai_core.prompt.manager import prompt_gateway

        _ = prompt_gateway.get("policy_agent_system", {"tenant_id": "ready_check"})
        return True
    except Exception:
        return False


async def _check_rag() -> bool:
    try:
        from core.ai_core.embedding.provider import get_embedding_provider
        from core.memory_rag.vector.store import vector_gateway

        get_embedding_provider().embed(["ready"])
        vector_gateway.list_collections()
        return True
    except Exception:
        return False


async def _check_rerank_available() -> bool:
    try:
        from core.memory_rag.rerank.service import rerank_gateway

        return getattr(rerank_gateway, "_model", None) is not None
    except Exception:
        return False


async def _check_prompts_source_langfuse() -> bool:
    try:
        from core.ai_core.prompt.provider import LangfusePromptProvider

        host = getattr(settings.observability, "langfuse_host", "")
        public_key = getattr(settings.observability, "langfuse_public_key", "")
        secret_key = getattr(settings.observability, "langfuse_secret_key", "")
        if not host or not public_key or not secret_key:
            return False
        provider = LangfusePromptProvider()
        prompt = provider.get("policy_agent_system")
        return prompt is not None and len(str(prompt)) > 0
    except Exception:
        return False


async def _check_rag_backend_qdrant() -> bool:
    try:
        backend = getattr(settings.vector_db, "backend", "")
        return str(backend).lower() == "qdrant"
    except Exception:
        return False


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("agent_platform_starting", env=settings.app_env)
    init_nacos_config(settings)

    logger.info("warming_up_models")
    try:
        from core.ai_core.embedding.provider import get_embedding_provider
        from core.memory_rag.rerank.service import rerank_gateway

        get_embedding_provider().embed(["warmup"])
        rerank_gateway.rerank("warmup", ["test"], top_k=1)
        readiness.mark_ready("models")
        logger.info("models_ready")
    except Exception as e:
        logger.error("model_warmup_failed", error=str(e))

    readiness.register_check("redis", _check_redis)
    readiness.register_check("milvus", _check_milvus)
    readiness.register_check("qdrant", _check_qdrant)
    readiness.register_check("prompts_ready", _check_prompts)
    readiness.register_check("prompts_source_langfuse", _check_prompts_source_langfuse)
    readiness.register_check("rag_ready", _check_rag)
    readiness.register_check("rag_backend_qdrant", _check_rag_backend_qdrant)
    readiness.register_check("rerank_available", _check_rerank_available)

    from domain_agents.policy.register import register as register_policy
    from domain_agents.claim.register import register as register_claim
    from domain_agents.customer.register import register as register_customer

    register_policy()
    register_claim()
    register_customer()
    domain_count = 3

    # 工具已通过 domain_agents 中的 @mcp.tool() 和 @skill 装饰器自动注册
    # 不需要额外的 MCP 客户端注册
    logger.info("tools_registered", count=len(tool_gateway.list_tools()))

    if domain_count > 0:
        readiness.mark_ready("domain_agents")
        logger.info("all_domains_ready", total=domain_count)
    else:
        logger.error("no_domains_registered")

    logger.info("agent_platform_started")
    yield
    await get_internal_api_client().close()
    logger.info("agent_platform_stopped")
