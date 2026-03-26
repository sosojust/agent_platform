from __future__ import annotations
import json
import time
from typing import Any, Dict, List
from redis.asyncio import Redis
from shared.config.settings import settings
from core.memory_rag.memory.config import MemoryConfig


class MemoryManager:
    def __init__(self):
        self._client: Redis | None = None

    async def _r(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(settings.redis.url, decode_responses=True)
        return self._client

    async def append_short_term(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tenant_id: str,
        config: MemoryConfig,
    ) -> None:
        r = await self._r()
        key = f"mem:{tenant_id}:{conversation_id}"
        entry = {"role": role, "content": content, "ts": int(time.time())}
        await r.rpush(key, json.dumps(entry, ensure_ascii=False))
        await r.expire(key, settings.redis.checkpoint_ttl)
        length = await r.llen(key)
        exceed = max(0, length - config.short_term_max_turns)
        if exceed > 0:
            await r.ltrim(key, exceed, -1)

    async def build_memory_context(
        self,
        conversation_id: str,
        query: str,
        tenant_id: str,
        config: MemoryConfig,
    ) -> str:
        r = await self._r()
        key = f"mem:{tenant_id}:{conversation_id}"
        items: List[str] = await r.lrange(key, -config.short_term_max_turns, -1)
        parts: List[str] = []
        for it in items:
            obj = json.loads(it)
            parts.append(f"{obj.get('role')}: {obj.get('content')}")
        return "\n".join(parts[-config.short_term_max_turns:])


memory_manager = MemoryManager()
