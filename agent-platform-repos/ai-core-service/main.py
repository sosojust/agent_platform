"""
AI Core Service — FastAPI 入口（port 8002）。

对外接口：
  POST /llm/complete   普通 JSON 响应，供 RAG 查询改写等简单任务使用
  POST /llm/stream     HTTP streaming（NDJSON），供 Agent 推理使用
  GET  /prompt/{name}  获取渲染后的 Prompt 模板
  GET  /health
"""
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from config.settings import settings
from agent_platform_shared.config.nacos import init_nacos_config
from agent_platform_shared.logging.logger import configure_logging, get_logger
from agent_platform_shared.middleware.tenant import TenantContextMiddleware
from agent_platform_shared.models.schemas import LLMRequest, LLMResponse
from llm.client import complete, stream
from prompt.manager import get_prompt

configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("ai_core_service_starting", port=settings.port)
    init_nacos_config(settings)
    yield
    logger.info("ai_core_service_stopped")


app = FastAPI(title="AI Core Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(TenantContextMiddleware)


@app.post("/llm/complete", response_model=LLMResponse)
async def llm_complete(request: LLMRequest) -> LLMResponse:
    """
    同步 LLM 调用，等待完整响应后返回。
    适用于：RAG 查询改写、Prompt 渲染、简单分类任务。
    不适用于：Agent 主推理（用 /llm/stream 代替）。
    """
    try:
        output, usage = await complete(
            messages=request.messages,
            task_type=request.task_type,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return LLMResponse(output=output, usage=usage)
    except Exception as e:
        logger.error("llm_complete_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/llm/stream")
async def llm_stream(request: LLMRequest) -> StreamingResponse:
    """
    流式 LLM 调用，NDJSON 格式逐 token 返回。
    每行格式：{"token": "..."} 或 {"done": true} 或 {"error": "..."}

    agent-service 通过 httpx.AsyncClient.stream() 消费此接口，
    再转为 SSE 推给最终客户端。
    """
    async def generate():
        try:
            async for token in stream(
                messages=request.messages,
                task_type=request.task_type,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ):
                yield json.dumps({"token": token}) + "\n"
            yield json.dumps({"done": True}) + "\n"
        except Exception as e:
            logger.error("llm_stream_error", error=str(e))
            yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.get("/prompt/{name}")
async def get_prompt_api(
    name: str,
    tenant_id: str = Query(default=""),
    **kwargs: str,
) -> dict:
    """获取渲染后的 Prompt 模板。"""
    variables = {"tenant_id": tenant_id, **kwargs}
    return {"name": name, "content": get_prompt(name, variables)}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ai-core-service", "env": settings.app_env}
