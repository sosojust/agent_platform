"""
Agent Platform — FastAPI 主入口（单体版）。

启动流程（顺序执行，全部完成后 /ready 才返回 200）：
  1. Nacos 动态配置
  2. Embedding / Rerank 模型预热（最慢，约 30~60s）
  3. 检查 Redis / Milvus / Qdrant 连通性
  4. 扫描 apps/ 自动注册所有 Agent

K8s probe 建议：
  liveness:  initialDelaySeconds: 15,  period: 30
  readiness: initialDelaySeconds: 90,  period: 10, failureThreshold: 12
"""
import importlib
import pkgutil
import uuid
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

import apps
from shared.config.settings import settings
from shared.config.nacos import init_nacos_config
from shared.logging.logger import configure_logging, get_logger
from shared.middleware.tenant import TenantContextMiddleware, get_current_tenant_id
from shared.models.schemas import AgentRunRequest, AgentRunResponse
from shared.fastapi_utils import ReadinessRegistry, make_health_router, register_error_handlers
from core.agent_engine.agents.registry import registry
from core.agent_engine.checkpoints.redis_checkpoint import get_checkpointer
from core.tool_service.client.gateway import gateway_client

configure_logging()
logger = get_logger(__name__)

# ── Readiness Registry ────────────────────────────────────────
# 单体：汇总所有模块的就绪条件
readiness = ReadinessRegistry()


# ── 动态检查函数（每次 /ready 调用时执行）───────────────────

async def _check_redis() -> bool:
    try:
        from core.memory_rag.memory.manager import memory_manager
        r = await memory_manager._r()
        await r.ping()
        return True
    except Exception:
        return False


async def _check_milvus() -> bool:
    try:
        from core.memory_rag.vector.store import vector_store
        vector_store._client.list_collections()
        return True
    except Exception:
        return False


async def _check_qdrant() -> bool:
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=settings.vector_db.qdrant_url, timeout=3)
        client.get_collections()
        return True
    except Exception:
        return False


# ── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("agent_platform_starting", env=settings.app_env)

    # 1. Nacos 动态配置（失败不阻断启动）
    init_nacos_config(settings)

    # 2. 预热 Embedding / Rerank 模型（这是最慢的步骤）
    #    预热完成前 /ready 返回 503，K8s 不分流量
    logger.info("warming_up_models")
    try:
        from core.memory_rag.embedding.service import embedding_service
        from core.memory_rag.rerank.service import rerank_service
        embedding_service.embed(["warmup"])
        rerank_service.rerank("warmup", ["test"], top_k=1)
        readiness.mark_ready("models")        # 模型加载完成
        logger.info("models_ready")
    except Exception as e:
        logger.error("model_warmup_failed", error=str(e))
        # 模型加载失败时不 mark_ready，/ready 持续返回 503

    # 3. 注册基础设施动态检查（每次 /ready 都会 ping）
    readiness.register_check("redis", _check_redis)
    readiness.register_check("milvus", _check_milvus)
    readiness.register_check("qdrant", _check_qdrant)

    # 4. 注册所有业务域的 Agent
    from apps.policy.register import register as register_policy
    from apps.claim.register import register as register_claim
    from apps.customer.register import register as register_customer

    register_policy()
    register_claim()
    register_customer()
    domain_count = 3

    # 所有域注册完成才标记 ready
    if domain_count > 0:
        readiness.mark_ready("apps")
        logger.info("all_domains_ready", total=domain_count)
    else:
        logger.error("no_domains_registered")

    logger.info("agent_platform_started")
    yield

    # ── 关闭阶段 ──
    await gateway_client.close()
    logger.info("agent_platform_stopped")


# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="Agent Platform",
    description="团险业务 Agent Platform",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(TenantContextMiddleware)

# 统一异常处理
register_error_handlers(app)

# 健康检查路由（自动挂载 /health 和 /ready）
app.include_router(make_health_router("agent-platform", readiness))


# ── 业务路由 ──────────────────────────────────────────────────

@app.post("/agent/run", response_model=AgentRunResponse, summary="同步运行 Agent")
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    """同步调用，等待完整响应。适合响应时间 < 10s 的简单查询。"""
    tenant_id = get_current_tenant_id()
    session_id = request.session_id or str(uuid.uuid4())

    agent_meta = registry.get(request.agent_id)
    if not agent_meta:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{request.agent_id}' not found. "
                   f"Available: {[a.agent_id for a in registry.list_all()]}",
        )

    agent = agent_meta.factory()
    checkpointer = await get_checkpointer()
    config = {"configurable": {"thread_id": session_id, "checkpointer": checkpointer}}
    initial_state = {
        "messages": [HumanMessage(content=request.input)],
        "session_id": session_id, "tenant_id": tenant_id,
        "memory_context": "", "rag_context": "", "step_count": 0,
    }

    try:
        result = await agent.ainvoke(initial_state, config=config)
        output = str(result["messages"][-1].content)
        logger.info("agent_run_complete", agent_id=request.agent_id,
                    session_id=session_id, steps=result["step_count"])
        return AgentRunResponse(session_id=session_id, output=output,
                                steps=[{"step_count": result["step_count"]}])
    except Exception as e:
        logger.error("agent_run_failed", agent_id=request.agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/stream", summary="流式运行 Agent（SSE）")
async def stream_agent(request: AgentRunRequest) -> StreamingResponse:
    """SSE 流式输出，事件类型：token | step_start | step_end | done | error"""
    tenant_id = get_current_tenant_id()
    session_id = request.session_id or str(uuid.uuid4())

    agent_meta = registry.get(request.agent_id)
    if not agent_meta:
        raise HTTPException(status_code=404,
                            detail=f"Agent '{request.agent_id}' not found")

    agent = agent_meta.factory()
    checkpointer = await get_checkpointer()
    config = {"configurable": {"thread_id": session_id, "checkpointer": checkpointer}}
    initial_state = {
        "messages": [HumanMessage(content=request.input)],
        "session_id": session_id, "tenant_id": tenant_id,
        "memory_context": "", "rag_context": "", "step_count": 0,
    }

    async def event_generator():
        try:
            async for event in agent.astream_events(
                initial_state, config=config, version="v2"
            ):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    token = event["data"]["chunk"].content
                    if token:
                        yield f"data: {json.dumps({'event': 'token', 'data': token})}\n\n"
                elif kind == "on_tool_start":
                    yield f"data: {json.dumps({'event': 'step_start', 'data': event['name']})}\n\n"
                elif kind == "on_tool_end":
                    yield f"data: {json.dumps({'event': 'step_end', 'data': event['name']})}\n\n"
            yield f"data: {json.dumps({'event': 'done', 'data': None})}\n\n"
        except Exception as e:
            logger.error("agent_stream_error", error=str(e))
            yield f"data: {json.dumps({'event': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/agent/list", summary="列出所有已注册的 Agent")
async def list_agents() -> list[dict]:
    return [
        {"agent_id": a.agent_id, "name": a.name,
         "description": a.description, "tags": a.tags, "version": a.version}
        for a in registry.list_all()
    ]
