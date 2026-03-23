"""Agent 注册表测试。"""
import pytest
from agent_service.agents.registry import AgentRegistry, AgentMeta
from memory_rag.memory.config import MemoryConfig


def _make_meta(agent_id: str) -> AgentMeta:
    return AgentMeta(
        agent_id=agent_id,
        name=f"Test Agent {agent_id}",
        description="test",
        factory=lambda: None,
    )


def test_register_and_get():
    reg = AgentRegistry()
    reg.register(_make_meta("test-001"))
    meta = reg.get("test-001")
    assert meta is not None
    assert meta.agent_id == "test-001"


def test_get_missing_returns_none():
    reg = AgentRegistry()
    assert reg.get("non-existent") is None


def test_list_all():
    reg = AgentRegistry()
    reg.register(_make_meta("a"))
    reg.register(_make_meta("b"))
    assert len(reg.list_all()) == 2


def test_default_memory_config():
    """未指定 memory_config 时应使用框架默认值"""
    reg = AgentRegistry()
    reg.register(_make_meta("default-cfg"))
    meta = reg.get("default-cfg")
    assert meta is not None
    assert isinstance(meta.memory_config, MemoryConfig)
    assert meta.memory_config.short_term_max_turns == 20  # 框架默认值
