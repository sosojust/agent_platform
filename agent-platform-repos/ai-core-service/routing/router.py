"""
模型路由策略。

按 task_type 选择模型，平衡效果和成本：
  simple  → 小模型（gpt-4o-mini），速度快、成本低
            适用：RAG 查询改写、简单分类、Prompt 渲染
  complex → 强模型（gpt-4o），推理能力强
            适用：Agent 主推理、多步决策、复杂问题
  local   → 本地模型（vLLM/Ollama 部署），数据不出内网
            适用：含客户敏感信息的推理任务

路由规则可通过 Nacos 动态下发，无需重启服务更新：
  Nacos key: llm_default_model / llm_strong_model
"""
from config.settings import settings
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)

# task_type → settings 字段名
_ROUTING_MAP: dict[str, str] = {
    "simple": "default_model",
    "complex": "strong_model",
    "local": "_local",
}


def select_model(task_type: str = "simple") -> str:
    """
    根据任务类型返回 LiteLLM 模型字符串。
    未知 task_type 默认走 simple。
    """
    attr = _ROUTING_MAP.get(task_type, "default_model")

    if attr == "_local":
        if not settings.local_model_base_url:
            logger.warning("local_model_not_configured", fallback="default_model")
            return settings.default_model
        # LiteLLM openai-compatible 格式：openai/<base_url>
        return f"openai/{settings.local_model_base_url}"

    model = getattr(settings, attr, settings.default_model)
    logger.debug("model_selected", task_type=task_type, model=model)
    return model


def get_routing_table() -> dict[str, str]:
    """返回当前路由表，用于健康检查和调试。"""
    return {
        "simple": settings.default_model,
        "complex": settings.strong_model,
        "local": settings.local_model_base_url or "(not configured)",
    }
