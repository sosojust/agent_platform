import json
from unittest.mock import Mock
import pytest

from core.memory_rag.memory.config import MemoryConfig
from core.memory_rag.memory.manager import MemoryGateway


class FakeRedis:
    def __init__(self) -> None:
        self._lists: dict[str, list[str]] = {}
        self._expires: dict[str, int] = {}
        self._kv: dict[str, str] = {}

    async def rpush(self, key: str, value: str) -> None:
        self._lists.setdefault(key, []).append(value)

    async def expire(self, key: str, ttl: int) -> None:
        self._expires[key] = ttl

    async def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))

    async def ltrim(self, key: str, start: int, end: int) -> None:
        items = self._lists.get(key, [])
        self._lists[key] = self._slice(items, start, end)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self._lists.get(key, [])
        return self._slice(items, start, end)

    async def get(self, key: str) -> str | None:
        return self._kv.get(key)

    async def set(self, key: str, value: str) -> None:
        self._kv[key] = value

    def _slice(self, items: list[str], start: int, end: int) -> list[str]:
        n = len(items)
        if n == 0:
            return []
        if start < 0:
            start = n + start
        if end < 0:
            end = n + end
        start = max(0, start)
        end = min(n - 1, end)
        if start > end:
            return []
        return items[start : end + 1]


async def test_append_short_term_filters_noise_text() -> None:
    manager = MemoryGateway()
    fake = FakeRedis()
    manager._client = fake
    cfg = MemoryConfig(memory_noise_filter_enabled=True)
    await manager.append_short_term(
        conversation_id="c1",
        role="user",
        content="好的",
        tenant_id="t1",
        config=cfg,
    )
    assert await fake.llen("mem:t1:c1") == 0


async def test_append_short_term_deduplicates_recent_content() -> None:
    manager = MemoryGateway()
    fake = FakeRedis()
    manager._client = fake
    cfg = MemoryConfig(memory_noise_filter_enabled=True)
    await manager.append_short_term(
        conversation_id="c2",
        role="user",
        content="我要查询保单",
        tenant_id="t1",
        config=cfg,
    )
    await manager.append_short_term(
        conversation_id="c2",
        role="user",
        content="我要查询保单",
        tenant_id="t1",
        config=cfg,
    )
    assert await fake.llen("mem:t1:c2") == 1


async def test_append_short_term_keeps_noise_when_filter_disabled() -> None:
    manager = MemoryGateway()
    fake = FakeRedis()
    manager._client = fake
    cfg = MemoryConfig(memory_noise_filter_enabled=False)
    await manager.append_short_term(
        conversation_id="c3",
        role="assistant",
        content="好的",
        tenant_id="t1",
        config=cfg,
    )
    context = await manager.build_memory_context(
        conversation_id="c3",
        query="",
        tenant_id="t1",
        config=cfg,
    )
    assert context == "assistant: 好的"
    item = (await fake.lrange("mem:t1:c3", 0, -1))[0]
    payload = json.loads(item)
    assert payload["content"] == "好的"


async def test_short_term_trigger_consolidate(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = MemoryGateway()
    fake = FakeRedis()
    manager._client = fake
    cfg = MemoryConfig(
        long_term_enabled=True,
        memory_noise_filter_enabled=False,
        short_to_long_trigger_turns=2,
    )
    append_long_term_mock = Mock(return_value=2)
    monkeypatch.setattr(manager, "append_long_term", append_long_term_mock)
    await manager.append_short_term(
        conversation_id="c4",
        role="user",
        content="第一句",
        tenant_id="t1",
        config=cfg,
    )
    await manager.append_short_term(
        conversation_id="c4",
        role="assistant",
        content="第二句",
        tenant_id="t1",
        config=cfg,
    )
    assert append_long_term_mock.call_count == 1


async def test_build_memory_context_merges_long_term(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = MemoryGateway()
    fake = FakeRedis()
    manager._client = fake
    write_cfg = MemoryConfig(long_term_enabled=False, memory_noise_filter_enabled=False)
    await manager.append_short_term(
        conversation_id="c5",
        role="user",
        content="查询理赔进度",
        tenant_id="t1",
        config=write_cfg,
    )

    async def _fake_retrieve_long_term(
        query: str,
        tenant_id: str,
        config: MemoryConfig,
        memory_types: list[str] | None = None,
        top_k: int | None = None,
    ) -> list[str]:
        return ["历史理赔记录A", "用户偏好B"]

    monkeypatch.setattr(manager, "retrieve_long_term", _fake_retrieve_long_term)
    read_cfg = MemoryConfig(
        long_term_enabled=True,
        memory_noise_filter_enabled=False,
        long_term_retrieve_top_k=2,
    )
    context = await manager.build_memory_context(
        conversation_id="c5",
        query="理赔",
        tenant_id="t1",
        config=read_cfg,
    )
    assert "user: 查询理赔进度" in context
    assert "memory: 历史理赔记录A" in context
