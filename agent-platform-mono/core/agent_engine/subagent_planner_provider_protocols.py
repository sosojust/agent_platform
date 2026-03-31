from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol, TypedDict

from core.agent_engine.agents.registry import AgentMeta

SubagentPlannerExecutor = Literal["llm", "subagents"]
SubagentAggregationStrategy = Literal[
    "summary",
    "priority",
    "vote",
    "confidence_rank",
    "conflict_resolution",
]


class SubagentPlannerDecision(TypedDict):
    executor: SubagentPlannerExecutor
    reason: str
    decision_source: str
    sub_agents: list[str]
    aggregation_strategy: SubagentAggregationStrategy
    preferred_agent_ids: list[str]
    aggregation_params: dict[str, Any]
    confidence_score: float
    merge_debug: dict[str, Any]


class SubagentPlannerProvider(Protocol):
    async def resolve(
        self,
        *,
        meta: AgentMeta,
        user_input: str,
        state: Mapping[str, Any],
        available_sub_agents: Sequence[str],
    ) -> SubagentPlannerDecision:
        ...
