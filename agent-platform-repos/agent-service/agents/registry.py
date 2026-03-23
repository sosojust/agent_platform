"""Agent 注册表，启动时由各域 register.py 填充。"""
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AgentMeta:
    agent_id: str
    name: str
    description: str
    factory: Callable[[], Any]       # 返回编译后的 LangGraph CompiledGraph
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    # 该 agent 使用的 tool name 列表（用于从 mcp-service 拉取的 schema 中过滤）
    tool_names: list[str] = field(default_factory=list)
    # RAG 参数覆盖（None 时使用框架默认值）
    rag_top_k_recall: int = 20
    rag_top_k_rerank: int = 5
    rag_rerank_threshold: float = 0.3
    long_term_memory: bool = True


class AgentRegistry:
    def __init__(self) -> None:
        self._store: dict[str, AgentMeta] = {}

    def register(self, meta: AgentMeta) -> None:
        self._store[meta.agent_id] = meta
        logger.info("agent_registered", agent_id=meta.agent_id, name=meta.name)

    def get(self, agent_id: str) -> Optional[AgentMeta]:
        return self._store.get(agent_id)

    def list_all(self) -> list[AgentMeta]:
        return list(self._store.values())

    def exists(self, agent_id: str) -> bool:
        return agent_id in self._store


registry = AgentRegistry()
