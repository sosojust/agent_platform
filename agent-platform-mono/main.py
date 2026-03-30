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
from typing import AsyncIterator, Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

import apps
from shared.config.settings import settings
from shared.config.nacos import init_nacos_config
from shared.logging.logger import configure_logging, get_logger
from shared.middleware.tenant import (
    TenantContextMiddleware,
    get_current_tenant_id,
    set_current_conversation_id,
    set_current_thread_id,
)
from shared.models.schemas import AgentRunRequest, AgentRunResponse
from shared.fastapi_utils import ReadinessRegistry, make_health_router, register_error_handlers
from core.agent_engine.agents.registry import agent_gateway
from core.agent_engine.checkpoints.redis_checkpoint import get_checkpointer
from core.agent_engine.orchestrator_factory import build_orchestrator
from core.agent_engine.workflows.state import make_initial_state
from core.tool_service.client.gateway import internal_gateway
from core.tool_service.registry import tool_gateway

configure_logging()
logger = get_logger(__name__)

# ── Readiness Registry ────────────────────────────────────────
# 单体：汇总所有模块的就绪条件
readiness = ReadinessRegistry()


# ── 动态检查函数（每次 /ready 调用时执行）───────────────────

async def _check_redis() -> bool:
    try:
        from core.memory_rag.memory.manager import memory_gateway
        r = await memory_gateway._r()
        await r.ping()
        return True
    except Exception:
        return False


async def _check_milvus() -> bool:
    try:
        from core.memory_rag.vector.store import vector_gateway
        vector_gateway._client.list_collections()
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

async def _check_prompts() -> bool:
    try:
        from core.ai_core.prompt.manager import prompt_gateway
        _ = prompt_gateway.get("policy_agent_system", {"tenant_id": "ready_check"})
        return True
    except Exception:
        return False

async def _check_rag() -> bool:
    try:
        from core.memory_rag.embedding.gateway import embedding_gateway
        from core.memory_rag.vector.store import vector_gateway
        embedding_gateway.embed(["ready"])
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
        provider = LangfusePromptProvider(host, public_key, secret_key)
        p = provider.get_prompt("policy_agent_system")
        return p is not None and len(str(p)) > 0
    except Exception:
        return False

async def _check_rag_backend_qdrant() -> bool:
    try:
        backend = getattr(settings.vector_db, "backend", "")
        return str(backend).lower() == "qdrant"
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
        from core.memory_rag.embedding.gateway import embedding_gateway
        from core.memory_rag.rerank.service import rerank_gateway
        embedding_gateway.embed(["warmup"])
        rerank_gateway.rerank("warmup", ["test"], top_k=1)
        readiness.mark_ready("models")        # 模型加载完成
        logger.info("models_ready")
    except Exception as e:
        logger.error("model_warmup_failed", error=str(e))
        # 模型加载失败时不 mark_ready，/ready 持续返回 503

    # 3. 注册基础设施动态检查（每次 /ready 都会 ping）
    readiness.register_check("redis", _check_redis)
    readiness.register_check("milvus", _check_milvus)
    readiness.register_check("qdrant", _check_qdrant)
    readiness.register_check("prompts_ready", _check_prompts)
    readiness.register_check("prompts_source_langfuse", _check_prompts_source_langfuse)
    readiness.register_check("rag_ready", _check_rag)
    readiness.register_check("rag_backend_qdrant", _check_rag_backend_qdrant)
    readiness.register_check("rerank_available", _check_rerank_available)

    # 4. 注册所有业务域的 Agent
    from apps.policy.register import register as register_policy
    from apps.claim.register import register as register_claim
    from apps.customer.register import register as register_customer

    register_policy()
    register_claim()
    register_customer()
    domain_count = 3

    # 5. 聚合 Tool Service：内部 MCP + 外部 MCP
    try:
        from core.tool_service.mcp.service_client import MCPServiceProvider
        from core.tool_service.mcp.external_client import ExternalMCPProvider
        await tool_gateway.register_mcp_provider("mcp", MCPServiceProvider())
        for idx, endpoint in enumerate(settings.external_mcp_endpoints or []):
            await tool_gateway.register_mcp_provider(f"ext{idx+1}", ExternalMCPProvider(endpoint, token=(settings.external_mcp_token or None)))
        logger.info("tools_registered", count=len(tool_gateway.list_tools()))
    except Exception as e:
        logger.error("tool_service_init_failed", error=str(e))

    # 所有域注册完成才标记 ready
    if domain_count > 0:
        readiness.mark_ready("apps")
        logger.info("all_domains_ready", total=domain_count)
    else:
        logger.error("no_domains_registered")

    logger.info("agent_platform_started")
    yield

    # ── 关闭阶段 ──
    await internal_gateway.close()
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

def _require_app_auth(headers: Dict[str, str]) -> str:
    app_id = headers.get("X-App-Id", "")
    app_token = headers.get("X-App-Token", "")
    if not app_id or not app_token:
        raise HTTPException(status_code=401, detail="missing app auth headers")
    expected = settings.tool_auth_map.get(app_id)
    if not expected or expected != app_token:
        raise HTTPException(status_code=401, detail="invalid app auth")
    return app_id


class ToolInvokeRequest(BaseModel):
    tool: str = Field(...)
    arguments: Dict[str, Any] = Field(default_factory=dict)


@app.get("/tools", summary="列出可用工具")
async def list_tools(request: Request) -> list[dict]:
    _require_app_auth(dict(request.headers))
    return tool_gateway.list_tools()


@app.post("/tools/invoke", summary="调用工具")
async def invoke_tool(req: ToolInvokeRequest, request: Request) -> dict:
    _require_app_auth(dict(request.headers))
    try:
        result = await tool_gateway.invoke(req.tool, req.arguments)
        if isinstance(result, dict):
            return result
        return {"result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/run", response_model=AgentRunResponse, summary="同步运行 Agent")
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    """同步调用，等待完整响应。适合响应时间 < 10s 的简单查询。"""
    tenant_id = get_current_tenant_id()
    conversation_id = request.conversation_id or str(uuid.uuid4())
    set_current_conversation_id(conversation_id)
    set_current_thread_id(conversation_id)

    agent_meta = agent_gateway.get(request.agent_id)
    if not agent_meta:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{request.agent_id}' not found. "
                   f"Available: {[a.agent_id for a in agent_gateway.list_all()]}",
        )

    initial_state = make_initial_state(
        messages=[HumanMessage(content=request.input)],
        conversation_id=conversation_id,
        tenant_id=tenant_id,
    )
    agent, mode = build_orchestrator(
        meta=agent_meta,
        tenant_id=tenant_id,
        user_input=request.input,
        state=initial_state,
    )
    checkpointer = await get_checkpointer()
    config = {"configurable": {"thread_id": conversation_id, "checkpointer": checkpointer}}

    try:
        result = await agent.ainvoke(initial_state, config=config)
        output = str(result["messages"][-1].content)
        logger.info("agent_run_complete", agent_id=request.agent_id,
                    conversation_id=conversation_id, steps=result.get("step_count", 0), mode=mode)
        return AgentRunResponse(conversation_id=conversation_id, output=output,
                                steps=[{"step_count": result.get("step_count", 0), "mode": mode}])
    except Exception as e:
        logger.error("agent_run_failed", agent_id=request.agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/stream", summary="流式运行 Agent（SSE）")
async def stream_agent(request: AgentRunRequest) -> StreamingResponse:
    """SSE 流式输出，事件类型：token | step_start | step_end | done | error"""
    tenant_id = get_current_tenant_id()
    conversation_id = request.conversation_id or str(uuid.uuid4())
    set_current_conversation_id(conversation_id)
    set_current_thread_id(conversation_id)

    agent_meta = agent_gateway.get(request.agent_id)
    if not agent_meta:
        raise HTTPException(status_code=404,
                            detail=f"Agent '{request.agent_id}' not found")

    initial_state = make_initial_state(
        messages=[HumanMessage(content=request.input)],
        conversation_id=conversation_id,
        tenant_id=tenant_id,
    )
    agent, mode = build_orchestrator(
        meta=agent_meta,
        tenant_id=tenant_id,
        user_input=request.input,
        state=initial_state,
    )
    checkpointer = await get_checkpointer()
    config = {"configurable": {"thread_id": conversation_id, "checkpointer": checkpointer}}

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
            yield f"data: {json.dumps({'event': 'done', 'data': {'mode': mode}})}\n\n"
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
        for a in agent_gateway.list_all()
    ]
