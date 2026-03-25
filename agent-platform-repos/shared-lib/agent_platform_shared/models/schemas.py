"""跨服务公用 Pydantic 模型。"""
from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum


class AgentRunRequest(BaseModel):
    agent_id: str
    input: str
    conversation_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunResponse(BaseModel):
    conversation_id: str
    output: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class LLMRequest(BaseModel):
    messages: list[dict[str, str]]
    task_type: str = "simple"       # simple | complex | local
    temperature: float = 0.7
    max_tokens: int = 2048


class LLMResponse(BaseModel):
    output: str
    usage: dict[str, int] = Field(default_factory=dict)


class RAGRetrieveRequest(BaseModel):
    query: str
    tenant_id: str
    collection_type: str = "business"
    top_k_recall: int = 20
    top_k_rerank: int = 5
    rewrite: bool = True


class RAGRetrieveResponse(BaseModel):
    documents: list[str]


class MemoryGetRequest(BaseModel):
    conversation_id: str
    query: str
    tenant_id: str


class MemoryGetResponse(BaseModel):
    context: str


class MemoryAppendRequest(BaseModel):
    conversation_id: str
    role: str
    content: str
    tenant_id: str


class StreamEvent(BaseModel):
    event: str      # token | step_start | step_end | done | error
    data: Any


class MemoryType(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
