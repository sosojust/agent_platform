"""
Agent Platform — FastAPI 主入口。

启动流程：
  1. 配置日志
  2. 初始化 Nacos 动态配置
  3. 自动扫描 domains/ 目录，调用每个域的 register.py 完成注册
  4. 挂载所有路由
  5. 服务就绪

关闭流程：
  1. 释放 HTTP 客户端连接池
  2. 关闭 Redis 连接
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

import domains
from shared.config.settings import settings
from shared.config.nacos import init_nacos_config
from shared.logging.logger import configure_logging, get_logger
from shared.middleware.tenant import TenantContextMiddleware, get_current_tenant_id
from shared.models.schemas import AgentRunRequest, AgentRunResponse
from agent_service.agents.registry import registry
from agent_service.checkpoints.redis_checkpoint import get_checkpointer
from mcp_server.client.gateway import gateway_client

configure_logging()
logger = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("agent_platform_starting", env=settings.app_env, version="0.2.0")

    # 1. 接入 Nacos 动态配置（非阻塞，失败降级到 .env）
    init_nacos_config(settings)

    # 2. 自动发现并注册所有业务域
    #    只要在 domains/ 下新建目录 + register.py，无需修改此处
    for module_info in pkgutil.iter_modules(domains.__path__):
        if module_info.ispkg:
            try:
                mod = importlib.import_module(f"domains.{module_info.name}.register")
                mod.register()
                logger.info("domain_registered", domain=module_info.name)
            except Exception as e:
                # 单个域注册失败不影响其他域启动
                logger.error("domain_register_failed", domain=module_info.name, error=str(e))

    logger.info("all_domains_registered", total=len(registry.list_all()))
    yield

    # 释放资源
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


# ── Routes ────────────────────────────────────────────────────

@app.post("/agent/run", response_model=AgentRunResponse, summary="同步运行 Agent")
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    """
    同步调用，等待 Agent 完整执行后返回。
    适合简单查询场景，响应时间 < 10s。
    超过此时间建议改用 /agent/stream。
    """
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
        "session_id": session_id,
        "tenant_id": tenant_id,
        "memory_context": "",
        "rag_context": "",
        "step_count": 0,
    }

    try:
        result = await agent.ainvoke(initial_state, config=config)
        output = str(result["messages"][-1].content)
        logger.info("agent_run_complete", agent_id=request.agent_id,
                    session_id=session_id, steps=result["step_count"])
        return AgentRunResponse(
            session_id=session_id,
            output=output,
            steps=[{"step_count": result["step_count"]}],
        )
    except Exception as e:
        logger.error("agent_run_failed", agent_id=request.agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/stream", summary="流式运行 Agent（SSE）")
async def stream_agent(request: AgentRunRequest) -> StreamingResponse:
    """
    SSE 流式输出，逐 token 返回。
    事件类型：token | step_start | step_end | done | error
    """
    tenant_id = get_current_tenant_id()
    session_id = request.session_id or str(uuid.uuid4())

    agent_meta = registry.get(request.agent_id)
    if not agent_meta:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent_id}' not found")

    agent = agent_meta.factory()
    checkpointer = await get_checkpointer()
    config = {"configurable": {"thread_id": session_id, "checkpointer": checkpointer}}
    initial_state = {
        "messages": [HumanMessage(content=request.input)],
        "session_id": session_id,
        "tenant_id": tenant_id,
        "memory_context": "",
        "rag_context": "",
        "step_count": 0,
    }

    async def event_generator():
        try:
            async for event in agent.astream_events(initial_state, config=config, version="v2"):
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

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/agent/list", summary="列出所有已注册的 Agent")
async def list_agents() -> list[dict]:
    return [
        {"agent_id": a.agent_id, "name": a.name,
         "description": a.description, "tags": a.tags, "version": a.version}
        for a in registry.list_all()
    ]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env, "agents": len(registry.list_all())}
