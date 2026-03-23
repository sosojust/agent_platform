"""短期记忆(Redis) + 长期记忆(mem0) 双层管理。"""
import json
from typing import Optional
import redis.asyncio as aioredis
from mem0 import Memory
from config.settings import settings
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)
MAX_SHORT_TERM_TURNS = 20


class MemoryManager:
    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None
        self._mem0 = Memory.from_config({
            "vector_store": {
                "provider": "qdrant",
                "config": {"url": settings.qdrant_url, "collection_name": "mem0_long_term"},
            },
            "llm": {"provider": "litellm", "config": {"model": "gpt-4o-mini"}},
        })

    async def _r(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def get_short_term(self, session_id: str) -> list[dict]:
        r = await self._r()
        raw = await r.get(f"mem:short:{session_id}")
        return json.loads(raw) if raw else []

    async def append_short_term(
        self, session_id: str, role: str, content: str, tenant_id: str
    ) -> None:
        r = await self._r()
        history = await self.get_short_term(session_id)
        history.append({"role": role, "content": content})
        if len(history) > MAX_SHORT_TERM_TURNS:
            await self._flush_long_term(session_id, history, tenant_id)
            history = history[-5:]
        await r.setex(f"mem:short:{session_id}", settings.checkpoint_ttl, json.dumps(history))

    async def _flush_long_term(
        self, session_id: str, history: list[dict], tenant_id: str
    ) -> None:
        try:
            self._mem0.add(
                messages=history,
                user_id=f"{tenant_id}:{session_id}",
                metadata={"tenant_id": tenant_id, "session_id": session_id},
            )
        except Exception as e:
            logger.error("long_term_flush_failed", error=str(e))

    def search_long_term(self, query: str, tenant_id: str, top_k: int = 5) -> list[str]:
        try:
            results = self._mem0.search(query=query, user_id=tenant_id, limit=top_k)
            return [r["memory"] for r in results]
        except Exception as e:
            logger.error("long_term_search_failed", error=str(e))
            return []

    async def build_memory_context(
        self, session_id: str, query: str, tenant_id: str
    ) -> str:
        short = await self.get_short_term(session_id)
        long = self.search_long_term(query, tenant_id)
        parts = []
        if long:
            parts.append("【历史记忆】\n" + "\n".join(f"- {m}" for m in long))
        if short:
            parts.append("【本次对话】\n" + "\n".join(
                f"{m['role']}: {m['content']}" for m in short[-6:]
            ))
        return "\n\n".join(parts)


memory_manager = MemoryManager()
