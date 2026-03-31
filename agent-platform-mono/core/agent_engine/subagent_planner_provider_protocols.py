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


class AggregationConfig(TypedDict):
    """Aggregation phase configuration — how results should be combined."""
    aggregation_strategy: SubagentAggregationStrategy
    preferred_agent_ids: list[str]
    aggregation_params: dict[str, Any]


class RoutingDecision(TypedDict):
    """Routing phase decision — which executor to use and which sub-agents to invoke."""
    executor: SubagentPlannerExecutor
    reason: str
    decision_source: str
    sub_agents: list[str]
    confidence_score: float
    merge_debug: dict[str, Any]


class SubagentPlannerDecision(RoutingDecision, AggregationConfig):
    """Combined planner decision (routing + aggregation).

    Kept as a single TypedDict for backward compatibility with existing callers.
    Downstream code should prefer reading routing fields from RoutingDecision and
    aggregation fields from AggregationConfig when the two concerns need to be
    handled separately.
    """


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
