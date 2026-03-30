from __future__ import annotations
import json
import time
from typing import Any, Dict, List
from redis.asyncio import Redis
from shared.config.settings import settings
from shared.logging.logger import get_logger
from core.memory_rag.memory.config import MemoryConfig
from core.memory_rag.embedding.gateway import embedding_gateway
from core.memory_rag.vector.store import vector_store

logger = get_logger(__name__)

_NOISE_TEXTS = {
    "嗯",
    "哦",
    "好的",
    "收到",
    "了解",
    "谢谢",
    "好的谢谢",
}


class MemoryManager:
    def __init__(self) -> None:
        self._client: Any | None = None

    async def _r(self) -> Any:
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
        normalized = self._normalize_content(content)
        if not normalized:
            logger.info(
                "memory_append_skipped",
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                reason="empty_content",
            )
            return
        if config.memory_noise_filter_enabled and self._is_noise(normalized):
            logger.info(
                "memory_append_skipped",
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                reason="noise_content",
            )
            return
        r: Any = await self._r()
        key = f"mem:{tenant_id}:{conversation_id}"
        if await self._is_duplicate_recent(
            redis_client=r,
            key=key,
            role=role,
            content=normalized,
        ):
            logger.info(
                "memory_append_skipped",
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                reason="duplicate_content",
            )
            return
        entry = {"role": role, "content": normalized, "ts": int(time.time())}
        await r.rpush(key, json.dumps(entry, ensure_ascii=False))
        await r.expire(key, settings.redis.checkpoint_ttl)
        length = await r.llen(key)
        exceed = max(0, length - config.short_term_max_turns)
        if exceed > 0:
            await r.ltrim(key, exceed, -1)
            length = await r.llen(key)
        if config.long_term_enabled:
            await self._trigger_consolidate_if_needed(
                redis_client=r,
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                config=config,
                current_short_term_len=int(length),
            )

    async def build_memory_context(
        self,
        conversation_id: str,
        query: str,
        tenant_id: str,
        config: MemoryConfig,
    ) -> str:
        r: Any = await self._r()
        key = f"mem:{tenant_id}:{conversation_id}"
        items: List[str] = await r.lrange(key, -config.short_term_max_turns, -1)
        parts: List[str] = []
        for it in items:
            obj = json.loads(it)
            parts.append(f"{obj.get('role')}: {obj.get('content')}")
        if config.long_term_enabled:
            memory_types = config.memory_types_default
            long_term_parts = await self.retrieve_long_term(
                query=query,
                tenant_id=tenant_id,
                config=config,
                memory_types=memory_types,
            )
            parts.extend([f"memory: {p}" for p in long_term_parts])
        return "\n".join(parts[-config.short_term_max_turns - config.long_term_retrieve_top_k :])

    async def retrieve_long_term(
        self,
        query: str,
        tenant_id: str,
        config: MemoryConfig,
        memory_types: List[str] | None = None,
        top_k: int | None = None,
    ) -> List[str]:
        if not query.strip():
            return []
        use_top_k = top_k or config.long_term_retrieve_top_k
        if use_top_k <= 0:
            return []
        query_vector = embedding_gateway.embed([query])[0]
        collection = self._memory_collection_name(tenant_id)
        filters = self._build_long_term_filter(tenant_id=tenant_id, memory_types=memory_types)
        try:
            hits = vector_store.search(
                collection=collection,
                query_vector=query_vector,
                top_k=use_top_k,
                filter_ast=filters,
            )
        except Exception:
            return []
        out: List[str] = []
        for hit in hits:
            metadata = dict(hit.get("metadata") or {})
            text = str(metadata.get("text", "")).strip()
            if text:
                out.append(text)
        return out

    async def consolidate_short_to_long(
        self,
        conversation_id: str,
        tenant_id: str,
        config: MemoryConfig,
    ) -> int:
        if not config.long_term_enabled:
            return 0
        r: Any = await self._r()
        key = f"mem:{tenant_id}:{conversation_id}"
        items: List[str] = await r.lrange(key, -config.short_to_long_trigger_turns, -1)
        entries: List[Dict[str, Any]] = []
        for raw in items:
            obj = json.loads(raw)
            role = str(obj.get("role", ""))
            content = self._normalize_content(str(obj.get("content", "")))
            if not content:
                continue
            if config.memory_noise_filter_enabled and self._is_noise(content):
                continue
            ts = int(obj.get("ts", int(time.time())))
            memory_type = self._resolve_memory_type(config)
            entries.append(
                {
                    "role": role,
                    "content": content,
                    "timestamp": ts,
                    "memory_type": memory_type,
                }
            )
        if not entries:
            return 0
        return self.append_long_term(
            entries=entries,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            memory_type=self._resolve_memory_type(config),
        )

    def append_long_term(
        self,
        entries: List[Dict[str, Any]],
        conversation_id: str,
        tenant_id: str,
        memory_type: str,
    ) -> int:
        if not entries:
            return 0
        collection = self._memory_collection_name(tenant_id)
        self._ensure_collection_exists(collection)
        texts: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        ids: List[str] = []
        now = int(time.time())
        for i, entry in enumerate(entries):
            content = self._normalize_content(str(entry.get("content", "")))
            if not content:
                continue
            ts = int(entry.get("timestamp", now))
            role = str(entry.get("role", "assistant"))
            texts.append(content)
            metadatas.append(
                {
                    "tenant_id": tenant_id,
                    "conversation_id": conversation_id,
                    "memory_type": memory_type,
                    "role": role,
                    "timestamp": ts,
                }
            )
            ids.append(f"{tenant_id}:{conversation_id}:{memory_type}:{ts}:{i}")
        if not texts:
            return 0
        vector_store.add_texts(
            collection=collection,
            texts=texts,
            metadatas=metadatas,
            ids=ids,
        )
        return len(texts)

    async def _is_duplicate_recent(
        self,
        redis_client: Any,
        key: str,
        role: str,
        content: str,
    ) -> bool:
        recent_items: List[str] = await redis_client.lrange(key, -6, -1)
        for raw in reversed(recent_items):
            obj: Dict[str, Any] = json.loads(raw)
            old_role = str(obj.get("role", ""))
            old_content = self._normalize_content(str(obj.get("content", "")))
            if old_role == role and old_content == content:
                return True
        return False

    def _normalize_content(self, content: str) -> str:
        return " ".join(content.strip().split())

    def _is_noise(self, content: str) -> bool:
        compact = content.replace(" ", "")
        if len(compact) <= 1:
            return True
        return compact in _NOISE_TEXTS

    def _memory_collection_name(self, tenant_id: str) -> str:
        return f"{tenant_id}_memory"

    def _resolve_memory_type(self, config: MemoryConfig) -> str:
        if config.memory_types_default:
            return str(config.memory_types_default[0])
        return "conversation"

    def _build_long_term_filter(
        self,
        tenant_id: str,
        memory_types: List[str] | None,
    ) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = [{"EQ": ["tenant_id", tenant_id]}]
        if memory_types:
            items.append({"IN": ["memory_type", [str(m) for m in memory_types]]})
        return {"AND": items}

    def _ensure_collection_exists(self, collection: str) -> None:
        try:
            if collection in vector_store.list_collections():
                return
            vector_store.create_collection(collection, {"vector_size": 0})
        except Exception:
            return

    async def _trigger_consolidate_if_needed(
        self,
        redis_client: Any,
        conversation_id: str,
        tenant_id: str,
        config: MemoryConfig,
        current_short_term_len: int,
    ) -> None:
        trigger = max(1, int(config.short_to_long_trigger_turns))
        progress_key = f"memc:{tenant_id}:{conversation_id}:last_len"
        last_raw = await redis_client.get(progress_key)
        last_len = int(last_raw) if last_raw else 0
        if current_short_term_len < trigger:
            return
        if current_short_term_len - last_len < trigger:
            return
        written = await self.consolidate_short_to_long(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            config=config,
        )
        await redis_client.set(progress_key, str(current_short_term_len))
        logger.info(
            "memory_consolidated",
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            written=written,
            short_term_len=current_short_term_len,
        )


memory_manager = MemoryManager()
