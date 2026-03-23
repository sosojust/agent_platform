"""
MCP Service — FastAPI 入口（port 8004）。

对外接口：
  POST /tools/call     agent-service 调用此接口执行指定 tool
  GET  /tools/list     返回所有已注册 tool 的 schema（供 agent-service 绑定 LLM）
  GET  /health
"""
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config.settings import settings
from agent_platform_shared.config.nacos import init_nacos_config
from agent_platform_shared.logging.logger import configure_logging, get_logger
from agent_platform_shared.middleware.tenant import TenantContextMiddleware
from client.gateway import gateway_client
from tools.policy_tools import policy_tools
from tools.claim_tools import claim_tools
from tools.customer_tools import customer_tools

configure_logging(settings.log_level)
logger = get_logger(__name__)

ALL_TOOLS = {t.name: t for t in policy_tools + claim_tools + customer_tools}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("mcp_service_starting", port=settings.port, tools=list(ALL_TOOLS.keys()))
    init_nacos_config(settings)
    yield
    await gateway_client.close()
    logger.info("mcp_service_stopped")


app = FastAPI(title="MCP Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(TenantContextMiddleware)


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any]


@app.post("/tools/call")
async def call_tool(request: ToolCallRequest) -> dict:
    """执行指定 MCP tool，agent-service 通过此接口调用业务工具。"""
    tool = ALL_TOOLS.get(request.tool_name)
    if not tool:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{request.tool_name}' not found. "
                   f"Available: {list(ALL_TOOLS.keys())}",
        )
    try:
        result = await tool.fn(**request.arguments)
        logger.info("tool_called", tool=request.tool_name)
        return {"result": result}
    except Exception as e:
        logger.error("tool_call_failed", tool=request.tool_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools/list")
async def list_tools() -> list[dict]:
    """返回所有 tool 的 schema，agent-service 启动时拉取用于绑定 LLM。"""
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in ALL_TOOLS.values()
    ]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "mcp-service",
            "tool_count": len(ALL_TOOLS), "env": settings.app_env}
