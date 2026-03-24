"""
Agent 注册表。
启动时由各域的 register.py 填充，运行时按 agent_id 查找。
"""
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from core.memory_rag.memory.config import MemoryConfig, DEFAULT_MEMORY_CONFIG
from shared.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AgentMeta:
    agent_id: str
    name: str
    description: str
    # 工厂函数：每次调用返回一个新的编译后 LangGraph agent
    factory: Callable[[], Any]
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    # 该域的记忆和 RAG 策略，不传则使用框架默认值
    memory_config: MemoryConfig = field(default_factory=lambda: DEFAULT_MEMORY_CONFIG)
    # 该 Agent 支持的 MCP tool 名称列表（用于文档展示）
    tools: list[str] = field(default_factory=list)


class AgentRegistry:
    def __init__(self) -> None:
        self._registry: dict[str, AgentMeta] = {}

    def register(self, meta: AgentMeta) -> None:
        if meta.agent_id in self._registry:
            logger.warning("agent_id_overwritten", agent_id=meta.agent_id)
        self._registry[meta.agent_id] = meta
        logger.info("agent_registered", agent_id=meta.agent_id, name=meta.name)

    def get(self, agent_id: str) -> Optional[AgentMeta]:
        return self._registry.get(agent_id)

    def list_all(self) -> list[AgentMeta]:
        return list(self._registry.values())

    def exists(self, agent_id: str) -> bool:
        return agent_id in self._registry


registry = AgentRegistry()
