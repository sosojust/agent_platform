"""
Agent Service — FastAPI 入口（port 8001）。

启动流程：
  1. 从 mcp-service 拉取所有 tool schema
  2. 自动扫描 domains/ 目录，传入 tool_schemas 完成注册
  3. 挂载路由

对外接口：
  POST /agent/run      同步调用，等待完整响应
  POST /agent/stream   SSE 流式输出（推荐，低延迟）
  GET  /agent/list     列出所有已注册 Agent
  GET  /health
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
from config.settings import settings
from agents.registry import registry
from checkpoints.redis_checkpoint import get_checkpointer
from clients.ai_core_client import ai_core_client
from clients.memory_rag_client import memory_rag_client
from clients.mcp_client import mcp_client
from agent_platform_shared.config.nacos import init_nacos_config
from agent_platform_shared.logging.logger import configure_logging, get_logger
from agent_platform_shared.middleware.tenant import TenantContextMiddleware, get_current_tenant_id
from agent_platform_shared.models.schemas import AgentRunRequest, AgentRunResponse

configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("agent_service_starting", port=settings.port)
    init_nacos_config(settings)

    # 1. 从 mcp-service 拉取所有 tool schema
    tool_schemas = await mcp_client.list_tools()
    logger.info("mcp_tools_fetched", count=len(tool_schemas))

    # 2. 自动扫描并注册所有业务域，传入 tool_schemas
    for mod_info in pkgutil.iter_modules(domains.__path__):
        if mod_info.ispkg:
            try:
                mod = importlib.import_module(f"domains.{mod_info.name}.register")
                mod.register(tool_schemas)
                logger.info("domain_registered", domain=mod_info.name)
            except Exception as e:
                logger.error("domain_register_failed", domain=mod_info.name, error=str(e))

    logger.info("all_agents_ready", total=len(registry.list_all()))
    yield

    # 关闭时释放资源
    await ai_core_client.close()
    await memory_rag_client.close()
    await mcp_client.close()
    logger.info("agent_service_stopped")


app = FastAPI(title="Agent Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(TenantContextMiddleware)


def _initial_state(request: AgentRunRequest, session_id: str, tenant_id: str,
                   meta) -> dict:
    return {
        "messages": [HumanMessage(content=request.input)],
        "session_id": session_id,
        "tenant_id": tenant_id,
        "memory_context": "",
        "rag_context": "",
        "step_count": 0,
        "system_prompt_key": "",
        "rag_top_k_recall": meta.rag_top_k_recall,
        "rag_top_k_rerank": meta.rag_top_k_rerank,
    }


@app.post("/agent/run", response_model=AgentRunResponse, summary="同步运行 Agent")
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    """等待 Agent 完整执行后返回，适合响应时间 < 10s 的简单查询。"""
    tenant_id = get_current_tenant_id()
    session_id = request.session_id or str(uuid.uuid4())

    meta = registry.get(request.agent_id)
    if not meta:
        raise HTTPException(status_code=404,
                            detail=f"Agent '{request.agent_id}' not found. "
                                   f"Available: {[a.agent_id for a in registry.list_all()]}")

    agent = meta.factory()
    checkpointer = await get_checkpointer()
    config = {"configurable": {"thread_id": session_id, "checkpointer": checkpointer}}

    try:
        result = await agent.ainvoke(_initial_state(request, session_id, tenant_id, meta),
                                     config=config)
        output = str(result["messages"][-1].content)
        logger.info("agent_run_complete", agent_id=request.agent_id,
                    session_id=session_id, steps=result["step_count"])
        return AgentRunResponse(
            session_id=session_id, output=output,
            steps=[{"step_count": result["step_count"]}],
        )
    except Exception as e:
        logger.error("agent_run_failed", agent_id=request.agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/stream", summary="流式运行 Agent（SSE）")
async def stream_agent(request: AgentRunRequest) -> StreamingResponse:
    """
    SSE 流式输出，首 token 延迟最低。
    事件格式（每行 data: {...}）：
      {"event": "token",      "data": "字"}          逐 token 输出
      {"event": "step_start", "data": "tool_name"}   tool 开始执行
      {"event": "step_end",   "data": "tool_name"}   tool 执行结束
      {"event": "done",       "data": null}           Agent 执行完毕
      {"event": "error",      "data": "error msg"}    发生错误
    """
    tenant_id = get_current_tenant_id()
    session_id = request.session_id or str(uuid.uuid4())

    meta = registry.get(request.agent_id)
    if not meta:
        raise HTTPException(status_code=404,
                            detail=f"Agent '{request.agent_id}' not found")

    agent = meta.factory()
    checkpointer = await get_checkpointer()
    config = {"configurable": {"thread_id": session_id, "checkpointer": checkpointer}}
    initial_state = _initial_state(request, session_id, tenant_id, meta)

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
            logger.error("agent_stream_error", agent_id=request.agent_id, error=str(e))
            yield f"data: {json.dumps({'event': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # 关闭 Nginx 缓冲，确保 token 实时推送
        },
    )


@app.get("/agent/list", summary="列出所有已注册 Agent")
async def list_agents() -> list[dict]:
    return [
        {"agent_id": a.agent_id, "name": a.name,
         "description": a.description, "tags": a.tags,
         "version": a.version, "tools": a.tool_names}
        for a in registry.list_all()
    ]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "agent-service",
            "agents": len(registry.list_all()), "env": settings.app_env}
