from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage


class OrchestratorState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    conversation_id: str
    tenant_id: str
    memory_context: str
    rag_context: str
    step_count: int
    error_count: int
    route_decision: dict[str, Any]
    selected_tools: list[str]
    plan: list[dict[str, Any]]
    past_steps: list[dict[str, Any]]
    replan_count: int
    metadata: dict[str, Any]


def make_initial_state(messages: list[BaseMessage], conversation_id: str, tenant_id: str) -> OrchestratorState:
    return {
        "messages": messages,
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "memory_context": "",
        "rag_context": "",
        "step_count": 0,
        "error_count": 0,
        "route_decision": {},
        "selected_tools": [],
        "plan": [],
        "past_steps": [],
        "replan_count": 0,
        "metadata": {},
    }
