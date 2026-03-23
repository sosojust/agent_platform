"""Prompt 版本管理，Langfuse 存储，本地 fallback。"""
from typing import Optional
from langfuse import Langfuse
from config.settings import settings
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)

langfuse = Langfuse(
    host=settings.observability.langfuse_host,
    public_key=settings.observability.langfuse_public_key,
    secret_key=settings.observability.langfuse_secret_key,
)

_FALLBACK: dict[str, str] = {
    "agent_system": (
        "你是一个团险业务助手，当前租户：{tenant_id}。"
        "请专业、准确地回答用户问题，不确定时主动告知。"
    ),
    "rag_query_rewrite": (
        "将以下问题改写为更适合向量检索的查询语句：\n{question}\n改写后："
    ),
    "policy_agent_system": (
        "你是团险保单查询助手，当前租户：{tenant_id}。"
        "专注保单查询，需要明确保单号才能查询。"
    ),
    "claim_agent_system": (
        "你是团险理赔助手，当前租户：{tenant_id}。"
        "协助用户处理理赔查询和材料核验。"
    ),
    "customer_agent_system": (
        "你是团险客服助手，当前租户：{tenant_id}。"
        "优先使用 FAQ，超出范围时转接人工。"
    ),
}


def get_prompt(name: str, variables: Optional[dict] = None) -> str:
    template = _fetch_langfuse(name) or _FALLBACK.get(name, "")
    if not template:
        logger.warning("prompt_not_found", name=name)
        return ""
    return template.format(**variables) if variables else template


def _fetch_langfuse(name: str) -> Optional[str]:
    try:
        return langfuse.get_prompt(name).compile()
    except Exception as e:
        logger.warning("langfuse_fetch_failed", name=name, error=str(e))
        return None
