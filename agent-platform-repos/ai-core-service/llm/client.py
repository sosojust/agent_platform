"""
LiteLLM 统一 LLM 客户端。
支持普通调用（complete）和流式调用（stream），
stream 方法供 /llm/stream 接口消费，逐 token 异步生成。
"""
from typing import AsyncIterator, Any
import litellm
from litellm import acompletion
from langfuse import Langfuse
from config.settings import settings
from agent_platform_shared.logging.logger import get_logger
from agent_platform_shared.middleware.tenant import get_current_tenant_id, get_current_trace_id

logger = get_logger(__name__)

langfuse = Langfuse(
    host=settings.observability.langfuse_host,
    public_key=settings.observability.langfuse_public_key,
    secret_key=settings.observability.langfuse_secret_key,
)

# 模型路由：按任务类型选择模型
TASK_MODEL_MAP = {
    "simple": "default_model",
    "complex": "strong_model",
    "local": "local",
}


def _select_model(task_type: str) -> str:
    attr = TASK_MODEL_MAP.get(task_type, "default_model")
    if attr == "local":
        return f"openai/{settings.local_model_base_url}"
    return getattr(settings, attr)


async def complete(
    messages: list[dict],
    task_type: str = "simple",
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> tuple[str, dict]:
    """普通调用，返回 (output, usage)。"""
    model = _select_model(task_type)
    trace = langfuse.trace(
        name="llm_complete",
        metadata={"tenant_id": get_current_tenant_id(), "model": model},
        trace_id=get_current_trace_id(),
    )
    gen = trace.generation(name="completion", model=model, input=messages)
    try:
        resp = await acompletion(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
        )
        output = resp.choices[0].message.content or ""
        usage = {"input": resp.usage.prompt_tokens, "output": resp.usage.completion_tokens}
        gen.end(output=output, usage=usage)
        logger.info("llm_complete", model=model, tokens=resp.usage.total_tokens)
        return output, usage
    except Exception as e:
        gen.end(level="ERROR", status_message=str(e))
        logger.error("llm_complete_failed", model=model, error=str(e))
        raise


async def stream(
    messages: list[dict],
    task_type: str = "complex",
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    """流式调用，逐 token yield。供 /llm/stream 接口消费。"""
    model = _select_model(task_type)
    try:
        resp = await acompletion(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as e:
        logger.error("llm_stream_failed", model=model, error=str(e))
        raise
