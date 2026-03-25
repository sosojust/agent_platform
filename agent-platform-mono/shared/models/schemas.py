"""跨层公用 Pydantic 模型。"""
from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum


class AgentRunRequest(BaseModel):
    agent_id: str = Field(description="要调用的 Agent 标识，如 'policy-assistant'")
    input: str = Field(description="用户输入")
    conversation_id: Optional[str] = Field(default=None, description="对话 ID（跨端/跨渠道稳定标识），不传则自动生成")
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunResponse(BaseModel):
    conversation_id: str
    output: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class StreamEvent(BaseModel):
    event: str  # token | step_start | step_end | done | error
    data: Any


class MemoryType(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
