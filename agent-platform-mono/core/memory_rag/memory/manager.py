from __future__ import annotations
import json
import time
from typing import Any, Dict, List
from redis.asyncio import Redis
from shared.config.settings import settings
from shared.logging.logger import get_logger
from core.memory_rag.memory.compressor import build_compressor, build_tokenizer
from core.memory_rag.memory.provider_protocols import CompressionRequest, MessageCompressor
from core.memory_rag.memory.config import MemoryConfig
from core.memory_rag.memory.filters import DuplicateRecentFilter, NoiseFilter, normalize_content
from core.memory_rag.embedding.gateway import embedding_gateway
from core.memory_rag.vector.store import vector_gateway

logger = get_logger(__name__)

class MemoryGateway:
    def __init__(self) -> None:
        self._client: Any | None = None
        self._default_noise_filter = NoiseFilter()
        self._default_duplicate_filter = DuplicateRecentFilter(window_size=6)

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
        normalized = normalize_content(content)
        if not normalized:
            logger.info(
                "memory_append_skipped",
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                reason="empty_content",
            )
            return
        noise_filter = self._noise_filter(config)
        if noise_filter is not None and noise_filter.is_noise(normalized):
            logger.info(
                "memory_append_skipped",
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                reason="noise_content",
            )
            return
        r: Any = await self._r()
        key = f"mem:{tenant_id}:{conversation_id}"
        duplicate_filter = self._duplicate_filter(config)
        recent_raw: List[str] = await r.lrange(key, -max(1, int(config.short_term_dedup_window)), -1)
        recent_items = [json.loads(raw) for raw in recent_raw]
        if duplicate_filter is not None and duplicate_filter.is_duplicate(
            role=role,
            content=normalized,
            recent_messages=recent_items,
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
        length = await self._apply_short_term_compression(
            redis_client=r,
            key=key,
            current_length=int(length),
            config=config,
        )
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
        
        short_term_parts: List[str] = []
        for it in items:
            obj = json.loads(it)
            short_term_parts.append(f"{obj.get('role')}: {obj.get('content')}")
            
        long_term_parts: List[str] = []
        if config.long_term_enabled:
            memory_types = config.memory_types_default
            long_term_parts = await self.retrieve_long_term(
                query=query,
                tenant_id=tenant_id,
                config=config,
                memory_types=memory_types,
            )

        # 优先保障短期记忆，然后追加长期记忆，直到达到 token limit
        tokenizer = build_tokenizer(config.tokenizer_provider)
        final_parts: List[str] = []
        current_tokens = 0
        
        # 短期记忆按时间顺序，从后往前计算，如果超限则截断更早的
        valid_short_term = []
        for part in reversed(short_term_parts):
            tokens = tokenizer.count_text(part, config.compression_model_name)
            if current_tokens + tokens > config.max_injection_tokens:
                break
            valid_short_term.insert(0, part)
            current_tokens += tokens
            
        # 长期记忆作为补充上下文
        valid_long_term = []
        for part in long_term_parts:
            fact_str = f"- Fact: {part}"
            tokens = tokenizer.count_text(fact_str, config.compression_model_name)
            if current_tokens + tokens > config.max_injection_tokens:
                break
            valid_long_term.append(fact_str)
            current_tokens += tokens

        if valid_long_term:
            final_parts.append("【相关历史事实】")
            final_parts.extend(valid_long_term)
            final_parts.append("")
            
        if valid_short_term:
            final_parts.append("【近期对话】")
            final_parts.extend(valid_short_term)

        return "\n".join(final_parts)

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
            hits = vector_gateway.search(
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
        
        messages = []
        for raw in items:
            obj = json.loads(raw)
            content = normalize_content(str(obj.get("content", "")))
            if not content:
                continue
            noise_filter = self._noise_filter(config)
            if noise_filter is not None and noise_filter.is_noise(content):
                continue
            messages.append({"role": obj.get("role", "user"), "content": content})
            
        if not messages:
            return 0
            
        from core.memory_rag.memory.extractor import LLMFactExtractor
        extractor = LLMFactExtractor()
        extracted_facts = await extractor.extract(messages, tenant_id, conversation_id)
        
        if not extracted_facts:
            return 0
            
        # Add memory_type to facts
        memory_type = self._resolve_memory_type(config)
        for fact in extracted_facts:
            fact["memory_type"] = memory_type
            
        return self.append_long_term(
            entries=extracted_facts,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            memory_type=memory_type,
        )

    def append_long_term(
        self,
        entries: List[Dict[str, Any]],
        conversation_id: str,
        tenant_id: str,
        memory_type: str,
    ) -> int:
        import hashlib
        if not entries:
            return 0
        collection = self._memory_collection_name(tenant_id)
        self._ensure_collection_exists(collection)
        texts: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        ids: List[str] = []
        now = int(time.time())
        for entry in entries:
            content = normalize_content(str(entry.get("content", "")))
            if not content:
                continue
            
            # 使用内容 Hash 去重，防止事实重复堆积
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            fact_id = f"{tenant_id}:{memory_type}:{content_hash}"
            
            ts = int(entry.get("timestamp", now))
            role = str(entry.get("role", "system"))
            texts.append(content)
            metadatas.append(
                {
                    "tenant_id": tenant_id,
                    "conversation_id": conversation_id,
                    "memory_type": memory_type,
                    "role": role,
                    "category": entry.get("category", "general"),
                    "confidence": entry.get("confidence", 1.0),
                    "timestamp": ts,
                }
            )
            ids.append(fact_id)
            
        if not texts:
            return 0
        vector_gateway.add_texts(
            collection=collection,
            texts=texts,
            metadatas=metadatas,
            ids=ids,
        )
        return len(texts)

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
            if collection in vector_gateway.list_collections():
                return
            vector_gateway.create_collection(collection, {"vector_size": 0})
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

    async def _apply_short_term_compression(
        self,
        redis_client: Any,
        key: str,
        current_length: int,
        config: MemoryConfig,
    ) -> int:
        compressor = self._compressor(config)
        threshold = self._compression_turn_threshold(config)
        token_threshold = max(0, int(config.compression_token_threshold))
        if current_length <= threshold and token_threshold <= 0:
            return current_length
        raw_items: List[str] = await redis_client.lrange(key, 0, -1)
        messages = [json.loads(raw) for raw in raw_items]
        if not messages:
            return 0
        tokenizer = build_tokenizer(config.tokenizer_provider)
        if token_threshold > 0:
            message_tokens = tokenizer.count_messages(messages, model_name=config.compression_model_name)
            if message_tokens <= token_threshold and len(messages) <= threshold:
                return len(messages)
        request = CompressionRequest(
            messages=messages,
            max_turns=threshold,
            keep_recent=max(1, int(config.compression_keep_recent)),
            token_threshold=token_threshold,
            model_name=config.compression_model_name,
        )
        result = await compressor.compress(request)
        if not result.applied:
            return len(messages)
        await redis_client.ltrim(key, 1, 0)
        now = int(time.time())
        for message in result.messages:
            role = str(message.get("role", "system"))
            content = normalize_content(str(message.get("content", "")))
            if not content:
                continue
            ts = int(message.get("ts", now))
            await redis_client.rpush(
                key,
                json.dumps({"role": role, "content": content, "ts": ts}, ensure_ascii=False),
            )
        await redis_client.expire(key, settings.redis.checkpoint_ttl)
        final_len = await redis_client.llen(key)
        return int(final_len)

    def _compression_turn_threshold(self, config: MemoryConfig) -> int:
        if int(config.compression_threshold) > 0:
            return int(config.compression_threshold)
        return max(1, int(config.short_term_max_turns))

    def _compressor(self, config: MemoryConfig) -> MessageCompressor:
        strategy = str(config.compression_strategy or "window")
        if strategy == "llm_summary":
            return build_compressor(strategy_name=f"{strategy}:{config.llm_compression_task_type}")
        return build_compressor(strategy_name=strategy)

    def _noise_filter(self, config: MemoryConfig) -> NoiseFilter | None:
        if not config.memory_noise_filter_enabled:
            return None
        if "noise" not in {str(x) for x in config.filter_strategies}:
            return None
        return self._default_noise_filter

    def _duplicate_filter(self, config: MemoryConfig) -> DuplicateRecentFilter | None:
        if "duplicate_recent" not in {str(x) for x in config.filter_strategies}:
            return None
        return DuplicateRecentFilter(window_size=max(1, int(config.short_term_dedup_window)))


memory_gateway = MemoryGateway()
