"""LangGraph Checkpoint 后端选择（Memory/Redis）。"""
from typing import Any
from langgraph.checkpoint.memory import MemorySaver
try:
    from langgraph.checkpoint.redis import RedisSaver  # 可选依赖
except Exception:
    RedisSaver = None
from shared.config.settings import settings

async def get_checkpointer() -> Any:
    backend = str(getattr(settings, "checkpoint_backend", "memory")).lower()
    if backend == "redis" and RedisSaver is not None:
        try:
            ttl = int(getattr(settings.redis, "checkpoint_ttl", 86400))
            cp = RedisSaver.from_url(settings.redis.url, ttl=ttl)
            return cp
        except Exception:
            return MemorySaver()
    return MemorySaver()
